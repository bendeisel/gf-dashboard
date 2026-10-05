import express from 'express';
import multer from 'multer';
import pty from 'node-pty';
import { WebSocketServer } from 'ws';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadSkills } from './skills.js';
import { getMetrics } from './metrics.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const env = process.env;

const PORT = Number(env.PORT || 3100);
const PASSWORD = env.DASHBOARD_PASSWORD;
// Named logins: DASHBOARD_USERS="ben:pass,lorenz:pass". Falls back to the single
// DASHBOARD_PASSWORD (username optional) when unset.
const USERS = new Map(
  (env.DASHBOARD_USERS || '').split(',').map((p) => p.trim()).filter(Boolean)
    .map((pair) => { const i = pair.indexOf(':'); return [pair.slice(0, i).trim().toLowerCase(), pair.slice(i + 1)]; })
    .filter(([u, p]) => u && p)
);
const SECRET = env.SESSION_SECRET || crypto.randomBytes(32).toString('hex');
const SECURE_COOKIE = env.COOKIE_SECURE === '1';
const WORKDIR = env.WORKDIR || os.homedir();
const SKILLS_DIR = env.SKILLS_DIR || path.join(root, 'skills');
const UPLOAD_DIR = env.UPLOAD_DIR || path.join(root, 'uploads');
const CLAUDE_CMD = env.CLAUDE_CMD || 'claude';
const MAX_PANES = Number(env.MAX_PANES || 12);
const SCROLLBACK_BYTES = 200_000;
const SESSION_TTL_MS = 7 * 24 * 3600 * 1000;

// Local testing only: no login, and the server binds to 127.0.0.1 so nothing else can reach it.
const NO_AUTH = env.AUTH_DISABLED === '1';
if (!PASSWORD && !USERS.size && !NO_AUTH) {
  console.error('Set DASHBOARD_USERS or DASHBOARD_PASSWORD. This dashboard exposes a shell; it will not start without a login.');
  process.exit(1);
}
fs.mkdirSync(UPLOAD_DIR, { recursive: true });

// ---------- auth ----------
const sign = (v) => crypto.createHmac('sha256', SECRET).update(v).digest('base64url');
const safeEq = (a, b) => {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
};
const makeToken = (user = '') => {
  const exp = String(Date.now() + SESSION_TTL_MS);
  const u = Buffer.from(user).toString('base64url');
  return `${exp}.${u}.${sign(exp + '.' + u)}`;
};
// returns the username (string, may be '') if valid, else false
const validToken = (t) => {
  if (!t) return false;
  const [exp, u, sig] = t.split('.');
  if (!exp || u === undefined || !sig || !safeEq(sig, sign(exp + '.' + u))) return false;
  if (Number(exp) <= Date.now()) return false;
  try { return Buffer.from(u, 'base64url').toString() || ''; } catch { return ''; }
};
// checks credentials; returns the resolved username or null
const checkLogin = (username, password) => {
  const u = String(username || '').trim().toLowerCase();
  if (USERS.size) {
    const stored = USERS.get(u);
    return stored !== undefined && safeEq(password ?? '', stored) ? u : null;
  }
  // single-password mode: username optional, any value allowed
  return PASSWORD && safeEq(password ?? '', PASSWORD) ? (u || 'user') : null;
};
const parseCookies = (h = '') =>
  Object.fromEntries(h.split(';').map((c) => c.trim().split(/=(.*)/s).slice(0, 2)).filter(([k]) => k));
const authUser = (req) => {
  if (NO_AUTH) return 'local';
  return validToken(parseCookies(req.headers.cookie).gf_session);
};
const authed = (req) => authUser(req) !== false;

const fails = new Map(); // ip -> {n, until}
const clientIp = (req) => req.headers['x-forwarded-for']?.split(',')[0].trim() || req.socket.remoteAddress;

// ---------- terminals ----------
/** @type {Map<string, {id:string,title:string,kind:string,proc:any,buf:string,clients:Set<any>,created:number,exited:boolean}>} */
const terms = new Map();

function childEnv() {
  const e = { ...env, TERM: 'xterm-256color', COLORTERM: 'truecolor' };
  // our own secrets never reach a terminal
  for (const k of ['DASHBOARD_PASSWORD', 'DASHBOARD_USERS', 'SESSION_SECRET', 'AUTH_DISABLED', 'COOKIE_SECURE']) delete e[k];
  // metrics tokens (GHL_DEMO_TOKEN, GHL_<GYM>_TOKEN) stay server-side, never in a terminal
  for (const k of Object.keys(e)) if (/^GHL_.*_TOKEN$/.test(k)) delete e[k];
  // strip the Claude Code runtime vars of the server's own parent session, so a
  // spawned `claude` starts fresh instead of thinking it's a nested child session.
  for (const k of Object.keys(e)) {
    if (k.startsWith('CLAUDE_CODE_') || k === 'CLAUDECODE' || k === 'CLAUDE_PID' ||
        k === 'CLAUDE_EFFORT' || k === 'AI_AGENT') delete e[k];
  }
  // account/login the terminals' `claude` should use. CLAUDE_CONFIG_DIR is the "gf alias":
  // /home/lorenz/.config/claude-accounts/gf-account. Override with CLAUDE_CONFIG_DIR in .env.
  if (env.CLAUDE_CONFIG_DIR) e.CLAUDE_CONFIG_DIR = env.CLAUDE_CONFIG_DIR;
  return e;
}

