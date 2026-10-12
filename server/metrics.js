// Read-only GoHighLevel v2 metrics. GET requests only (never POST/PUT/DELETE);
// tokens come from env vars named by tokenEnv. Tiles are configurable per business.
import fs from 'node:fs';
import path from 'node:path';

const TTL_MS = 5 * 60 * 1000;
const TIMEOUT_MS = 15_000;
const HISTORY_DAYS = 14;
const cache = new Map(); // key -> { at, value }

function loadConfig(root) {
  const file = process.env.METRICS_CONFIG || path.join(root, 'metrics.config.json');
  const historyFile = process.env.METRICS_HISTORY || path.join(root, 'metrics-history.json');
  try {
    const cfg = JSON.parse(fs.readFileSync(file, 'utf8'));
    return { apiBase: cfg.apiBase || 'https://services.leadconnectorhq.com', businesses: cfg.businesses || [], historyFile };
  } catch {
    return { apiBase: 'https://services.leadconnectorhq.com', businesses: [], historyFile };
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

const total = (x) => Number(x?.meta?.total ?? 0);

// Tiles a business shows if it doesn't configure its own.
function defaultTiles() {
  return [
    { label: 'Contacts', type: 'contacts' },
    { label: 'Open opportunities', type: 'opportunities', status: 'open' },
    { label: 'Won', type: 'opportunities', status: 'won' },
    { label: 'Lost', type: 'opportunities', status: 'lost' },
  ];
}

// All tile types below are read-only GET calls.
//   { type: 'contacts' }                                        -> total contacts
//   { type: 'opportunities', status: 'open'|'won'|'lost' }      -> opportunities by status
//   { type: 'stage', pipelineId, stageId }                      -> opportunities in a pipeline stage
//     (use 'stage' for trials / active members / past-due when they're modeled as pipeline stages)
async function fetchTile(apiBase, token, loc, t) {
  if (t.type === 'contacts') {
    return total(await ghlGet(apiBase, token, '/contacts/', { locationId: loc, limit: '1' }));
  }
  // opportunities + stage both hit the opportunity search (GET) with different filters
  const params = { location_id: loc, limit: '1' };
  if (t.status) params.status = t.status;
  if (t.pipelineId) params.pipeline_id = t.pipelineId;
  if (t.stageId) params.pipeline_stage_id = t.stageId;
  return total(await ghlGet(apiBase, token, '/opportunities/search', params));
}

async function fetchBusiness(apiBase, b, token) {
  const loc = b.locationId;
  const tiles = Array.isArray(b.tiles) && b.tiles.length ? b.tiles : defaultTiles();
  const values = await Promise.all(tiles.map((t) => fetchTile(apiBase, token, loc, t)));
  return tiles.map((t, i) => ({ label: t.label, value: values[i] }));
}

// Best-effort daily snapshot so cards can show a sparkline. Writes to our own file only
// (never GHL); if the file isn't writable, metrics still work — just without history.
function withHistory(file, key, tiles) {
  if (!file) return tiles;
  let hist;
  try { hist = JSON.parse(fs.readFileSync(file, 'utf8')); } catch { hist = {}; }
  const today = new Date().toISOString().slice(0, 10);
  const bh = hist[key] || (hist[key] = {});
  bh[today] = Object.fromEntries(tiles.map((t) => [t.label, t.value]));
  const dates = Object.keys(bh).sort();
  while (dates.length > HISTORY_DAYS) delete bh[dates.shift()];
  try { fs.writeFileSync(file, JSON.stringify(hist)); } catch {}
  const ordered = Object.keys(bh).sort();
  return tiles.map((t) => ({
    label: t.label,
    value: t.value,
    history: ordered.map((d) => bh[d][t.label]).filter((v) => v != null),
  }));
}

async function one(apiBase, b, historyFile, bypass) {
  const base = { key: b.key, name: b.name };
  const token = process.env[b.tokenEnv];
  if (!token || !b.locationId || b.locationId.startsWith('<')) return { ...base, needsToken: true };
  const hit = cache.get(b.key);
  if (hit && !bypass && Date.now() - hit.at < TTL_MS) return hit.value;
  try {
    const tiles = withHistory(historyFile, b.key, await fetchBusiness(apiBase, b, token));
    const value = { ...base, tiles, updated: Date.now() };
    cache.set(b.key, { at: Date.now(), value });
    return value;
  } catch (e) {
    return { ...base, error: String(e.message || e) };
  }
}

export async function getMetrics(root, { fresh = false } = {}) {
  const { apiBase, businesses, historyFile } = loadConfig(root);
  return Promise.all(businesses.map((b) => one(apiBase, b, historyFile, fresh)));
}
