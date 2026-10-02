import fs from 'node:fs';
import path from 'node:path';

// Skill file format (skills/<anything>.md):
//   ---
//   title: Build a Google Ad
//   category: Ads
//   description: One line shown on the card
//   tags: google, ads
//   cwd: /absolute/working/dir        (optional)
//   input: What should the ad promote? (optional placeholder for the prompt box)
//   ---
//   <prompt body sent to Claude as the first message>

function parse(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?([\s\S]*)$/);
  if (!m) return null;
  const meta = {};
  for (const line of m[1].split(/\r?\n/)) {
    const i = line.indexOf(':');
    if (i > 0) meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return { meta, body: m[2].trim() };
}

export function loadSkills(dir) {
  const skills = [];
  let files = [];
  try { files = fs.readdirSync(dir).filter((f) => f.endsWith('.md')).sort(); } catch {}
  for (const f of files) {
    const p = parse(fs.readFileSync(path.join(dir, f), 'utf8'));
    if (!p?.meta.title || !p.body) continue;
    skills.push({
      slug: f.replace(/\.md$/, ''),
      title: p.meta.title,
      category: p.meta.category || 'General',
      description: p.meta.description || '',
      tags: (p.meta.tags || '').split(',').map((s) => s.trim()).filter(Boolean),
      cwd: p.meta.cwd || undefined,
      input: p.meta.input || 'Describe what you want. Claude will ask for anything it is missing.',
      prompt: p.body,
    });
  }
  const categories = [...new Set(skills.map((s) => s.category))].sort();
  // prompt text is only needed server-side; keep the list payload light
  return { categories, skills: skills.map((s) => ({ ...s })) };
}
