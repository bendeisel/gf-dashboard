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
import { getSeo } from './seo.js';
import { transcribe, voiceConfigured } from './voice.js';
import { createSession, getSession, revoke, revokeUser } from './sessions.js';
import { sendCode, mailerConfigured } from './mailer.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const env = process.env;
// resolved SEO snapshot path, shared by getSeo() and the skill panes (via childEnv) that write it
if (!env.SEO_SNAPSHOT) env.SEO_SNAPSHOT = path.join(root, 'seo-snapshot.json');

const PORT = Number(env.PORT || 3100);
const PASSWORD = env.DASHBOARD_PASSWORD;
// Named logins: DASHBOARD_USERS="ben:pass,lorenz:pass". Falls back to the single
// DASHBOARD_PASSWORD (username optional) when unset.
const USERS = new Map(
  (env.DASHBOARD_USERS || '').split(',').map((p) => p.trim()).filter(Boolean)
    .map((pair) => { const i = pair.indexOf(':'); return [pair.slice(0, i).trim().toLowerCase(), pair.slice(i + 1)]; })
    .filter(([u, p]) => u && p)
);
const SECURE_COOKIE = env.COOKIE_SECURE === '1';
// Per-user email for the 2FA code: DASHBOARD_USER_EMAILS="ben:ben@...,lorenz:lorenz@..."
const USER_EMAILS = new Map(
  (env.DASHBOARD_USER_EMAILS || '').split(',').map((p) => p.trim()).filter(Boolean)
    .map((pair) => { const i = pair.indexOf(':'); return [pair.slice(0, i).trim().toLowerCase(), pair.slice(i + 1).trim()]; })
    .filter(([u, e]) => u && e)
);
// 2FA is enforced for a user only when we can actually email them a code.
const twofaActive = () => mailerConfigured() && USER_EMAILS.size > 0;
const userNeeds2fa = (user) => twofaActive() && USER_EMAILS.has(user);
const WORKDIR = env.WORKDIR || os.homedir();
const SKILLS_DIR = env.SKILLS_DIR || path.join(root, 'skills');
const UPLOAD_DIR = env.UPLOAD_DIR || path.join(root, 'uploads');
const CLAUDE_CMD = env.CLAUDE_CMD || 'claude';
// default model for Claude panes/skills; override with DASHBOARD_CLAUDE_MODEL
const CLAUDE_MODEL = env.DASHBOARD_CLAUDE_MODEL || 'claude-opus-5-5';
const modelArgs = CLAUDE_MODEL ? ['--model', CLAUDE_MODEL] : [];
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
const safeEq = (a, b) => {
  const ha = crypto.createHash('sha256').update(String(a)).digest();
  const hb = crypto.createHash('sha256').update(String(b)).digest();
  return crypto.timingSafeEqual(ha, hb);
};
// Verify a password against a stored value: scrypt hash (preferred) or legacy plaintext.
// Generate hashes with `node server/hash-password.js`.
const verifyPassword = (plain, stored) => {
  if (typeof stored !== 'string') return false;
  if (stored.startsWith('scrypt$')) {
    try {
      const [, saltb64, hashb64] = stored.split('$');
      const salt = Buffer.from(saltb64, 'base64');
      const expected = Buffer.from(hashb64, 'base64');
      const got = crypto.scryptSync(String(plain ?? ''), salt, expected.length);
      return got.length === expected.length && crypto.timingSafeEqual(got, expected);
    } catch { return false; }
  }
  return safeEq(plain ?? '', stored); // legacy plaintext — migrate with hash-password.js
};
// checks credentials; returns the resolved username or null
const checkLogin = (username, password) => {
  const u = String(username || '').trim().toLowerCase();
  if (USERS.size) {
    const stored = USERS.get(u);
    return stored !== undefined && verifyPassword(password, stored) ? u : null;
  }
  // single-password mode: username optional, any value allowed
  return PASSWORD && verifyPassword(password, PASSWORD) ? (u || 'user') : null;
};
const parseCookies = (h = '') =>
  Object.fromEntries(h.split(';').map((c) => c.trim().split(/=(.*)/s).slice(0, 2)).filter(([k]) => k));
