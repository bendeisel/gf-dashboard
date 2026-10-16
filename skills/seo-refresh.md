---
title: Refresh SEO data
category: SEO
description: Pull the latest OpenSEO numbers for every tracked project and update the dashboard's SEO page.
tags: seo, openseo, refresh, metrics
input: Leave blank to refresh every tracked project, or name one (e.g. "just Fighters").
---
You maintain the Growth Factor dashboard's **SEO snapshot** — a JSON file the dashboard reads to render its SEO page. Your job: pull fresh, read-only data from the OpenSEO MCP for each tracked project and rewrite that file.

## Where to write
Write the snapshot to the path in the `SEO_SNAPSHOT` environment variable (run `echo "$SEO_SNAPSHOT"`). If it is empty, write to `seo-snapshot.json` in the dashboard repo root. Write the file atomically (write, then confirm it parses as JSON).

## Steps
1. `list_projects` to get every OpenSEO project (id, name, domain). If the user named one, filter to it.
2. For each project, pull (read-only — these are reads, no writes, keep it to a few focused calls per project so credits stay low):
   - `get_project_context` → the goal line and competitor list.
   - `get_ranked_keywords` (projectId + target=domain, limit 12) → top keywords with positions and volumes, plus the total ranked-keyword count.
   - `get_backlinks_overview` (projectId + target=domain) → referring domains, backlinks, domain rank.
   - `list_site_audits` (projectId) → the most recent completed audit (date + pages crawled).
3. Build the snapshot in **exactly** this shape and write it:

```json
{
  "updated": <epoch ms, Date.now()>,
  "source": "OpenSEO",
  "projects": [
    {
      "id": "<projectId>",
      "name": "<name>",
      "domain": "<domain>",
      "url": "https://app.openseo.so/p/<projectId>",
      "goal": "<one line from current_goal context>",
      "tiles": [
        { "label": "Ranked keywords", "value": <totalCount> },
        { "label": "Domain rank", "value": <rank>, "lowerIsBetter": true },
        { "label": "Referring domains", "value": <referringDomains> },
        { "label": "Backlinks", "value": <backlinks> }
      ],
      "audit": { "pages": <pagesCrawled>, "when": "<YYYY-MM-DD>", "status": "done", "url": "https://app.openseo.so/p/<projectId>/audit?auditId=<id>" },
      "keywords": [ { "kw": "<keyword>", "pos": <rank_absolute>, "vol": <search_volume> } ],
      "competitors": [ { "name": "<name>", "domain": "<domain>", "note": "<short note>" } ]
    }
  ]
}
```

## Rules
- **Read-only**: only use OpenSEO *get/list* tools. Never create, delete, or run paid batch jobs (no new site audits, no AI-visibility runs) unless the user explicitly asks — those cost credits.
- Keep real values accurate; don't invent numbers. If a field is missing, omit it rather than guessing.
- When done, print a one-line summary per project (name → ranked keywords, domain rank, referring domains) and confirm the file was written and parses.
