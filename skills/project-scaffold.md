---
title: Scaffold a client project
category: Planning
description: Set up a new project repo the GF way — CLAUDE.md context, structure, secrets hygiene, and a deploy path.
tags: scaffold, setup, claude-md, repo
input: The client / project name and what it is (website, GHL build, automation, etc.).
---
Stand up a new project so every later Claude session starts with durable context instead of a long chat. Keep it maintainable from day one.

## Steps
1. **Own directory + repo.** Create a clean project folder and (when the user wants it) a GitHub repo under the correct account — for Growth Factor work that is **bendeisel only**, confirmed with `gh api user --jq .login` before any create/push.
2. **CLAUDE.md.** Write a specific, current project CLAUDE.md: what this project is, the client, the stack, conventions, the deploy path, and the hard rules (what NOT to touch, read-only/live-data limits, drafts-stay-drafts). Keep it short and true — stale or contradictory instructions hurt later work. Add a nested CLAUDE.md per sub-area (backend/frontend) when the project is big enough.
3. **Secrets hygiene.** Add `.gitignore` for env + credential + generated files up front; commit a `.env.example` documenting every var with placeholders. Real IDs/tokens never enter the repo (especially public ones) — only placeholders in committed files.
4. **Structure + handoff.** Lay out predictable folders, drop a short README (run/build/deploy), and a handoff note capturing current state and next steps so a future session resumes cleanly.
5. **Deploy path.** Note how it ships (repo → host) and how to verify the *deployed* result in a browser, not just a local build.

## Rules
- Confirm the active GitHub account is **bendeisel** before creating or pushing anything (GF hard rule).
- No real GHL location/company IDs or tokens in committed files — placeholders only; real values in gitignored env/config.
- Prefer the smallest structure that fits; don't scaffold features the project doesn't need yet.
