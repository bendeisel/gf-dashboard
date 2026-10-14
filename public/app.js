const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
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

/* ---------------- icons ---------------- */
const I = {
  plus: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"/></svg>',
  shell: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 17l6-6-6-6M12 19h8"/></svg>',
  sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4.2"/><path d="M12 2v2.5M12 19.5V22M4.2 4.2l1.8 1.8M18 18l1.8 1.8M2 12h2.5M19.5 12H22M4.2 19.8 6 18M18 6l1.8-1.8"/></svg>',
  moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>',
  page: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>',
  claude: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/><circle cx="12" cy="12" r="3"/></svg>',
  skill: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>',
};
const CAT_ICON = {
  Ads: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11v2a1 1 0 0 0 1 1h3l5 4V6L7 10H4a1 1 0 0 0-1 1zM16 9a3 3 0 0 1 0 6"/></svg>',
  Automation: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="5" cy="12" r="2"/><circle cx="19" cy="6" r="2"/><circle cx="19" cy="18" r="2"/><path d="M7 12h5M12 12l5-5M12 12l5 5"/></svg>',
  GoHighLevel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>',
  Social: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="M8.6 10.5l6.8-4M8.6 13.5l6.8 4"/></svg>',
  Websites: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>',
  Outreach: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.3"/></svg>',
  Productivity: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5h16v14H4zM4 13h5a3 3 0 0 0 6 0h5"/></svg>',
  Planning: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="4" width="14" height="17" rx="1"/><path d="M9 4V3h6v1M8 10h8M8 14h8M8 18h5"/></svg>',
  General: I.skill,
};
const catIcon = (c) => CAT_ICON[c] || CAT_ICON.General;

/* ---------------- theme ---------------- */
const THEME_KEY = 'gf-theme';
const curTheme = () => (document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');
function setTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  try { localStorage.setItem(THEME_KEY, t); } catch {}
  const btn = $('#themeToggle'); if (btn) btn.innerHTML = curTheme() === 'dark' ? I.sun : I.moon;
}
$('#themeToggle').onclick = () => setTheme(curTheme() === 'dark' ? 'light' : 'dark');
setTheme(curTheme());

/* ---------------- terminals ---------------- */
const panes = new Map(); // id -> {id, el, term, fit, ws, info, dead}
let layout = 'auto';
let focusId = null;

function updateTermCount() {
  const b = $('#navTermCount'); if (!b) return;
  b.textContent = panes.size; b.hidden = panes.size === 0;
}

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
  updateTermCount();
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
    $('.dot', p.el).title = 'Connected';
    p.fit.fit();
    ws.send(JSON.stringify({ t: 'resize', cols: p.term.cols, rows: p.term.rows }));
  };
  ws.onmessage = (e) => p.term.write(e.data);
  ws.onclose = () => {
    if (!panes.has(p.id)) return;
    const dot = $('.dot', p.el); dot.classList.add('dead'); dot.title = 'Reconnecting…';
    if (attempt < 8) setTimeout(() => panes.has(p.id) && connect(p, attempt + 1), Math.min(500 * 2 ** attempt, 8000));
  };
}

/* ---- clipboard helpers (terminals) ---- */
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; }
  catch {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.cssText = 'position:fixed;opacity:0';
    document.body.append(ta); ta.select();
    let ok = false; try { ok = document.execCommand('copy'); } catch {}
    ta.remove(); return ok;
  }
}
function bufferText(term) {
  const b = term.buffer.active, out = [];
  for (let i = 0; i < b.length; i++) out.push(b.getLine(i)?.translateToString(true) ?? '');
  return out.join('\n').replace(/\s+$/, '');
}
async function termCopy(p) {
  const sel = p.term.getSelection();
  const text = sel || bufferText(p.term);
  if (!text) return toast('Nothing to copy yet.');
  toast((await copyText(text)) ? (sel ? 'Copied selection.' : 'Copied the whole terminal output.') : 'The browser blocked copying.');
}
async function termPaste(p) {
  try { const t = await navigator.clipboard.readText(); if (t) p.term.paste(t); }
  catch { toast('Allow clipboard access for this site, or press Ctrl/Cmd+V.'); }
  p.term.focus();
}

/* ---- voice dictation (Wispr Flow, via the server) ---- */
let VOICE_ON = false; // set at boot from /api/config; gates the mic button
const voice = { rec: null, chunks: [], stream: null, pane: null, btn: null, timer: null };

