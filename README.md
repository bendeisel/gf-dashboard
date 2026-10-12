# Growth Factor Dashboard

Web UI for dashboard.growth-factor.ai. Same look as the Lead Gen vault design.

**Pages**
- **Home**: overview — at-a-glance stats, active sessions, and quick-launch into skills.
- **Terminals**: real shells and Claude sessions in the browser. Auto/1/2/3-column grid (4 panes = 2x2), maximize, close, per-pane kind badge + reconnect indicator. Sessions keep running when you refresh or close the tab. Paste or drag an image onto a pane and its server path is typed in for Claude to read.
- **Skills**: card library with a category dropdown and search. A card opens a prompt box (plus image attach) and starts a Claude session with the skill's instructions already loaded.
- **GHL CLI**: quick start for GoHighLevel work (a plain shell, plus every skill in the `GoHighLevel` category).
- **SEO / Automations / Hermes**: launcher pages — open a Claude session preloaded for the job (OpenSEO, n8n flows, Hermes builds) or jump to the n8n editor. Live in-page widgets are gated on a credential (see below).
- **Metrics**: live read-only GHL numbers per business — configurable tiles with daily-trend sparklines, status pills and refresh. See *Metrics config*.
- **Reporting**: clean, printable per-client snapshots built from the same GHL numbers.

**UI**
- Light + **dark** theme (toggle in the top bar, remembered per browser; warm-light is the default).
- **Command palette** — `⌘K` / `Ctrl-K`: jump to any page, start a Claude/shell session, or open any skill.

**Metrics config** — real location IDs live in `metrics.config.json` (gitignored; copy `metrics.config.example.json`). Each business reads its token from the env var named by `tokenEnv` (`GHL_<KEY>_TOKEN`). A business may set an optional `tiles` array to override the default (Contacts / Open / Won / Lost); all tile types are read-only GET calls — `contacts`, `opportunities` (by status), and `stage` (pipeline + stage, for trials / active / past-due). Daily snapshots for the sparklines are written to `metrics-history.json` (also gitignored).

**Phase-2 (credential-gated) live widgets** — the SEO / Automations pages work as launchers today; to light up live in-page data add `OPENSEO_TOKEN` (SEO) and/or `N8N_API_KEY` (n8n) to `.env`. Hermes panels need a spec (what to show + source).

## Adding or editing skills

Drop a `.md` file in `skills/`. No rebuild or restart needed (the folder is re-read on every request).

```
---
title: Build a Google Ad
category: Ads
description: One line for the card
tags: google, ads
cwd: /workspace/some-repo        (optional)
input: Placeholder text for the prompt box
---
The first message Claude receives. Reference tools and rules here.
```

The prompt goes to `claude` as an argument (not through a shell), so quotes and special characters in what you type are safe.

## Run locally

```
npm install
DASHBOARD_PASSWORD=pick-one npm start       # http://localhost:3100
# or, for quick local UI work with no login (binds 127.0.0.1 only):
AUTH_DISABLED=1 npm start                   # http://localhost:3100
```

## Deploy to the VPS (Docker, behind Caddy)

1. **DNS**: add an `A` record `dashboard` on growth-factor.ai pointing at the VPS IP.
2. Copy this folder to the VPS, then in it:
   ```
   cp .env.example .env     # set DASHBOARD_PASSWORD and SESSION_SECRET (openssl rand -hex 32)
   mkdir -p workspace uploads ghl-cli ghl-profiles
   docker compose up -d --build
   ```
3. **Claude account (gf alias)**: the terminals' `claude` uses the account at `CLAUDE_CONFIG_DIR`. Either copy the gf account dir (`~/.config/claude-accounts/gf-account`) into `./claude-gf` on the VPS, or run `docker exec -it gf-dashboard claude` once and sign in. The token auto-refreshes; it's stored in the mounted `./claude-gf`.
4. **GHL CLI (optional)**: copy the `gohighlevel-cli` skill folder into `./ghl-cli` and profile `.env` files into `./ghl-profiles`. Skills refer to it as `$GHL_CLI_DIR`.
5. **HTTPS**: install Caddy on the host and use `deploy/Caddyfile` (it auto-issues the certificate). If this VPS already runs Traefik/nginx for n8n, point that at `127.0.0.1:3100` instead. The compose file binds only to localhost, so the app is never reachable without TLS.

## Security notes

- Anyone who signs in gets a shell inside the container. Use a long password; sign-in is rate limited (5 failures / 15 min per IP) and cookies are HttpOnly, SameSite=Strict, Secure.
- The server refuses to start without `DASHBOARD_PASSWORD`, and strips it and `SESSION_SECRET` from the environment of every terminal.
- WebSockets require the session cookie and a same-origin `Origin` header.
- The container runs as a non-root user. Don't mount the Docker socket or `/` into it.
- Sessions live in server memory: a container restart ends running terminals (files and the Claude login survive).
- Next steps worth considering: per-user logins (Ben and Lorenz separately), Cloudflare Access in front, and Hermes agent panels.
