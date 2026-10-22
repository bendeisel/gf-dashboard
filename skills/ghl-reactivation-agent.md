---
title: Reactivation / win-back agent
category: GoHighLevel
description: Build the SMS reactivation + tag-triggered win-back campaign for a gym (stays draft).
tags: ghl, reactivation, sms, retention
input: Which gym/account, and the lead list or tag that triggers the win-back.
---
Use the gohighlevel-cli skill (folder `$GHL_CLI_DIR`). Build a reactivation / win-back flow for the gym I name: a tag-triggered SMS sequence under a sender avatar that texts lapsed members/old leads, sounds human and different each run, books or stops, never nags. SMS-only. Everything stays as DRAFT — never publish, never send.

**Check before refusing:** creating the workflow and any smart list uses the CLI's `--experimental` internal API — read the **Command Groups** table in SKILL.md and run `./ghl <group> --help` rather than assuming the public API's limits apply. Note any real blockers (AI Employee add-on, A2P/consent, lead list). Confirm the plan in bullets before writing. Never touch live contacts; build in Demo unless told otherwise.