function spawnTerm({ kind, title, file, args, cwd }) {
  if (terms.size >= MAX_PANES) throw new Error(`Pane limit reached (${MAX_PANES}). Close one first.`);
  const id = crypto.randomBytes(6).toString('hex');
  const proc = pty.spawn(file, args, {
    name: 'xterm-256color', cols: 120, rows: 32,
    cwd: cwd && fs.existsSync(cwd) ? cwd : WORKDIR, env: childEnv(),
  });
  const t = { id, title, kind, proc, buf: '', clients: new Set(), created: Date.now(), exited: false };
  proc.onData((d) => {
    t.buf = (t.buf + d).slice(-SCROLLBACK_BYTES);
    for (const ws of t.clients) if (ws.readyState === 1) ws.send(d);
  });
  proc.onExit(({ exitCode }) => {
    t.exited = true;
    const msg = `\r\n\x1b[2m[process exited ${exitCode}]\x1b[0m\r\n`;
    t.buf += msg;
    for (const ws of t.clients) if (ws.readyState === 1) ws.send(msg);
  });
  terms.set(id, t);
  return t;
}
const describe = (t) => ({ id: t.id, title: t.title, kind: t.kind, exited: t.exited, created: t.created });

// ---------- http ----------
const app = express();
app.disable('x-powered-by');
app.set('trust proxy', true);
app.use((req, res, next) => {
  res.set({ 'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'same-origin' });
  next();
});
app.use(express.json({ limit: '256kb' }));

app.post('/api/login', (req, res) => {
  const ip = clientIp(req);
  const f = fails.get(ip);
  if (f && f.n >= 5 && f.until > Date.now()) return res.status(429).json({ error: 'Too many attempts. Try again in a few minutes.' });
  const user = checkLogin(req.body?.username, req.body?.password);
  if (!user) {
    fails.set(ip, { n: (f && f.until > Date.now() ? f.n : 0) + 1, until: Date.now() + 15 * 60 * 1000 });
    return res.status(401).json({ error: USERS.size ? 'Wrong username or password.' : 'Wrong password.' });
  }
  fails.delete(ip);
  res.cookie('gf_session', makeToken(user), {
    httpOnly: true, sameSite: 'strict', secure: SECURE_COOKIE, maxAge: SESSION_TTL_MS, path: '/',
  });
  res.json({ ok: true, user });
});
app.post('/api/logout', (_req, res) => { res.clearCookie('gf_session', { path: '/' }); res.json({ ok: true }); });

// login page + assets are public; everything else needs a session
app.get('/login', (_req, res) => res.sendFile(path.join(root, 'public', 'login.html')));
app.get('/app.css', (_req, res) => res.sendFile(path.join(root, 'public', 'app.css')));
app.get('/favicon.ico', (_req, res) => res.status(204).end());
app.use((req, res, next) => {
  if (authed(req)) return next();
  if (req.path.startsWith('/api/')) return res.status(401).json({ error: 'unauthorized' });
  res.redirect('/login');
});

app.get('/api/me', (req, res) => res.json({ ok: true, user: authUser(req) || 'user', multiuser: USERS.size > 0 }));
app.get('/api/config', (_req, res) => res.json({ workdir: WORKDIR, maxPanes: MAX_PANES }));

// project folders the terminals can start in (immediate subdirs of WORKDIR, plus WORKDIR itself)
app.get('/api/dirs', (_req, res) => {
  let subs = [];
  try {
    subs = fs.readdirSync(WORKDIR, { withFileTypes: true })
      .filter((d) => d.isDirectory() && !d.name.startsWith('.') && d.name !== 'node_modules')
      .map((d) => d.name).sort();
  } catch {}
  res.json({ workdir: WORKDIR, dirs: subs });
});

function resolveCwd(cwd) {
  if (!cwd) return WORKDIR;
  const base = path.resolve(WORKDIR);
  const p = path.resolve(base, cwd);
  return (p === base || p.startsWith(base + path.sep)) && fs.existsSync(p) ? p : WORKDIR;
}

app.get('/api/skills', (_req, res) => {
  const { categories, skills } = loadSkills(SKILLS_DIR);
  res.json({ categories, skills: skills.map(({ prompt, cwd, ...s }) => s) });
});

app.get('/api/metrics', async (_req, res) => {
  try { res.json({ businesses: await getMetrics(root) }); }
  catch (e) { res.status(500).json({ error: 'metrics unavailable' }); }
});
app.get('/api/terminals', (_req, res) => res.json([...terms.values()].map(describe)));
app.post('/api/terminals', (req, res) => {
  const { kind = 'shell', skill, input = '', attachments = [], cwd: reqCwd } = req.body ?? {};
  const pickedCwd = resolveCwd(reqCwd);
  const suffix = pickedCwd !== WORKDIR ? ` · ${path.basename(pickedCwd)}` : '';
  try {
    let spec;
    if (kind === 'shell') {
      spec = { kind, title: `Shell${suffix}`, file: env.SHELL || '/bin/bash', args: [], cwd: pickedCwd };
    } else if (kind === 'claude') {
      spec = { kind, title: `Claude${suffix}`, file: CLAUDE_CMD, args: [], cwd: pickedCwd };
    } else if (kind === 'skill') {
      const s = loadSkills(SKILLS_DIR).skills.find((x) => x.slug === skill);
      if (!s) return res.status(404).json({ error: 'Unknown skill' });
      const files = (Array.isArray(attachments) ? attachments : [])
        .map(String).filter((p) => path.resolve(p).startsWith(path.resolve(UPLOAD_DIR) + path.sep));
      let prompt = s.prompt;
      if (String(input).trim()) prompt += `\n\n---\nRequest from the user:\n${String(input).trim()}`;
      if (files.length) prompt += `\n\nAttached files (read them as needed):\n${files.map((f) => `- ${f}`).join('\n')}`;
      // argv, not a shell string: no injection through prompt text
      spec = { kind, title: s.title, file: CLAUDE_CMD, args: [prompt], cwd: s.cwd ? resolveCwd(s.cwd) : pickedCwd };
    } else {
      return res.status(400).json({ error: 'Unknown kind' });
    }
    res.json(describe(spawnTerm(spec)));
  } catch (e) {
    res.status(e.message.startsWith('Pane limit') ? 429 : 500).json({ error: e.message });
  }
});
app.delete('/api/terminals/:id', (req, res) => {
  const t = terms.get(req.params.id);
  if (!t) return res.status(404).json({ error: 'not found' });
  try { t.proc.kill(); } catch {}
  for (const ws of t.clients) ws.close();
  terms.delete(t.id);
  res.json({ ok: true });
});

const upload = multer({
  limits: { fileSize: 25 * 1024 * 1024, files: 10 },
  storage: multer.diskStorage({
    destination: (_r, _f, cb) => {
      const d = path.join(UPLOAD_DIR, new Date().toISOString().slice(0, 10));
      fs.mkdirSync(d, { recursive: true });
      cb(null, d);
    },
    filename: (_r, f, cb) => {
      const base = path.basename(f.originalname).replace(/[^\w.\-]+/g, '_').slice(-80) || 'file';
      cb(null, `${Date.now().toString(36)}-${base}`);
    },
  }),
});
app.post('/api/upload', upload.array('files', 10), (req, res) =>
  res.json({ files: (req.files ?? []).map((f) => ({ name: f.originalname, path: path.resolve(f.path), size: f.size })) }));

app.use('/vendor/xterm', express.static(path.join(root, 'node_modules/@xterm/xterm')));
app.use('/vendor/xterm-fit', express.static(path.join(root, 'node_modules/@xterm/addon-fit')));
app.use(express.static(path.join(root, 'public'), { index: 'index.html' }));

app.use((err, _req, res, _next) => {
  res.status(err.code === 'LIMIT_FILE_SIZE' ? 413 : 500).json({ error: err.message });
});

// ---------- websocket ----------
const server = http.createServer(app);
const wss = new WebSocketServer({ noServer: true });

server.on('upgrade', (req, socket, head) => {
  const m = req.url?.match(/^\/ws\/term\/([a-f0-9]+)/);
  const origin = req.headers.origin;
  const sameOrigin = !origin || new URL(origin).host === req.headers.host;
  const t = m && terms.get(m[1]);
  if (!authed(req) || !sameOrigin || !t) {
    socket.write('HTTP/1.1 403 Forbidden\r\n\r\n');
    return socket.destroy();
  }
  wss.handleUpgrade(req, socket, head, (ws) => {
    t.clients.add(ws);
    if (t.buf) ws.send(t.buf); // replay scrollback so a refresh picks up where it left off
    ws.on('message', (raw, isBinary) => {
      if (isBinary) return;
      let msg;
      try { msg = JSON.parse(raw.toString()); } catch { return; }
      if (msg.t === 'in' && typeof msg.d === 'string' && !t.exited) t.proc.write(msg.d);
      else if (msg.t === 'resize' && !t.exited) {
        const cols = Math.max(20, Math.min(400, msg.cols | 0));
        const rows = Math.max(5, Math.min(200, msg.rows | 0));
        try { t.proc.resize(cols, rows); } catch {}
      }
    });
    ws.on('close', () => t.clients.delete(ws));
  });
});

server.listen(PORT, NO_AUTH ? '127.0.0.1' : undefined, () => console.log(`GF dashboard on :${PORT} ${NO_AUTH ? '[AUTH DISABLED, localhost only] ' : ''}(workdir ${WORKDIR}, skills ${SKILLS_DIR})`));
const shutdown = () => { for (const t of terms.values()) try { t.proc.kill(); } catch {} process.exit(0); };
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