const authUser = (req) => {
  if (NO_AUTH) return 'local';
  const s = getSession(parseCookies(req.headers.cookie).gf_session);
  return s ? s.user : false;
};
const authed = (req) => authUser(req) !== false;

// one-line visibility into the security posture at boot
const plaintextUsers = [...USERS.values()].some((v) => !String(v).startsWith('scrypt$'));
const log = (...a) => console.log(new Date().toISOString(), ...a);

// Brute-force throttle. `trust proxy = 1` makes req.ip the real client (Caddy's upstream),
// so it can't be spoofed via X-Forwarded-For. We key per-IP *and* per-account.
const fails = new Map(); // key -> {n, until}
const clientIp = (req) => req.ip || req.socket.remoteAddress;
const LOCK_MS = 15 * 60 * 1000, LOCK_N = 5;
const rlBlocked = (key) => { const f = fails.get(key); return !!(f && f.n >= LOCK_N && f.until > Date.now()); };
const rlFail = (key) => { const f = fails.get(key); fails.set(key, { n: (f && f.until > Date.now() ? f.n : 0) + 1, until: Date.now() + LOCK_MS }); };
const rlClear = (key) => fails.delete(key);

// Pending email-2FA challenges: pid -> { user, codeHash, exp, tries, sentAt, ip }
const pending2fa = new Map();
const hashCode = (c) => crypto.createHash('sha256').update(String(c)).digest();
const genCode = () => String(crypto.randomInt(0, 1_000_000)).padStart(6, '0');
const maskEmail = (e) => e.replace(/^(.)(.*)(.)(@.*)$/, (_, a, m, z, d) => `${a}${'*'.repeat(Math.max(1, m.length))}${z}${d}`);
setInterval(() => { const now = Date.now(); for (const [k, v] of pending2fa) if (v.exp < now) pending2fa.delete(k); }, 5 * 60 * 1000).unref?.();

// ---------- terminals ----------
/** @type {Map<string, {id:string,title:string,kind:string,proc:any,buf:string,clients:Set<any>,created:number,exited:boolean}>} */
const terms = new Map();

