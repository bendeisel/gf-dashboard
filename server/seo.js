// SEO snapshot reader. OpenSEO is reached via Claude's OAuth MCP (not a server REST call),
// so a Claude session refreshes seo-snapshot.json via the "SEO refresh" skill and the
// dashboard serves whatever snapshot is on disk. Read-only here.
import fs from 'node:fs';
import path from 'node:path';

export function getSeo(root) {
  const file = process.env.SEO_SNAPSHOT || path.join(root, 'seo-snapshot.json');
  try {
    const d = JSON.parse(fs.readFileSync(file, 'utf8'));
    return { configured: true, updated: d.updated || null, source: d.source || 'OpenSEO', projects: d.projects || [] };
  } catch {
    return { configured: false, projects: [] };
  }
}