function setMic(btn, state) { // state: idle | rec | busy
  if (!btn) return;
  btn.classList.toggle('rec', state === 'rec');
  btn.classList.toggle('busy', state === 'busy');
  btn.disabled = state === 'busy';
  btn.title = state === 'rec' ? 'Stop and insert transcription'
    : state === 'busy' ? 'Transcribing…' : 'Dictate with your voice (Wispr Flow)';
}

// Decode whatever MediaRecorder gave us, resample to 16kHz mono, and build a 16-bit PCM WAV.
async function toWav16k(blob) {
  const AC = window.AudioContext || window.webkitAudioContext;
  const tmp = new AC();
  const decoded = await tmp.decodeAudioData(await blob.arrayBuffer());
  tmp.close?.();
  const dstRate = 16000, frames = Math.max(1, Math.ceil(decoded.duration * dstRate));
  const off = new OfflineAudioContext(1, frames, dstRate);
  const src = off.createBufferSource(); src.buffer = decoded; src.connect(off.destination); src.start(0);
  const data = (await off.startRendering()).getChannelData(0);
  const ab = new ArrayBuffer(44 + data.length * 2), dv = new DataView(ab);
  const str = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); dv.setUint32(4, 36 + data.length * 2, true); str(8, 'WAVE'); str(12, 'fmt ');
  dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, dstRate, true); dv.setUint32(28, dstRate * 2, true); dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
  str(36, 'data'); dv.setUint32(40, data.length * 2, true);
  let o = 44; for (let i = 0; i < data.length; i++) { const s = Math.max(-1, Math.min(1, data[i])); dv.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true); o += 2; }
  return ab;
}
function abToBase64(ab) {
  const b = new Uint8Array(ab); let s = ''; const chunk = 0x8000;
  for (let i = 0; i < b.length; i += chunk) s += String.fromCharCode.apply(null, b.subarray(i, i + chunk));
  return btoa(s);
}

async function toggleVoice(p, btn) {
  if (voice.rec) return stopVoice();            // already recording → stop & transcribe
  if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) return toast('This browser can’t record audio.');
  let stream;
  try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
  catch { return toast('Allow microphone access to dictate.'); }
  Object.assign(voice, { stream, chunks: [], pane: p, btn });
  const rec = new MediaRecorder(stream);
  voice.rec = rec;
  rec.ondataavailable = (e) => { if (e.data.size) voice.chunks.push(e.data); };
  rec.onstop = finishVoice;
  rec.start();
  setMic(btn, 'rec');
  voice.timer = setTimeout(stopVoice, 90000);   // 90s safety cap
}
function stopVoice() {
  clearTimeout(voice.timer);
  if (voice.rec && voice.rec.state !== 'inactive') voice.rec.stop();
}
async function finishVoice() {
  const { pane, btn, chunks, stream } = voice;
  stream?.getTracks().forEach((t) => t.stop());
  voice.rec = null; voice.stream = null;
  if (!chunks.length) return setMic(btn, 'idle');
  setMic(btn, 'busy');
  try {
    const wav = await toWav16k(new Blob(chunks, { type: chunks[0].type || 'audio/webm' }));
    const { text } = await api('/api/voice/transcribe', { method: 'POST', body: { audio: abToBase64(wav), language: ['en'] } });
    const out = (text || '').trim();
    if (out) { pane.term.paste(out); pane.term.focus(); toast('Inserted dictation — review it, then press Enter.'); }
    else toast('Didn’t catch any speech. Try again.');
  } catch (e) {
    if (/set up|WISPR/i.test(e.message)) { VOICE_ON = false; $$('button[data-a="mic"]').forEach((b) => b.remove()); toast('Voice isn’t set up on the server yet.'); }
    else toast(e.message || 'Transcription failed.');
  } finally {
    setMic(btn, 'idle');
  }
}

