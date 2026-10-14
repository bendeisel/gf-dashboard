// Server-side session store. Replaces the old stateless HMAC token so sessions can be
// revoked (sign-out, sign-out-everywhere) and expire on inactivity, not just on an
// absolute clock. The cookie carries only an opaque random id; all state lives here.
//
// In-memory on purpose: nothing sensitive is written to disk, and a server restart
// simply forces a fresh login. Tune with SESSION_IDLE_MS / SESSION_MAX_MS.
import crypto from 'node:crypto';

const IDLE_MS = Number(process.env.SESSION_IDLE_MS || 8 * 3600 * 1000);      // 8h of inactivity
const ABS_MS = Number(process.env.SESSION_MAX_MS || 7 * 24 * 3600 * 1000);   // 7d hard cap

const store = new Map(); // sid -> { user, created, seen, ip }

export function createSession(user, ip = '') {
  const sid = crypto.randomBytes(32).toString('base64url');
  store.set(sid, { user, created: Date.now(), seen: Date.now(), ip });
  return sid;
}

// Returns the session (and slides the idle window) or null if missing/expired.
export function getSession(sid) {
  const s = sid && store.get(sid);
  if (!s) return null;
  const now = Date.now();
  if (now - s.created > ABS_MS || now - s.seen > IDLE_MS) { store.delete(sid); return null; }
  s.seen = now;
  return s;
}

export function revoke(sid) { if (sid) store.delete(sid); }

// "Sign out everywhere" for one user (e.g. after a password change or suspected leak).
export function revokeUser(user) {
  let n = 0;
  for (const [k, v] of store) if (v.user === user) { store.delete(k); n++; }
  return n;
}

// Opportunistic sweep so the map can't grow without bound.
setInterval(() => {
  const now = Date.now();
  for (const [k, s] of store) if (now - s.created > ABS_MS || now - s.seen > IDLE_MS) store.delete(k);
}, 3600 * 1000).unref?.();
