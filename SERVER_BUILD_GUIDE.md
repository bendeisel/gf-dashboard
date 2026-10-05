# GF Dashboard — Server Build & Deploy Guide

**For: a Claude Code session running on the Growth Factor VPS (or a human).**
Goal: get `dashboard.growth-factor.ai` live — a web UI that runs Claude Code and shell
sessions in the browser, a Skills library, GHL CLI access, and per-gym Metrics.

This guide is self-contained. Read it top to bottom before running anything. Confirm the
plan before any step that writes to DNS, the server, or a live GHL account.

---

## 0. What this is

A small Node server (`server/index.js`, Express + `node-pty` + `ws`) that:
- spawns **real PTYs** (shells and `claude` sessions) and streams them to `xterm.js` in the browser over WebSocket;
- keeps sessions alive across page refresh (scrollback is replayed on reconnect);
- serves a **Skills** library — Markdown files in `skills/` that each launch a `claude` session preloaded with a task prompt;
- lets you pick which **project folder** a session starts in;
- (to build) shows **Metrics** per business from the GHL API.

Frontend is plain HTML/CSS/JS — **no build step**. Design matches Ben's "Lead Gen Ben AI
Vault" artifact: dark sidebar `#0C0A09`, ivory content `#F5F1EA`, orange→gold accent
`#E66B3A`→`#D4A93A`, fonts Bricolage Grotesque (display) + Manrope (UI) + JetBrains Mono (terminal).

The code is already written and tested locally. On the server your job is mostly: **deploy
it, wire the gf Claude account and GHL tokens, and build the Metrics backend (section 7).**

---

## 1. Repo layout

```
dashboard/
  server/
    index.js        # HTTP + WS server, auth, PTY manager, uploads, dirs, (metrics TODO)
    skills.js       # parses skills/*.md into the catalog
  public/
    index.html      # app shell (sidebar, terminals, skills, ghl, metrics views)
    app.js          # all frontend logic (terminals, skills modal, folder picker, routing)
    app.css         # the whole design system
    login.html      # password page
  skills/           # one .md per task card (see section 5). Hot-read; no restart needed.
  Dockerfile        # node:20 + python + build tools + installs @anthropic-ai/claude-code
  docker-compose.yml
  deploy/Caddyfile  # reverse proxy + auto HTTPS for dashboard.growth-factor.ai
  .env.example      # DASHBOARD_PASSWORD, SESSION_SECRET
  README.md         # short operator readme
  SERVER_BUILD_GUIDE.md  # this file
```

## 2. How it runs

**Env vars the server reads** (all optional except the password):
- `DASHBOARD_PASSWORD` — **required** (unless `AUTH_DISABLED=1`). Login password.
- `SESSION_SECRET` — HMAC key for login cookies. `openssl rand -hex 32`. Auto-generated if unset (sessions drop on restart).
- `PORT` — default `3100`.
- `WORKDIR` — where terminals start and the folder picker lists from. Docker: `/workspace`.
- `SKILLS_DIR` — default `./skills`.
- `UPLOAD_DIR` — where pasted/attached files land. Docker: `/uploads`.
- `CLAUDE_CMD` — the Claude binary, default `claude`.
- `CLAUDE_CONFIG_DIR` — **the gf Claude account** (see section 3).
- `GHL_CLI_DIR` — path to the gohighlevel-cli skill, exposed to skills as `$GHL_CLI_DIR`.
- `MAX_PANES` — default `12`.
- `COOKIE_SECURE=1` — set in production (cookies only over HTTPS).
- `AUTH_DISABLED=1` — **local testing only**: skips login and binds to `127.0.0.1`. Never in production.

**Local run:** `npm install && DASHBOARD_PASSWORD=pick npm start` → http://localhost:3100

## 3. The gf Claude account ("gf alias")

The terminals' `claude` must log in as the **Growth Factor** account. That account is a
`CLAUDE_CONFIG_DIR`:

- On Lorenz's machine: `/home/lorenz/.config/claude-accounts/gf-account` (this is the "gf alias").
- The server passes `CLAUDE_CONFIG_DIR` into every spawned `claude`, and **strips its own
  parent Claude Code runtime vars** (`CLAUDECODE`, `CLAUDE_CODE_*`, `CLAUDE_PID`,
  `CLAUDE_EFFORT`, `AI_AGENT`) so each spawned `claude` starts clean, not as a nested child.

**On the server** (two options):
1. You said Claude Code is already installed and logged in on the server. Find its config dir
   (default `~/.claude`, or wherever you logged in) and point `CLAUDE_CONFIG_DIR` at it. In
   Docker, mount that dir to `/home/gf/.config/claude-gf` and set
   `CLAUDE_CONFIG_DIR=/home/gf/.config/claude-gf` (already wired in `docker-compose.yml`).
2. Or `docker exec -it gf-dashboard claude` once and sign in; the login persists in the mounted volume.

The OAuth token auto-refreshes, so a one-time login is enough. **Never commit or publish the
token** (`.credentials.json`). It's a full login.

## 4. Terminals — behavior to preserve

