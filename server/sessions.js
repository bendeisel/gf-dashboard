// Server-side session store. Replaces the old stateless HMAC token so sessions can be
// revoked (sign-out, sign-out-everywhere) and expire on inactivity, not just on an
// absolute clock. The cookie carries only an opaque random id; all state lives here.
//
// Persisted so a redeploy / restart doesn't force everyone to log in again. Only a
// SHA-256 hash of each id is written to disk: the file alone can't forge a cookie.
// Set SESSIONS_FILE to move it, or SESSIONS_FILE= (empty) to stay memory-only.
// Tune with SESSION_IDLE_MS / SESSION_MAX_MS.
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const IDLE_MS = Number(process.env.SESSION_IDLE_MS || 8 * 3600 * 1000);      // 8h of inactivity
const ABS_MS = Number(process.env.SESSION_MAX_MS || 7 * 24 * 3600 * 1000);   // 7d hard cap
const FILE = process.env.SESSIONS_FILE === undefined
  ? path.join(os.homedir(), '.gf-dashboard-sessions.json')
  : process.env.SESSIONS_FILE; // '' disables persistence

const store = new Map(); // sha256(sid) -> { user, created, seen, ip }
const key = (sid) => crypto.createHash('sha256').update(sid).digest('base64url');
const expired = (s, now) => now - s.created > ABS_MS || now - s.seen > IDLE_MS;

// ---- persistence (debounced, atomic, 0600) ----
let saveT = null;
function save() {
  if (!FILE) return;
  clearTimeout(saveT);
  saveT = setTimeout(() => {
    try {
      const tmp = `${FILE}.tmp`;
      fs.writeFileSync(tmp, JSON.stringify([...store]), { mode: 0o600 });
      fs.renameSync(tmp, FILE);
    } catch (e) { console.warn(`[sessions] could not save ${FILE}: ${e.message}`); }
  }, 1500);
  saveT.unref?.();
}
function load() {
  if (!FILE || !fs.existsSync(FILE)) return;
  try {
    const now = Date.now();
    for (const [k, s] of JSON.parse(fs.readFileSync(FILE, 'utf8'))) if (s && !expired(s, now)) store.set(k, s);
  } catch (e) { console.warn(`[sessions] ignoring unreadable ${FILE}: ${e.message}`); }
}
load();

export function createSession(user, ip = '') {
  const sid = crypto.randomBytes(32).toString('base64url');
  store.set(key(sid), { user, created: Date.now(), seen: Date.now(), ip });
  save();
  return sid;
}

// Returns the session (and slides the idle window) or null if missing/expired.
export function getSession(sid) {
  const s = sid && store.get(key(sid));
  if (!s) return null;
  const now = Date.now();
  if (expired(s, now)) { store.delete(key(sid)); save(); return null; }
  s.seen = now;
  save();
  return s;
}

export function revoke(sid) { if (sid) { store.delete(key(sid)); save(); } }

// "Sign out everywhere" for one user (e.g. after a password change or suspected leak).
export function revokeUser(user) {
  let n = 0;
  for (const [k, v] of store) if (v.user === user) { store.delete(k); n++; }
  if (n) save();
  return n;
}

// Opportunistic sweep so the map can't grow without bound.
setInterval(() => {
  const now = Date.now();
  let n = 0;
  for (const [k, s] of store) if (expired(s, now)) { store.delete(k); n++; }
  if (n) save();
}, 3600 * 1000).unref?.();