const KIND_LABEL = { claude: 'Claude', shell: 'Shell', skill: 'Skill' };
function addPane(info) {
  if (panes.has(info.id)) return;
  const kind = info.kind || 'shell';
  const badge = KIND_LABEL[kind] || 'Session';
  const el = document.createElement('div');
  el.className = 'pane';
  el.innerHTML = `<div class="pane-head"><span class="dot" title="Connected"></span>
    <span class="badge ${esc(kind)}">${esc(badge)}</span>
    <span class="grow title" title="Double-click to rename">${esc(info.title)}</span>
    ${VOICE_ON ? `<button class="txt mic" data-a="mic" title="Dictate with your voice (Wispr Flow)" aria-label="Dictate"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4"/></svg></button>` : ''}
    <button class="txt" data-a="copy" title="Copy the selected text, or the whole output if nothing is selected">Copy</button>
    <button class="txt" data-a="paste" title="Paste from your clipboard">Paste</button>
    <button data-a="focus" title="Maximize / restore" aria-label="Maximize">⤢</button>
    <button data-a="close" title="Close session" aria-label="Close session">✕</button></div><div class="pane-body"></div>`;
  $('#termGrid').append(el);

  const term = new Terminal({
    fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 13, cursorBlink: true, scrollback: 5000,
    macOptionClickForcesSelection: true,
    theme: { background: '#14110F', foreground: '#EAE4DA', cursor: '#E66B3A', selectionBackground: '#5a3a2a' },
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.open($('.pane-body', el));
  const p = { id: info.id, el, term, fit, ws: null, info };
  panes.set(info.id, p);

  term.onData((d) => sendTo(p, d));
  term.attachCustomKeyEventHandler((e) => {
    if (e.type !== 'keydown') return true;
    if (e.key === 'Enter' && e.shiftKey) { sendTo(p, '\x1b\r'); return false; }
    if ((e.ctrlKey || e.metaKey) && !e.altKey && e.key.toLowerCase() === 'c' && (e.shiftKey || e.metaKey || term.hasSelection())) {
      e.preventDefault();
      if (term.hasSelection()) termCopy(p);
      return false;
    }
    return true;
  });
  // copy-on-select (debounced); silent so dragging doesn't spam toasts
  let selT; term.onSelectionChange(() => { clearTimeout(selT); selT = setTimeout(() => { const t = term.getSelection(); if (t) copyText(t); }, 150); });
  // right-click: copy if something is selected, otherwise paste (Shift+right-click keeps the browser menu)
  $('.pane-body', el).addEventListener('contextmenu', (e) => {
    if (e.shiftKey) return;
    e.preventDefault();
    term.hasSelection() ? termCopy(p) : termPaste(p);
  });
  new ResizeObserver(() => { if (!el.hidden) fitAll(); }).observe($('.pane-body', el));

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
    if (a === 'mic') toggleVoice(p, e.target.closest('button'));
    if (a === 'copy') termCopy(p);
    if (a === 'paste') termPaste(p);
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
  try {
    if (!localStorage.getItem('gf-copy-tip')) {
      localStorage.setItem('gf-copy-tip', '1');
      setTimeout(() => toast('Tip: hold Shift (Option on Mac) and drag to select text. The Copy / Paste buttons on each pane always work.'), 1500);
    }
  } catch {}
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

const pickedDir = () => $('#dirPick')?.value || '';
$('#newShell').onclick = () => newTerminal({ kind: 'shell', cwd: pickedDir() });
$('#newClaude').onclick = () => newTerminal({ kind: 'claude', cwd: pickedDir() });
$('#emptyClaude').onclick = () => newTerminal({ kind: 'claude', cwd: pickedDir() });
$('#quickNew').onclick = () => openPalette();
$('#homeNewClaude').onclick = () => newTerminal({ kind: 'claude', cwd: pickedDir() });
$('#homeSkills').onclick = () => (location.hash = '#/skills');
$('#homePalette').onclick = () => openPalette();

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
  return `<div class="card"><h3><span class="card-ico">${catIcon(s.category)}</span>${esc(s.title)}</h3>
    <p>${esc(s.description)}</p>
    <div class="meta"><span class="chip">${esc(s.category)}</span>${s.tags.slice(0, 3).map((t) => `<span class="chip neutral">${esc(t)}</span>`).join('')}</div>
    <button class="btn primary small" data-skill="${esc(s.slug)}">Open</button></div>`;
}
function skillSkeletons(n = 6) {
  return Array.from({ length: n }, () => `<div class="sk-card"><div class="sk sk-line w-60"></div><div class="sk sk-line w-80"></div><div class="sk sk-line w-40"></div></div>`).join('');
}

function renderSkills() {
  const q = $('#skillSearch').value.trim().toLowerCase();
  const cat = $('#skillCat').value;
  const list = skillData.skills.filter((s) =>
    (!cat || s.category === cat) &&
    (!q || `${s.title} ${s.description} ${s.tags.join(' ')}`.toLowerCase().includes(q)));
  $('#skillGrid').innerHTML = list.length ? list.map(skillCard).join('')
    : `<div class="empty-state"><div class="ico">${I.skill}</div><h3>No skills match</h3><p>Try a different search or category.</p></div>`;
}

function renderGhl() {
  const list = skillData.skills.filter((s) => s.category === 'GoHighLevel');
  $('#ghlGrid').innerHTML =
    `<div class="card"><h3><span class="card-ico">${I.shell}</span>GHL shell</h3><p>A plain terminal in the working directory. Run <code>ghl</code> commands yourself.</p>
      <button class="btn small" id="ghlShell">Open shell</button></div>` +
    list.map(skillCard).join('');
  $('#ghlShell').onclick = () => newTerminal({ kind: 'shell' });
}

async function loadSkills() {
  $('#skillGrid').innerHTML = skillSkeletons();
  skillData = await api('/api/skills');
  const sel = $('#skillCat');
  sel.innerHTML = '<option value="">All categories</option>' + skillData.categories.map((c) => `<option>${esc(c)}</option>`).join('');
  renderSkills(); renderGhl();
}
$('#skillSearch').oninput = renderSkills;
$('#skillCat').onchange = renderSkills;

/* ---- skill launcher dialog ---- */
const dlg = $('#launch');
let launching = null;
let pending = [];

function openLauncher(s, preset = '') {
  if (!s) return;
  launching = s; pending = [];
  $('#lCat').textContent = s.category;
  $('#lTitle').textContent = s.title;
  $('#lDesc').textContent = s.description;
  $('#lInput').value = preset;
  $('#lInput').placeholder = s.input;
  $('#lList').textContent = '';
  $('#lErr').textContent = '';
  dlg.showModal();
  $('#lInput').focus();
}
function openSlug(slug, preset = '') {
  const s = skillData.skills.find((x) => x.slug === slug);
  if (!s) return toast('That skill isn’t available yet — opening a plain Claude session instead.') || newTerminal({ kind: 'claude', cwd: pickedDir() });
  openLauncher(s, preset);
}

document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-skill]');
  if (!b) return;
  openLauncher(skillData.skills.find((s) => s.slug === b.dataset.skill));
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

/* ---------------- metrics ---------------- */
function ago(ts) {
  const s = Math.max(0, (Date.now() - ts) / 1000);
  if (s < 50) return 'just now';
  const m = Math.floor(s / 60); if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60); return `${h}h ago`;
}
function sparkline(vals) {
  if (!Array.isArray(vals) || vals.length < 2) return '';
  const w = 100, h = 26, max = Math.max(...vals), min = Math.min(...vals), rng = max - min || 1;
  const pts = vals.map((v, i) => [i / (vals.length - 1) * w, h - ((v - min) / rng) * (h - 3) - 1.5]);
  const d = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
  const last = pts[pts.length - 1];
  return `<div class="tile-spark"><svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><path d="${d}" fill="none" stroke="var(--accent)" stroke-width="1.6" vector-effect="non-scaling-stroke" stroke-linecap="round" stroke-linejoin="round"/><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2" fill="var(--accent)"/></svg></div>`;
}
function tileHtml(t) {
  const spark = sparkline(t.history);
  return `<div class="tile"><div class="tile-v">${Number(t.value).toLocaleString()}</div><div class="tile-l">${esc(t.label)}</div>${spark}</div>`;
}
function initials(name) { return name.replace(/\(.*?\)/g, '').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase() || '•'; }