- Sessions live in server memory (`terms` Map). A **server restart ends running PTYs** (the
  Claude login and files survive). If you want sessions to survive restarts, back each PTY
  with `tmux`/`dtach` — optional, not done yet.
- WebSocket auth: the session cookie **and** a same-origin `Origin` header are both required.
- Paste or drag a file onto a pane → it uploads to `UPLOAD_DIR` and the server path is typed
  into the terminal for `claude` to read. (xterm can't show the image inline; the path is the handoff.)
- Shift+Enter sends `ESC+CR` (newline without submitting), matching the Claude CLI.
- Folder picker: `GET /api/dirs` lists immediate subdirs of `WORKDIR`; new sessions pass `cwd`
  (validated to stay inside `WORKDIR` — traversal is rejected).

## 5. Skills — how to add tasks

Drop a file in `skills/<slug>.md`. No rebuild/restart (re-read each request). Format:

```
---
title: Build a Google Ad
category: Ads
description: One line shown on the card
tags: google, ads
cwd: /workspace/some-repo        # optional; else uses the folder picked in the UI
input: Placeholder for the prompt box
---
The first message Claude receives. Put the rules, guardrails and tool references here.
```

The body is passed to `claude` **as an argv argument**, not through a shell — so quotes and
special characters in user input are safe (no injection). User input and attached file paths
are appended under `---` headers.

Current 12 skills: brand-research-seo, facebook-ad, ghl-audit-delete, ghl-build-account,
ghl-reactivation-agent, ghost-text-email, google-ad, n8n-flow, review-request-agent,
social-recreate-video, website-build, website-deploy. Keep the house rules in every GHL/n8n
skill: **drafts only, never send/publish; SMS-only where relevant; never touch live contacts;
build in Demo and ship via Snapshot.**

## 5b. GHL CLI setup notes (learned in deploy)

- The CLI now lives **in this repo** at `ghl-cli/` (no separate clone). It ships source
  only; build its venv **inside the container**: `docker exec gf-dashboard sh -lc 'cd /opt/ghl-cli && bash install.sh'`.
- `ghl-cli` must be owned by UID 1001 on the host so the container can write `.venv`
  (`update.sh` chowns it).
- Profiles mount: `./ghl-profiles` → `/home/gf/.config/ghl`, and the CLI expects
  **`profiles/<name>.env` plus a `config`** inside it, i.e.
  `ghl-profiles/config` (`default_profile=demo`) and `ghl-profiles/profiles/demo.env`.

## 6. GHL CLI

Mount the `gohighlevel-cli` skill folder to `/opt/ghl-cli` and the profiles
(`~/.config/ghl/profiles/*.env` + `config`) to `/home/gf/.config/ghl`. Set
`GHL_CLI_DIR=/opt/ghl-cli`. Skills run `./ghl ...` from there (zsh/bash: pass args as
separate words, not a quoted string). Default profile `demo` = Demo Account
`<DEMO_LOCATION_ID>` with a **location PIT** + an **agency PIT**.

## 7. Metrics — TO BUILD (design is ready)

**Decision (Ben/Lorenz): pull live numbers per gym from GHL.**

**Hard constraint discovered:** the **agency** PIT can list SaaS sub-accounts
(`ghl saas locations --company-id <AGENCY_COMPANY_ID>`) but **cannot read a sub-account's
contacts** — the API returns `403 token does not have access to this location`. So **each gym
needs its own location-level Private Integration Token (PIT)**, generated inside that gym's
GHL: Settings → Private Integrations → create a token with contacts + opportunities read scopes.

**Sub-account location IDs** — the real values are NOT in this public repo. They arrive
with the secrets (separate channel), and belong only in the gitignored `metrics.config.json`
(copy `metrics.config.example.json`) or in env. Placeholders below:
| Business | locationId | token (needed) |
|---|---|---|
| Growth Factor / Demo | `<DEMO_LOCATION_ID>` | have it (demo profile `GHL_API_KEY`) |
| Furst Place MMA | `<FPMMA_LOCATION_ID>` | **need gym PIT** |
| Fighters Boxing Gym | `<FIGHTERS_LOCATION_ID>` | **need gym PIT** |
| Nashville MMA Training Camp | `<NMMA_LOCATION_ID>` | **need gym PIT** |

**The GHL v2 REST API works directly (verified).** Base `https://services.leadconnectorhq.com`,
headers `Authorization: Bearer <PIT>` and `Version: 2021-07-28`. Useful calls:
- Contacts total: `GET /contacts/?locationId=<id>&limit=1` → `meta.total`.
- Opportunities total: `GET /opportunities/search?location_id=<id>&limit=1` → `meta.total`.
  Add `&status=open|won|lost` for a breakdown, `&pipeline_stage_id=<id>` for a stage.
- Pipelines + stages: `GET /opportunities/pipelines?locationId=<id>` → `pipelines[].stages[]`.
  (Demo has "New Leads Pipeline": New Lead, Hot Lead, Appt Set, Appt Past, No Show/Cancelled,
  Rescheduling; and a "Reactivation Pipeline".)

**Build this:**
1. `metrics.config.json` (gitignored; example in `metrics.config.example.json`):
   ```json
   {
     "apiBase": "https://services.leadconnectorhq.com",
     "businesses": [
       { "key": "demo",  "name": "Growth Factor (Demo)", "locationId": "<DEMO_LOCATION_ID>", "tokenEnv": "GHL_DEMO_TOKEN" },
       { "key": "fpmma", "name": "Furst Place MMA",       "locationId": "<FPMMA_LOCATION_ID>", "tokenEnv": "GHL_FPMMA_TOKEN" },
       { "key": "fighters","name": "Fighters Boxing Gym", "locationId": "<FIGHTERS_LOCATION_ID>", "tokenEnv": "GHL_FIGHTERS_TOKEN" },
       { "key": "nmma",  "name": "Nashville MMA",          "locationId": "<NMMA_LOCATION_ID>", "tokenEnv": "GHL_NMMA_TOKEN" }
     ]
   }
   ```
   Tokens come from **env vars** named by `tokenEnv` (never inline in a committed file).
2. `server/metrics.js`: for each business whose token env is set, fetch (in parallel) contacts
   total + opportunities open/won/lost. Cache per business ~5 min. No token → `{ needsToken: true }`.
   **Read-only — never POST/PUT/DELETE.**
3. `GET /api/metrics` (behind auth) returns the array of `{ key, name, tiles: [...] | needsToken }`.
4. Metrics view in `app.js`: render stat tiles per business, or an "Add API token" state.
   Follow the `dataviz` skill for the tile styling; keep the warm palette.

Wire Demo first as a live proof (its token is the demo profile `GHL_API_KEY` → set
`GHL_DEMO_TOKEN` to that value at launch). The three gym cards light up as each PIT is added.

## 8. Deploy to the VPS

1. **DNS:** add an `A` record `dashboard` on `growth-factor.ai` → the VPS IP. (Hostinger DNS.)
2. **Copy** this `dashboard/` folder to the VPS. In it:
   ```
   cp .env.example .env
   # set DASHBOARD_PASSWORD (long/random) and SESSION_SECRET (openssl rand -hex 32)
   mkdir -p workspace uploads ghl-cli ghl-profiles claude-gf
   # put the gohighlevel-cli skill in ./ghl-cli, GHL profiles in ./ghl-profiles,
   # the gf Claude account in ./claude-gf (or log in after start)
   docker compose up -d --build
   ```
3. **Claude login:** `docker exec -it gf-dashboard claude` → sign in once (if not mounted).
4. **HTTPS:** install Caddy on the host, use `deploy/Caddyfile` (auto-issues the cert).
   **If the VPS already runs a reverse proxy for n8n** (Traefik/nginx/Caddy), don't start a
   second one — add `dashboard.growth-factor.ai → 127.0.0.1:3100` to the existing proxy.
   `docker-compose.yml` binds the app to `127.0.0.1:3100` only, so it's never exposed without TLS.
5. **Docker/Hermes:** run this in its **own container** (it already is). If Hermes runs on the
   same VPS, keep it in a separate container/port — don't share.

## 8b. Mounted-dir permissions (UID 1001) — IMPORTANT

The container runs as the non-root user `gf`, which is **UID 1001**. Every
bind-mounted dir the app writes to must be owned by 1001 on the host, or you get
silent failures (uploads can't be written, `claude` can't read/refresh its creds,
the GHL CLI can't read profiles). After creating the mount dirs, run once (and
`update.sh` also does this each deploy when run as root):

```
sudo chown -R 1001:1001 claude-gf ghl-profiles workspace uploads
```

The simplest way to populate `claude-gf` correctly is to log in **inside** the
container (`docker exec -it gf-dashboard claude`) — the files are then written as
1001 automatically, no chown needed for that dir.

## 9. Security — do not regress

- A login here = a shell inside the container. Long password; login is rate-limited
  (5 fails / 15 min per IP); cookies are HttpOnly, SameSite=Strict, Secure.
- Server refuses to start without `DASHBOARD_PASSWORD` (unless `AUTH_DISABLED=1`, which also
  binds to localhost). It strips `DASHBOARD_PASSWORD`/`SESSION_SECRET` from every terminal's env.
- Container runs as **non-root** (`gf`). Do **not** mount the Docker socket or `/` into it.
- Never commit/publish: `.env`, the Claude `.credentials.json`, GHL PITs, Firebase tokens.
  These are gitignored; keep them that way.

## 10. Open tasks checklist

- [ ] DNS A record for `dashboard`.
- [ ] Deploy container; wire gf Claude account + GHL CLI mounts.
- [ ] HTTPS (Caddy or existing proxy).
- [ ] Build Metrics backend (section 7); wire Demo live.
- [ ] Get 3 gym PITs (FPMMA, Fighters, NMMA) → fill `GHL_*_TOKEN` env.
- [ ] Decide per-gym tiles (leads this month, trials, active members, past-due) → map to tags/stages.
- [ ] Optional: tmux-backed PTYs so sessions survive restarts; Hermes agent panels; per-user logins (Ben vs Lorenz).
```
