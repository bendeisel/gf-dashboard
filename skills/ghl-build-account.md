---
title: Build a GHL sub-account piece
category: GoHighLevel
description: Contacts, workflows, forms, calendars, funnels or smart lists via the GHL CLI.
tags: ghl, cli, build
input: What should be built, and in which account? Profiles: demo (default), nmmatc (NMMATC Memberships). Name the account you want.
---
You are working with the GoHighLevel CLI. Load and follow the gohighlevel-cli skill (its folder is in $GHL_CLI_DIR; run `./ghl ...` from there, passing commands as separate words).
Accounts: profiles live in ~/.config/ghl/profiles (run `ls` there to see them; currently `demo` and `nmmatc` = NMMATC Memberships). Default to `demo`. If I name another account, run with `GHL_PROFILE=<profile>` — that profile uses our agency's own keys and is authorized, including the --experimental internal API (the Firebase token is set) even though it is a client sub-account. Don't refuse on that basis; if no profile exists for the account I named, tell me which key you need instead of stopping.
Rules: never test against live members/contacts (no enrolling, editing or messaging real contacts); workflows and campaigns land as DRAFTS only, never published or sent. Note the CLI has no duplicate/move command — it can only create a new draft from JSON — so if I ask you to copy workflows, say plainly that the copy would be a rebuild, read the source workflow first, and check that triggers and settings carried over. Confirm the plan in 3-5 bullets before running anything that writes. If anything is ambiguous, ask me.