function metricCard(b) {
  const head = `<div class="metric-head"><span class="metric-logo">${esc(initials(b.name))}</span><h3>${esc(b.name)}</h3></div>`;
  if (b.needsToken) {
    return `<div class="card metric-card">${head}
      <p class="muted">Add this location's Private Integration Token to show live numbers.</p>
      <span class="status-pill wait"><span class="d"></span>Add API token</span></div>`;
  }
  if (b.error) {
    return `<div class="card metric-card">${head}
      <p class="muted">${esc(b.error)}</p>
      <span class="status-pill err"><span class="d"></span>Error</span></div>`;
  }
  const tiles = (b.tiles || []).map(tileHtml).join('');
  return `<div class="card metric-card">${head}
    <div class="metric-sub"><span class="status-pill live"><span class="d"></span>Live</span>
      <span>Updated ${ago(b.updated)}</span>
      <button class="refresh" data-refresh="${esc(b.key || '')}" title="Refresh"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6"/></svg></button></div>
    <div class="tiles">${tiles}</div></div>`;
}
function metricSkeletons(n = 4) {
  return Array.from({ length: n }, () => `<div class="sk-card"><div class="sk sk-line w-40"></div><div class="tiles" style="margin-top:14px"><div class="sk sk-tile"></div><div class="sk sk-tile"></div><div class="sk sk-tile"></div><div class="sk sk-tile"></div></div></div>`).join('');
}
let metricsCache = null;
async function loadMetrics(fresh = false) {
  const grid = $('#metricsGrid');
  if (!metricsCache || fresh) grid.innerHTML = metricSkeletons();
  try {
    const { businesses } = await api('/api/metrics' + (fresh ? '?fresh=1' : ''));
    metricsCache = businesses;
    grid.innerHTML = businesses.length ? businesses.map(metricCard).join('')
      : `<div class="empty-state"><div class="ico">${I.page}</div><h3>No businesses configured</h3><p>Add entries to metrics.config.json to track a business here.</p></div>`;
  } catch (e) { grid.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}
$('#metricsRefresh').onclick = () => loadMetrics(true);
$('#metricsGrid').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-refresh]');
  if (!btn) return;
  btn.classList.add('spin');
  loadMetrics(true);
});

