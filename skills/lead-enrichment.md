---
title: Lead enrichment + verify
category: Outreach
description: Qualify a lead list against the offer, enrich with real evidence, run an email waterfall, validate and dedupe — ready to send.
tags: leads, enrichment, waterfall, verify
input: The raw lead list (CSV/paste) + the offer / ideal-customer definition.
---
Turn a raw lead list into a clean, qualified, send-ready list. Work in stages and keep cost down — run paid lookups conditionally, only when a cheaper check fails.

## Steps
1. **Qualify fit first.** Before enriching anything, check each company against the offer / ICP (industry, size, location, buying signals). Drop records that don't fit — this is the biggest cost saver.
2. **Enrich from real evidence.** Pull signals that make personalization real: recent news, reviews, hiring posts, tech stack, site content. Capture a specific hook per lead — never a generic "love what you're doing."
3. **Email waterfall.** Find a work email by trying sources in sequence and **stopping at the first usable address** (don't pay every provider for every row). Then validate (syntax, MX, deliverability/bounce risk).
4. **Dedupe + clean.** Remove duplicates (by domain + person), drop role/catch-all addresses if the campaign needs personal inboxes, normalize fields.
5. **Output.** A clean table (CSV) with: name, company, email, fit reason, personalization hook, and a pass/fail flag. Only rows that pass every gate go to the sender. Report counts at each stage (in → qualified → enriched → valid email → deduped) and the cost if any paid lookups ran.

## Rules
- **Never test or send against real members/contacts.** This produces a *list*, not a send — hand off to the campaign skill for drafting, and sending is always a separate, explicitly-approved step. See the "test contacts only" rule.
- Measure cost per stage; prefer free/cheap checks first and only escalate to paid enrichment for rows that survive qualification.
- Don't invent evidence. If there's no real hook for a lead, mark it and let the user decide — a fake personalization is worse than none.
