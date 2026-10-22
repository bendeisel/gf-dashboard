---
title: Build a GHL sub-account piece
category: GoHighLevel
description: Contacts, workflows, forms, calendars, funnels or smart lists via the GHL CLI.
tags: ghl, cli, build
input: What should be built, and in which account? Profiles: demo (default), nmmatc (NMMATC Memberships). Name the account you want.
---
You are working with the GoHighLevel CLI. Load and follow the gohighlevel-cli skill (its folder is `$GHL_CLI_DIR`; run `./ghl ...` from there, passing commands as separate words).

**Don't refuse from memory — check the real command surface first.** This CLI also drives GHL's *internal* API via `--experimental`, so most things the public GoHighLevel API can't do, it CAN: creating workflows, forms, surveys, funnels/landing pages, broadcast email campaigns, smart lists, and document templates. Before telling me something isn't possible, read the **Command Groups** table in the skill's SKILL.md and run `./ghl --help` (and `./ghl <group> --help`). If a write command looks missing, try it with `--experimental` before concluding it's unsupported. Only cite a limit that's in the skill's own **Known Limitations** — the real ones are: it drafts email campaigns but can't *send* them (a human sends from the UI), there's no duplicate/move command, and workflows can't be deleted via the CLI.

Accounts: profiles live in ~/.config/ghl/profiles (run `ls` there to see them; currently `demo` and `nmmatc` = NMMATC Memberships). Default to `demo`. If I name another account, run with `GHL_PROFILE=<profile>` — that profile uses our agency's own keys and is authorized, including the `--experimental` internal API (the Firebase token is set) even though it is a client sub-account. Don't refuse on that basis; if no profile exists for the account I named, tell me which key you need instead of stopping.

Rules: never test against live members/contacts (no enrolling, editing or messaging real contacts); workflows and campaigns land as DRAFTS only, never published or sent. If I ask you to copy a workflow, say plainly the copy is a rebuild (no duplicate/move command), read the source workflow first, and check that triggers and settings carried over. Confirm the plan in 3-5 bullets before running anything that writes. If anything is ambiguous, ask me.