/* ---------------- phase-2 launcher pages ---------------- */
function launchCard({ ico, title, desc, btn, action }) {
  const id = 'lc_' + Math.random().toString(36).slice(2, 8);
  setTimeout(() => { const el = document.getElementById(id); if (el) el.onclick = action; });
  return `<div class="card"><h3><span class="card-ico">${ico}</span>${esc(title)}</h3><p>${esc(desc)}</p>
    <button class="btn primary small" id="${id}">${esc(btn)}</button></div>`;
}
function openLink(url) { window.open(url, '_blank', 'noopener'); }

function seoProjectHtml(p) {
  const tiles = (p.tiles || []).map((t) => `<div class="tile"><div class="tile-v">${Number(t.value).toLocaleString()}</div><div class="tile-l">${esc(t.label)}</div>${sparkline(t.history)}</div>`).join('');
  const kws = (p.keywords || []).map((k) => `<tr><td>${esc(k.kw)}</td><td class="seo-pos ${k.pos <= 10 ? 'p1' : k.pos <= 20 ? 'p2' : 'p3'}">#${k.pos}</td><td class="muted">${Number(k.vol).toLocaleString()}/mo</td></tr>`).join('');
  const comps = `<div class="seo-comp">${(p.competitors || []).map((c) => `<a href="https://${esc(c.domain)}" target="_blank" rel="noopener"><b>${esc(c.name)}</b><span class="cd">${esc(c.domain)}${c.note ? ' · ' + esc(c.note) : ''}</span></a>`).join('')}</div>`;
  const audit = p.audit ? `<div style="margin-top:12px"><div class="seo-h">Latest audit</div><span class="chip neutral">${esc(p.audit.when)} · ${p.audit.pages} pages · ${esc(p.audit.status || 'done')}</span> <a class="btn small" href="${esc(p.audit.url || p.url)}" target="_blank" rel="noopener">View ↗</a></div>` : '';
  return `<div class="panel seo-panel">
    <div class="metric-head"><span class="metric-logo">${esc(initials(p.name))}</span><h3>${esc(p.name)} <span class="muted" style="font-weight:600;font-size:13px">· ${esc(p.domain)}</span></h3><a class="btn small" href="${esc(p.url)}" target="_blank" rel="noopener">OpenSEO ↗</a></div>
    ${p.goal ? `<p class="muted" style="font-size:12.5px;margin:2px 0 14px">${esc(p.goal)}</p>` : ''}
    <div class="stat-strip">${tiles}</div>
    <div class="seo-cols">
      <div><div class="seo-h">Top keywords</div><table class="seo-tbl"><tbody>${kws || '<tr><td class="muted">No keyword data.</td></tr>'}</tbody></table></div>
      <div><div class="seo-h">Competitors</div>${comps}${audit}</div>
    </div></div>`;
}
function renderSeoLaunchers() {
  const ico = CAT_ICON.Websites;
  const cards = [
    { ico, title: 'OpenSEO research session', desc: 'Start a Claude session preloaded with the OpenSEO playbook — keywords, audits, competitors, local.', btn: 'Launch session', action: () => openSlug('seo-openseo', '') },
    { ico, title: 'Refresh live data', desc: 'Pull the latest OpenSEO numbers for every tracked project onto this page.', btn: 'Refresh now', action: () => openSlug('seo-refresh', '') },
    { ico, title: 'Site audit', desc: 'Crawl a site and deliver a plain-language one-page SEO report with a do-this-week action.', btn: 'Start', action: () => openSlug('seo-openseo', 'Run a site audit for: ') },
    { ico, title: 'Brand research + SEO', desc: 'Redo brand research and an SEO baseline before a rebuild.', btn: 'Start', action: () => openSlug('brand-research-seo', '') },
  ];
  $('#seoGrid').innerHTML = cards.map(launchCard).join('');
  $('#seoLaunchHead').hidden = false;
}
async function renderSeo() {
  renderSeoLaunchers();
  try {
    const data = await api('/api/seo');
    if (data.configured && data.projects?.length) {
      $('#seoNotice').hidden = true;
      $('#seoLive').innerHTML =
        `<div class="section-head"><h2>Live — ${esc(data.source || 'OpenSEO')}</h2><span class="status-pill live"><span class="d"></span>Connected</span><div class="grow"></div>${data.updated ? `<span class="muted" style="font-size:12px">Updated ${ago(data.updated)}</span>` : ''}<button class="btn small" id="seoRefresh"><svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-2.6-6.4M21 3v6h-6"/></svg>Refresh data</button></div>`
        + data.projects.map(seoProjectHtml).join('');
      const rb = $('#seoRefresh'); if (rb) rb.onclick = () => openSlug('seo-refresh', '');
    } else {
      $('#seoNotice').hidden = false;
      $('#seoLive').innerHTML = '';
    }
  } catch { $('#seoLive').innerHTML = ''; }
}

