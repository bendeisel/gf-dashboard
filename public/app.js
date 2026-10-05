const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json', ...opts.headers } : opts.headers,
    body: opts.body && !(opts.body instanceof FormData) ? JSON.stringify(opts.body) : opts.body,
  });
  if (r.status === 401) { location.href = '/login'; throw new Error('unauthorized'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || `Request failed (${r.status})`);
  return data;
}

let toastTimer;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 3500);
}

/* ---------------- terminals ---------------- */
const panes = new Map(); // id -> {id, el, term, fit, ws, info, dead}
let layout = 'auto';
let focusId = null;

function applyLayout() {
  const grid = $('#termGrid');
  const n = panes.size;
  const cols = focusId ? 1 : layout === 'auto' ? (n <= 1 ? 1 : n <= 4 ? 2 : 3) : Number(layout);
  grid.style.gridTemplateColumns = `repeat(${Math.min(cols, Math.max(n, 1))}, minmax(0, 1fr))`;
  $('#termEmpty').hidden = n > 0;
  grid.hidden = n === 0;
  for (const p of panes.values()) {
    p.el.hidden = !!focusId && p.id !== focusId;
    p.el.classList.toggle('focus', p.id === focusId);
  }
  requestAnimationFrame(fitAll);
}

function fitAll() {
  for (const p of panes.values()) {
    if (p.el.hidden || !p.el.offsetParent) continue;
    try {
      p.fit.fit();
      if (p.ws?.readyState === 1) p.ws.send(JSON.stringify({ t: 'resize', cols: p.term.cols, rows: p.term.rows }));
    } catch {}
  }
}

async function uploadFiles(files) {
  const fd = new FormData();
  for (const f of files) fd.append('files', f, f.name);
  return (await api('/api/upload', { method: 'POST', body: fd })).files;
}

function sendTo(p, text) {
  if (p.ws?.readyState === 1) p.ws.send(JSON.stringify({ t: 'in', d: text }));
}

async function uploadInto(p, files) {
  try {
    const up = await uploadFiles(files);
    sendTo(p, up.map((f) => `"${f.path}"`).join(' ') + ' ');
    toast(`Uploaded ${up.length} file${up.length > 1 ? 's' : ''}; path typed into the terminal.`);
  } catch (e) { toast(e.message); }
}

