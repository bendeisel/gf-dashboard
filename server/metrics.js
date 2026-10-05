// Read-only GoHighLevel v2 metrics. GET requests only; tokens come from env vars named by tokenEnv.
import fs from 'node:fs';
import path from 'node:path';

const TTL_MS = 5 * 60 * 1000;
const TIMEOUT_MS = 15_000;
const cache = new Map(); // key -> { at, value }

function loadConfig(root) {
  const file = process.env.METRICS_CONFIG || path.join(root, 'metrics.config.json');
  try {
    const cfg = JSON.parse(fs.readFileSync(file, 'utf8'));
    return { apiBase: cfg.apiBase || 'https://services.leadconnectorhq.com', businesses: cfg.businesses || [] };
  } catch {
    return { apiBase: 'https://services.leadconnectorhq.com', businesses: [] };
  }
}

async function ghlGet(apiBase, token, pathname, params) {
  const url = new URL(pathname, apiBase);
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  const r = await fetch(url, {
    method: 'GET',
    headers: { Authorization: `Bearer ${token}`, Version: '2021-07-28', Accept: 'application/json' },
    signal: AbortSignal.timeout(TIMEOUT_MS),
  });
  if (!r.ok) throw new Error(r.status === 403 || r.status === 401 ? `GHL ${r.status}: token lacks access to this location` : `GHL ${r.status}`);
  return r.json();
}

async function fetchBusiness(apiBase, b, token) {
  const loc = b.locationId;
  const opp = (status) => ghlGet(apiBase, token, '/opportunities/search', { location_id: loc, limit: '1', ...(status ? { status } : {}) });
  const [contacts, open, won, lost] = await Promise.all([
    ghlGet(apiBase, token, '/contacts/', { locationId: loc, limit: '1' }),
    opp('open'), opp('won'), opp('lost'),
  ]);
  const n = (x) => Number(x?.meta?.total ?? 0);
  return [
    { label: 'Contacts', value: n(contacts) },
    { label: 'Open opportunities', value: n(open) },
    { label: 'Won', value: n(won) },
    { label: 'Lost', value: n(lost) },
  ];
}

async function one(apiBase, b) {
  const base = { key: b.key, name: b.name };
  const token = process.env[b.tokenEnv];
  if (!token || !b.locationId || b.locationId.startsWith('<')) return { ...base, needsToken: true };
  const hit = cache.get(b.key);
  if (hit && Date.now() - hit.at < TTL_MS) return hit.value;
  try {
    const value = { ...base, tiles: await fetchBusiness(apiBase, b, token), updated: Date.now() };
    cache.set(b.key, { at: Date.now(), value });
    return value;
  } catch (e) {
    return { ...base, error: String(e.message || e) };
  }
}

export async function getMetrics(root) {
  const { apiBase, businesses } = loadConfig(root);
  return Promise.all(businesses.map((b) => one(apiBase, b)));
}