let n8nDone = false;
const N8N_URL = 'https://n8n.srv969651.hstgr.cloud';
function renderN8n() {
  if (n8nDone) return; n8nDone = true;
  const ico = CAT_ICON.Automation;
  const cards = [
    { ico, title: 'Open n8n editor', desc: 'Jump to the hosted n8n instance to view and edit workflows.', btn: 'Open editor ↗', action: () => openLink(N8N_URL) },
    { ico, title: 'Build a flow', desc: 'Start a Claude session set up to design, validate and create an n8n workflow.', btn: 'Launch session', action: () => openSlug('n8n-flow', '') },
    { ico, title: 'Audit flows', desc: 'Review existing flows for dead tokens, unpublished changes and silent skips.', btn: 'Start', action: () => openSlug('n8n-flow', 'Audit the existing workflows and report issues (dead tokens, unpublished changes, silent skips). Read-only — do not publish anything.') },
  ];
  $('#n8nGrid').innerHTML = cards.map(launchCard).join('');
}

let hermesDone = false;
function renderHermes() {
  if (hermesDone) return; hermesDone = true;
  const ico = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 1 3 3v1a4 4 0 0 1 4 4v3l1 3H4l1-3v-3a4 4 0 0 1 4-4V5a3 3 0 0 1 3-3zM9 20a3 3 0 0 0 6 0"/></svg>';
  const soon = (title, desc) => `<div class="card"><h3><span class="card-ico">${ico}</span>${esc(title)}</h3><p>${esc(desc)}</p><span class="status-pill soon"><span class="d"></span>Awaiting spec</span></div>`;
  $('#hermesGrid').innerHTML = [
    launchCard({ ico, title: 'Launch Hermes work session', desc: 'Open a Claude session to build or debug Hermes (AZ + Max) pieces.', btn: 'Launch session', action: () => newTerminal({ kind: 'claude', cwd: pickedDir() }) }),
    soon('Runtime status', 'Live/offline, current load, and last heartbeat for the AZ + Max runtime.'),
    soon('Call & booking log', 'Recent live-event responses, bookings and closing actions handled by the agent.'),
    soon('Voice stack', 'ElevenLabs voice health and after-hours bot state.'),
  ].join('');
}