function childEnv() {
  const e = { ...env, TERM: 'xterm-256color', COLORTERM: 'truecolor' };
  // our own secrets never reach a terminal
  for (const k of ['DASHBOARD_PASSWORD', 'DASHBOARD_USERS', 'SESSION_SECRET', 'AUTH_DISABLED', 'COOKIE_SECURE', 'WISPR_API_KEY']) delete e[k];
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

function spawnTerm({ kind, title, file, args, cwd, owner = 'local', shared = false }) {
  if (terms.size >= MAX_PANES) throw new Error(`Pane limit reached (${MAX_PANES}). Close one first.`);
  const id = crypto.randomBytes(6).toString('hex');
  const proc = pty.spawn(file, args, {
    name: 'xterm-256color', cols: 120, rows: 32,
    cwd: cwd && fs.existsSync(cwd) ? cwd : WORKDIR, env: childEnv(),
  });
  const t = { id, title, kind, proc, buf: '', clients: new Set(), created: Date.now(), exited: false, owner, shared: !!shared };
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
const describe = (t, me) => ({ id: t.id, title: t.title, kind: t.kind, exited: t.exited, created: t.created, owner: t.owner, shared: t.shared, mine: t.owner === me });
// who may see/attach a session: its owner, or anyone if it's shared
const canView = (t, me) => t.owner === me || t.shared;

// ---------- http ----------
const app = express();
app.disable('x-powered-by');
app.set('trust proxy', 1); // exactly one hop (Caddy): req.ip is the real client, not a spoofable XFF
const CSP = [
  "default-src 'self'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'",
  "object-src 'none'", "img-src 'self' data:", "font-src 'self' https://fonts.gstatic.com",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com", "script-src 'self'", "connect-src 'self'",
].join('; ');
app.use((req, res, next) => {
  res.set({
    'X-Frame-Options': 'DENY', 'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'same-origin', 'Content-Security-Policy': CSP,
    'Permissions-Policy': 'microphone=(self), camera=(), geolocation=()', // mic for Wispr dictation
  });
  if (SECURE_COOKIE) res.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
  next();
});
const COOKIE_OPTS = { httpOnly: true, sameSite: 'strict', secure: SECURE_COOKIE, path: '/' };
// Global JSON stays tight; the voice route carries a base64 audio clip and parses its
// own larger body, so skip it here.
const jsonSmall = express.json({ limit: '256kb' });
app.use((req, res, next) => (req.path === '/api/voice/transcribe' ? next() : jsonSmall(req, res, next)));

// starts a session cookie for a verified user
function grant(res, user, ip) {
  res.cookie('gf_session', createSession(user, ip), { ...COOKIE_OPTS, maxAge: SESSION_TTL_MS });
}
async function beginChallenge(res, user, ip) {
  const email = USER_EMAILS.get(user);
  const code = genCode();
  const pid = crypto.randomBytes(18).toString('base64url');
  pending2fa.set(pid, { user, codeHash: hashCode(code), exp: Date.now() + 10 * 60 * 1000, tries: 0, sentAt: Date.now(), ip });
  try { await sendCode(email, code); }
  catch (e) { pending2fa.delete(pid); log('[login] 2fa send failed', user, e.message); return res.status(502).json({ error: 'Could not send your sign-in code. Try again shortly.' }); }
  res.cookie('gf_2fa', pid, { ...COOKIE_OPTS, maxAge: 10 * 60 * 1000 });
  log('[login] step1 ok, code sent', user, ip);
  res.json({ twofa: true, email: maskEmail(email) });
}

// Step 1: username + password. Either grants a session or starts an email-code challenge.
app.post('/api/login', async (req, res) => {
  const ip = clientIp(req);
  const uname = String(req.body?.username || '').trim().toLowerCase();
  if (rlBlocked(`ip:${ip}`) || rlBlocked(`u:${uname}`)) return res.status(429).json({ error: 'Too many attempts. Try again in a few minutes.' });
  const user = checkLogin(req.body?.username, req.body?.password);
  if (!user) {
    rlFail(`ip:${ip}`); rlFail(`u:${uname}`);
    log('[login] bad password', uname, ip);
    return res.status(401).json({ error: USERS.size ? 'Wrong username or password.' : 'Wrong password.' });
  }
  rlClear(`ip:${ip}`); rlClear(`u:${uname}`);
  if (userNeeds2fa(user)) return beginChallenge(res, user, ip);
  grant(res, user, ip);
  log('[login] ok (no 2fa configured for user)', user, ip);
  res.json({ ok: true, user });
});

// Step 2: verify the emailed code.
app.post('/api/login/verify', (req, res) => {
  const ip = clientIp(req);
  if (rlBlocked(`2fa:${ip}`)) return res.status(429).json({ error: 'Too many attempts. Try again in a few minutes.' });
  const pid = parseCookies(req.headers.cookie).gf_2fa;
  const p = pid && pending2fa.get(pid);
  if (!p || p.exp < Date.now()) { if (pid) pending2fa.delete(pid); return res.status(440).json({ error: 'Your code expired. Please sign in again.' }); }
  if (p.tries >= 5) { pending2fa.delete(pid); return res.status(429).json({ error: 'Too many wrong codes. Please sign in again.' }); }
  const code = String(req.body?.code || '').trim();
  const ok = code.length === 6 && crypto.timingSafeEqual(hashCode(code), p.codeHash);
  if (!ok) { p.tries++; rlFail(`2fa:${ip}`); log('[login] bad 2fa code', p.user, ip); return res.status(401).json({ error: 'Wrong code.' }); }
  pending2fa.delete(pid);
  res.clearCookie('gf_2fa', COOKIE_OPTS);
  grant(res, p.user, ip);
  log('[login] 2fa ok', p.user, ip);
  res.json({ ok: true, user: p.user });
});

// Resend the code for an in-flight challenge (throttled).
app.post('/api/login/resend', async (req, res) => {
  const pid = parseCookies(req.headers.cookie).gf_2fa;
  const p = pid && pending2fa.get(pid);
  if (!p || p.exp < Date.now()) return res.status(440).json({ error: 'Your code expired. Please sign in again.' });
  if (Date.now() - p.sentAt < 20 * 1000) return res.status(429).json({ error: 'Hold on a moment before requesting another code.' });
  const code = genCode();
  p.codeHash = hashCode(code); p.sentAt = Date.now(); p.exp = Date.now() + 10 * 60 * 1000;
  try { await sendCode(USER_EMAILS.get(p.user), code); } catch { return res.status(502).json({ error: 'Could not resend the code.' }); }
  res.json({ ok: true });
});

app.post('/api/logout', (req, res) => { revoke(parseCookies(req.headers.cookie).gf_session); res.clearCookie('gf_session', COOKIE_OPTS); res.json({ ok: true }); });
// sign out of every device for the current user
app.post('/api/logout-all', (req, res) => { const u = authUser(req); if (u && u !== false) revokeUser(u); res.clearCookie('gf_session', COOKIE_OPTS); res.json({ ok: true }); });

// login page + assets are public; everything else needs a session
app.get('/login', (_req, res) => res.sendFile(path.join(root, 'public', 'login.html')));
app.get('/app.css', (_req, res) => res.sendFile(path.join(root, 'public', 'app.css')));
app.get('/login.js', (_req, res) => res.type('application/javascript').sendFile(path.join(root, 'public', 'login.js')));
// brand assets used by the (public) login page
for (const f of ['logo-flame.png', 'logo-wordmark.webp', 'favicon.png', 'apple-touch-icon.png']) {
  app.get('/' + f, (_req, res) => res.sendFile(path.join(root, 'public', f)));
}
app.get('/favicon.ico', (_req, res) => res.status(204).end());
app.use((req, res, next) => {
  if (authed(req)) return next();
  if (req.path.startsWith('/api/')) return res.status(401).json({ error: 'unauthorized' });
  res.redirect('/login');
});

app.get('/api/me', (req, res) => res.json({ ok: true, user: authUser(req) || 'user', multiuser: USERS.size > 0 }));
app.get('/api/config', (_req, res) => res.json({ workdir: WORKDIR, maxPanes: MAX_PANES, voice: voiceConfigured() }));

// Voice dictation: browser posts a base64 16kHz-mono WAV; we forward to Wispr Flow and
// return the transcript. Key stays server-side (see server/voice.js). Behind the auth gate.
app.post('/api/voice/transcribe', express.json({ limit: '16mb' }), async (req, res) => {
  const { audio, language } = req.body ?? {};
  if (typeof audio !== 'string' || !audio) return res.status(400).json({ error: 'No audio.' });
  try {
    const { text } = await transcribe({ audioBase64: audio, language });
    res.json({ text });
  } catch (e) {
    if (e.code === 'NO_KEY') return res.status(503).json({ error: 'Voice isn’t set up on the server (WISPR_API_KEY missing).' });
    console.error('[voice] transcription failed:', e.message, e.status || '', e.detail || '');
    res.status(502).json({ error: 'Transcription failed — check the server logs.' });
  }
});

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

app.get('/api/metrics', async (req, res) => {
  try { res.json({ businesses: await getMetrics(root, { fresh: req.query.fresh === '1' }) }); }
  catch (e) { res.status(500).json({ error: 'metrics unavailable' }); }
});
app.get('/api/seo', (_req, res) => res.json(getSeo(root)));
app.get('/api/terminals', (req, res) => {
  const me = authUser(req);
  res.json([...terms.values()].filter((t) => canView(t, me)).map((t) => describe(t, me)));
});
app.post('/api/terminals', (req, res) => {
  const me = authUser(req);
  const { kind = 'shell', skill, input = '', attachments = [], cwd: reqCwd, shared = false } = req.body ?? {};
  const pickedCwd = resolveCwd(reqCwd);
  const suffix = pickedCwd !== WORKDIR ? ` · ${path.basename(pickedCwd)}` : '';
  try {
    let spec;
    if (kind === 'shell') {
      spec = { kind, title: `Shell${suffix}`, file: env.SHELL || '/bin/bash', args: [], cwd: pickedCwd };
    } else if (kind === 'claude') {
      spec = { kind, title: `Claude${suffix}`, file: CLAUDE_CMD, args: [...modelArgs], cwd: pickedCwd };
    } else if (kind === 'skill') {
      const s = loadSkills(SKILLS_DIR).skills.find((x) => x.slug === skill);
      if (!s) return res.status(404).json({ error: 'Unknown skill' });
      const files = (Array.isArray(attachments) ? attachments : [])
        .map(String).filter((p) => path.resolve(p).startsWith(path.resolve(UPLOAD_DIR) + path.sep));
      let prompt = s.prompt;
      if (String(input).trim()) prompt += `\n\n---\nRequest from the user:\n${String(input).trim()}`;
      if (files.length) prompt += `\n\nAttached files (read them as needed):\n${files.map((f) => `- ${f}`).join('\n')}`;
      // argv, not a shell string: no injection through prompt text
      spec = { kind, title: s.title, file: CLAUDE_CMD, args: [...modelArgs, prompt], cwd: s.cwd ? resolveCwd(s.cwd) : pickedCwd };
    } else {
      return res.status(400).json({ error: 'Unknown kind' });
    }
    const t = spawnTerm({ ...spec, owner: me, shared: !!shared });
    res.json(describe(t, me));
  } catch (e) {
    res.status(e.message.startsWith('Pane limit') ? 429 : 500).json({ error: e.message });
  }
});
// Flip a session between Personal and Shared. Owner only.
app.post('/api/terminals/:id/share', (req, res) => {
  const me = authUser(req);
  const t = terms.get(req.params.id);
  if (!t) return res.status(404).json({ error: 'not found' });
  if (t.owner !== me) return res.status(403).json({ error: 'Only the owner can change who can see this session.' });
  t.shared = !!req.body?.shared;
  res.json(describe(t, me));
});
app.delete('/api/terminals/:id', (req, res) => {
  const me = authUser(req);
  const t = terms.get(req.params.id);
  if (!t) return res.status(404).json({ error: 'not found' });
  // You can only close your own sessions — never someone else's, even a shared one.
  if (t.owner !== me) return res.status(403).json({ error: 'This session belongs to someone else — only they can close it.' });
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
  const me = authUser(req);
  // must be authed, same-origin, the session must exist, and be yours or shared
  if (me === false || !sameOrigin || !t || !canView(t, me)) {
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

server.listen(PORT, NO_AUTH ? '127.0.0.1' : undefined, () => {
  log(`GF dashboard on :${PORT} ${NO_AUTH ? '[AUTH DISABLED, localhost only] ' : ''}(workdir ${WORKDIR}, skills ${SKILLS_DIR})`);
  if (!NO_AUTH) {
    log(`[security] email 2FA ${twofaActive() ? 'ACTIVE for: ' + [...USER_EMAILS.keys()].join(', ') : 'OFF (set DASHBOARD_USER_EMAILS + a mail backend to enable)'}`);
    if (plaintextUsers) log('[security] WARNING: some DASHBOARD_USERS passwords are plaintext — hash them with `node server/hash-password.js`');
    if (!SECURE_COOKIE) log('[security] WARNING: COOKIE_SECURE is off — set COOKIE_SECURE=1 behind TLS');
  }
});
const shutdown = () => { for (const t of terms.values()) try { t.proc.kill(); } catch {} process.exit(0); };
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