function connect(p, attempt = 0) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/term/${p.id}`);
  p.ws = ws;
  ws.onopen = () => {
    p.term.reset();
    $('.dot', p.el).classList.remove('dead');
    p.fit.fit();
    ws.send(JSON.stringify({ t: 'resize', cols: p.term.cols, rows: p.term.rows }));
  };
  ws.onmessage = (e) => p.term.write(e.data);
  ws.onclose = () => {
    if (!panes.has(p.id)) return;
    $('.dot', p.el).classList.add('dead');
    if (attempt < 8) setTimeout(() => panes.has(p.id) && connect(p, attempt + 1), Math.min(500 * 2 ** attempt, 8000));
  };
}

function addPane(info) {
  if (panes.has(info.id)) return;
  const el = document.createElement('div');
  el.className = 'pane';
  el.innerHTML = `<div class="pane-head"><span class="dot"></span><span class="grow title" title="Double-click to rename">${esc(info.title)}</span>
    <button data-a="focus" title="Maximize / restore" aria-label="Maximize">⤢</button>
    <button data-a="close" title="Close session" aria-label="Close session">✕</button></div><div class="pane-body"></div>`;
  $('#termGrid').append(el);

  const term = new Terminal({
    fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 13, cursorBlink: true, scrollback: 5000,
    theme: { background: '#14110F', foreground: '#EAE4DA', cursor: '#E66B3A', selectionBackground: '#5a3a2a' },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open($('.pane-body', el));
  const p = { id: info.id, el, term, fit, ws: null, info };
  panes.set(info.id, p);

  term.onData((d) => sendTo(p, d));
  // Shift+Enter => newline without submitting (same as the Claude CLI expects via backslash-enter)
  term.attachCustomKeyEventHandler((e) => {
    if (e.type === 'keydown' && e.key === 'Enter' && e.shiftKey) { sendTo(p, '\x1b\r'); return false; }
    return true;
  });
  new ResizeObserver(() => { if (!el.hidden) fitAll(); }).observe($('.pane-body', el));

  // images/files: paste or drag-and-drop uploads to the server and types the path
  el.addEventListener('paste', (e) => {
    const files = [...(e.clipboardData?.files ?? [])];
    if (!files.length) return;
    e.preventDefault(); e.stopPropagation();
    uploadInto(p, files);
  }, true);
  el.addEventListener('dragover', (e) => { e.preventDefault(); el.classList.add('drop'); });
  el.addEventListener('dragleave', () => el.classList.remove('drop'));
  el.addEventListener('drop', (e) => {
    e.preventDefault(); el.classList.remove('drop');
    if (e.dataTransfer.files.length) uploadInto(p, [...e.dataTransfer.files]);
  });

  $('.title', el).addEventListener('dblclick', (e) => {
    const name = prompt('Rename this session', e.target.textContent);
    if (name && name.trim()) e.target.textContent = name.trim();
  });

  el.addEventListener('click', async (e) => {
    const a = e.target.closest('button')?.dataset.a;
    if (a === 'focus') { focusId = focusId === p.id ? null : p.id; applyLayout(); }
    if (a === 'close') {
      if (!confirm(`Close "${info.title}"? Anything running in it will stop.`)) return;
      await api(`/api/terminals/${p.id}`, { method: 'DELETE' }).catch(() => {});
      removePane(p.id);
    }
  });

  applyLayout();
  connect(p);
  term.focus();
}

function removePane(id) {
  const p = panes.get(id);
  if (!p) return;
  panes.delete(id);
  p.ws?.close(); p.term.dispose(); p.el.remove();
  if (focusId === id) focusId = null;
  applyLayout();
}

async function newTerminal(body) {
  try {
    const info = await api('/api/terminals', { method: 'POST', body });
    location.hash = '#/terminals';
    addPane(info);
    return info;
  } catch (e) { toast(e.message); }
}

const pickedDir = () => $('#dirPick').value || '';
$('#newShell').onclick = () => newTerminal({ kind: 'shell', cwd: pickedDir() });
$('#newClaude').onclick = () => newTerminal({ kind: 'claude', cwd: pickedDir() });
$('#emptyClaude').onclick = () => newTerminal({ kind: 'claude', cwd: pickedDir() });

async function loadDirs() {
  try {
    const { dirs } = await api('/api/dirs');
    const opts = '<option value="">(root)</option>' + dirs.map((d) => `<option value="${esc(d)}">${esc(d)}</option>`).join('');
    $('#dirPick').innerHTML = opts;
    $('#lDir').innerHTML = opts;
  } catch {}
}
$('#layoutSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button');
  if (!b) return;
  layout = b.dataset.l; focusId = null;
  for (const x of $('#layoutSeg').children) x.classList.toggle('on', x === b);
  applyLayout();
});
window.addEventListener('resize', fitAll);

/* ---------------- skills ---------------- */
let skillData = { categories: [], skills: [] };

function skillCard(s) {
  return `<div class="card"><h3>${esc(s.title)}</h3><p>${esc(s.description)}</p>
    <div class="meta"><span class="chip">${esc(s.category)}</span>${s.tags.map((t) => `<span class="chip" style="background:#F0EBE1;color:#4F4840">${esc(t)}</span>`).join('')}</div>
    <button class="btn primary small" data-skill="${esc(s.slug)}">Open</button></div>`;
}

function renderSkills() {
  const q = $('#skillSearch').value.trim().toLowerCase();
  const cat = $('#skillCat').value;
  const list = skillData.skills.filter((s) =>
    (!cat || s.category === cat) &&
    (!q || `${s.title} ${s.description} ${s.tags.join(' ')}`.toLowerCase().includes(q)));
  $('#skillGrid').innerHTML = list.length ? list.map(skillCard).join('') : '<p class="muted">No skills match.</p>';
}

function renderGhl() {
  const list = skillData.skills.filter((s) => s.category === 'GoHighLevel');
  $('#ghlGrid').innerHTML =
    `<div class="card"><h3>GHL shell</h3><p>A plain terminal in the working directory. Run <code>ghl</code> commands yourself.</p>
      <button class="btn small" id="ghlShell">Open shell</button></div>` +
    list.map(skillCard).join('');
  $('#ghlShell').onclick = () => newTerminal({ kind: 'shell' });
}

async function loadSkills() {
  skillData = await api('/api/skills');
  const sel = $('#skillCat');
  sel.innerHTML = '<option value="">All categories</option>' + skillData.categories.map((c) => `<option>${esc(c)}</option>`).join('');
  renderSkills(); renderGhl();
}
$('#skillSearch').oninput = renderSkills;
$('#skillCat').onchange = renderSkills;

const dlg = $('#launch');
let launching = null;
let pending = [];

document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-skill]');
  if (!b) return;
  launching = skillData.skills.find((s) => s.slug === b.dataset.skill);
  if (!launching) return;
  pending = [];
  $('#lCat').textContent = launching.category;
  $('#lTitle').textContent = launching.title;
  $('#lDesc').textContent = launching.description;
  $('#lInput').value = '';
  $('#lInput').placeholder = launching.input;
  $('#lList').textContent = '';
  $('#lErr').textContent = '';
  dlg.showModal();
  $('#lInput').focus();
});
$('#lFiles').onchange = (e) => {
  pending = [...e.target.files];
  $('#lList').textContent = pending.map((f) => f.name).join(', ');
};
$('#lCancel').onclick = () => dlg.close();
$('#launchForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (e.submitter?.value === 'cancel') return dlg.close();
  const go = $('#lGo');
  go.disabled = true; $('#lErr').textContent = '';
  try {
    const attachments = pending.length ? (await uploadFiles(pending)).map((f) => f.path) : [];
    const info = await api('/api/terminals', { method: 'POST', body: { kind: 'skill', skill: launching.slug, input: $('#lInput').value, attachments, cwd: $('#lDir').value || '' } });
    dlg.close();
    location.hash = '#/terminals';
    addPane(info);
  } catch (err) { $('#lErr').textContent = err.message; }
  go.disabled = false;
});

/* ---------------- routing ---------------- */
const titles = { terminals: 'Terminals', skills: 'Skills', ghl: 'GHL CLI', metrics: 'Metrics' };
function route() {
  const r = (location.hash.slice(2) || 'terminals');
  const name = titles[r] ? r : 'terminals';
  for (const v of document.querySelectorAll('.view')) v.hidden = v.id !== `view-${name}`;
  for (const a of document.querySelectorAll('nav a')) a.classList.toggle('on', a.dataset.route === name);
  $('#crumb').textContent = titles[name];
  $('#side').classList.remove('open');
  if (name === 'terminals') requestAnimationFrame(fitAll);
}
window.addEventListener('hashchange', route);
$('#burger').onclick = () => $('#side').classList.toggle('open');
$('#logout').onclick = async () => { await api('/api/logout', { method: 'POST' }); location.href = '/login'; };

/* ---------------- boot ---------------- */
(async () => {
  route();
  api('/api/me').then((m) => { if (m.user) $('#logout').textContent = `Sign out · ${m.user}`; }).catch(() => {});
  await Promise.all([loadSkills().catch(() => {}), loadDirs().catch(() => {})]);
  const existing = await api('/api/terminals').catch(() => []);
  existing.forEach(addPane);
  applyLayout();
  route();
})();