let reportDone = false;
async function renderReporting() {
  const grid = $('#reportGrid');
  if (!reportDone) grid.innerHTML = metricSkeletons(3);
  reportDone = true;
  try {
    const businesses = metricsCache || (await api('/api/metrics')).businesses;
    metricsCache = businesses;
    grid.innerHTML = businesses.map((b) => {
      const status = b.needsToken ? '<span class="status-pill wait"><span class="d"></span>Needs token</span>'
        : b.error ? '<span class="status-pill err"><span class="d"></span>Error</span>'
        : '<span class="status-pill live"><span class="d"></span>Live</span>';
      const body = b.tiles ? `<div class="tiles">${b.tiles.map(tileHtml).join('')}</div>`
        : `<p class="muted">${b.needsToken ? 'Connect this client’s GHL token to generate a report.' : esc(b.error || '')}</p>`;
      const btn = b.tiles ? `<div class="card-foot"><button class="btn small" data-print="${esc(b.key)}">Print / save PDF</button></div>` : '';
      return `<div class="card metric-card"><div class="metric-head"><span class="metric-logo">${esc(initials(b.name))}</span><h3>${esc(b.name)}</h3></div>
        <div class="metric-sub">${status}${b.updated ? `<span>Updated ${ago(b.updated)}</span>` : ''}</div>${body}${btn}</div>`;
    }).join('') || `<div class="empty-state"><div class="ico">${I.page}</div><h3>No clients configured</h3><p>Add businesses to metrics.config.json to report on them.</p></div>`;
  } catch (e) { grid.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}
$('#reportGrid').addEventListener('click', (e) => {
  if (e.target.closest('[data-print]')) window.print();
});

/* ---------------- home ---------------- */
function statTile(v, l) { return `<div class="tile"><div class="tile-v">${v}</div><div class="tile-l">${esc(l)}</div></div>`; }
async function loadHome() {
  // sessions (always fresh)
  const sess = [...panes.values()];
  const sEl = $('#homeSessions');
  sEl.innerHTML = sess.length ? sess.map((p) => `<div class="row-item" data-focus="${esc(p.id)}"><span class="ri-ico">${I[p.info.kind] || I.shell}</span><span class="grow"><b>${esc(p.info.title)}</b><div class="ri-sub">${esc(KIND_LABEL[p.info.kind] || 'Session')}</div></span></div>`).join('')
    : `<p class="muted" style="font-size:13px">No active sessions. <a href="#/terminals">Open one →</a></p>`;

  // quick skills
  const rEl = $('#homeSkillRows');
  const top = skillData.skills.slice(0, 6);
  rEl.innerHTML = top.length ? top.map((s) => `<div class="row-item" data-open="${esc(s.slug)}"><span class="ri-ico">${catIcon(s.category)}</span><span class="grow"><b>${esc(s.title)}</b><div class="ri-sub">${esc(s.category)}</div></span><span class="ri-ico" style="background:transparent">${I.page}</span></div>`).join('')
    : '<p class="muted" style="font-size:13px">Loading skills…</p>';

  // stats
  const statsEl = $('#homeStats');
  statsEl.innerHTML = `<div class="sk sk-tile"></div><div class="sk sk-tile"></div><div class="sk sk-tile"></div><div class="sk sk-tile"></div>`;
  try {
    const businesses = metricsCache || (await api('/api/metrics')).businesses;
    metricsCache = businesses;
    const live = businesses.filter((b) => b.tiles);
    const contactsTile = (b) => (b.tiles || []).find((t) => /contact|member/i.test(t.label));
    const totalContacts = live.reduce((n, b) => n + (Number(contactsTile(b)?.value) || 0), 0);
    statsEl.innerHTML = [
      statTile(sess.length, 'Active sessions'),
      statTile(skillData.skills.length, 'Skills ready'),
      statTile(`${live.length}/${businesses.length}`, 'Businesses live'),
      statTile(totalContacts.toLocaleString(), 'Contacts tracked'),
    ].join('');
  } catch {
    statsEl.innerHTML = [statTile(sess.length, 'Active sessions'), statTile(skillData.skills.length, 'Skills ready')].join('');
  }
}
$('#homeSessions').addEventListener('click', (e) => {
  const id = e.target.closest('[data-focus]')?.dataset.focus;
  if (!id) return;
  location.hash = '#/terminals';
  focusId = id; applyLayout();
});
$('#homeSkillRows').addEventListener('click', (e) => {
  const slug = e.target.closest('[data-open]')?.dataset.open;
  if (slug) openSlug(slug, '');
});

/* ---------------- command palette ---------------- */
const pal = $('#palette');
let palItems = [], palSel = 0;
function paletteActions() {
  const acts = [
    { ico: I.claude, label: 'New Claude session', sub: 'Start a Claude pane', kind: 'action', run: () => newTerminal({ kind: 'claude', cwd: pickedDir() }) },
    { ico: I.shell, label: 'New shell', sub: 'Plain terminal', kind: 'action', run: () => newTerminal({ kind: 'shell', cwd: pickedDir() }) },
  ];
  for (const [r, t] of Object.entries(titles)) acts.push({ ico: I.page, label: t, sub: 'Go to page', kind: 'page', run: () => (location.hash = '#/' + r) });
  acts.push({ ico: curTheme() === 'dark' ? I.sun : I.moon, label: 'Toggle light / dark', sub: 'Theme', kind: 'action', run: () => setTheme(curTheme() === 'dark' ? 'light' : 'dark') });
  for (const s of skillData.skills) acts.push({ ico: catIcon(s.category), label: s.title, sub: s.category, kind: 'skill', run: () => openSlug(s.slug, '') });
  return acts;
}
function renderPalette(q = '') {
  const all = paletteActions();
  const ql = q.trim().toLowerCase();
  palItems = ql ? all.filter((a) => `${a.label} ${a.sub}`.toLowerCase().includes(ql)) : all;
  palSel = 0;
  const list = $('#palList');
  list.innerHTML = palItems.length ? palItems.map((a, i) => `<li class="pal-item${i === 0 ? ' sel' : ''}" data-i="${i}">
    <span class="pi-ico">${a.ico}</span><span class="grow"><b>${esc(a.label)}</b><div class="pi-sub">${esc(a.sub)}</div></span><span class="pi-kind">${esc(a.kind)}</span></li>`).join('')
    : '<li class="pal-empty">No matches</li>';
}
function palMove(d) {
  if (!palItems.length) return;
  palSel = (palSel + d + palItems.length) % palItems.length;
  $$('.pal-item', $('#palList')).forEach((el, i) => el.classList.toggle('sel', i === palSel));
  $('.pal-item.sel', $('#palList'))?.scrollIntoView({ block: 'nearest' });
}
function palRun(i = palSel) {
  const a = palItems[i]; if (!a) return;
  pal.close(); a.run();
}
function openPalette() {
  renderPalette('');
  $('#palInput').value = '';
  if (!pal.open) pal.showModal();
  $('#palInput').focus();
}
$('#paletteBtn').onclick = () => openPalette();
$('#palInput').addEventListener('input', (e) => renderPalette(e.target.value));
$('#palInput').addEventListener('keydown', (e) => {
  if (e.key === 'ArrowDown') { e.preventDefault(); palMove(1); }
  else if (e.key === 'ArrowUp') { e.preventDefault(); palMove(-1); }
  else if (e.key === 'Enter') { e.preventDefault(); palRun(); }
});
$('#palList').addEventListener('click', (e) => {
  const li = e.target.closest('[data-i]'); if (!li) return;
  palRun(Number(li.dataset.i));
});
window.addEventListener('keydown', (e) => {
  if ((e.metaKey || e.ctrlKey) && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    if (pal.open) pal.close(); else openPalette();
  }
});

/* ---------------- routing ---------------- */
const titles = { home: 'Home', terminals: 'Terminals', skills: 'Skills', ghl: 'GHL CLI', seo: 'SEO', n8n: 'Automations', metrics: 'Metrics', reporting: 'Reporting', hermes: 'Hermes' };
function route() {
  const r = location.hash.slice(2) || 'home';
  const name = titles[r] ? r : 'home';
  for (const v of $$('.view')) v.hidden = v.id !== `view-${name}`;
  for (const a of $$('nav a')) a.classList.toggle('on', a.dataset.route === name);
  $('#crumb').textContent = titles[name];
  $('#side').classList.remove('open');
  if (name === 'terminals') requestAnimationFrame(fitAll);
  if (name === 'home') loadHome();
  if (name === 'metrics') loadMetrics();
  if (name === 'reporting') renderReporting();
  if (name === 'seo') renderSeo();
  if (name === 'n8n') renderN8n();
  if (name === 'hermes') renderHermes();
}
window.addEventListener('hashchange', route);
$('#burger').onclick = () => $('#side').classList.toggle('open');
$('#logout').onclick = async () => { await api('/api/logout', { method: 'POST' }); location.href = '/login'; };

/* ---------------- boot ---------------- */
(async () => {
  route();
  api('/api/me').then((m) => {
    if (m.user) {
      $('#userChip').hidden = false;
      $('#userName').textContent = m.user;
      $('#userAv').textContent = (m.user[0] || 'U').toUpperCase();
      $('#logout').querySelector('span').textContent = `Sign out · ${m.user}`;
      $('#homeHi').textContent = `Welcome, ${m.user}`;
    }
  }).catch(() => {});
  VOICE_ON = await api('/api/config').then((c) => !!c.voice).catch(() => false);
  await Promise.all([loadSkills().catch(() => {}), loadDirs().catch(() => {})]);
  const existing = await api('/api/terminals').catch(() => []);
  existing.forEach(addPane);
  applyLayout();
  route();
})();
