---
title: Score + enrich an inbound lead
category: Outreach
description: Research a new inbound lead, score fit/intent, and enrich the GHL record so sales can prioritize.
tags: sales, scoring, research, ghl
input: The lead (name / company / email / phone) and the pipeline or offer it came in on.
---
Help sales prioritize by turning a raw inbound lead into a scored, enriched record. Research first, score second, and always surface *why*.

## Steps
1. **Research** the lead and their business from public evidence: website, reviews, socials, recent news, size/location. Note anything that signals real intent (filled a form, booked a call, replied, visited pricing).
2. **Score** on two axes — **fit** (matches the ideal customer for this offer) and **intent** (how hot the signal is) — and give a short, concrete explanation for each. Store the explanation, not just the number; a stale low score should be re-checked against fresh evidence before it's trusted.
3. **Enrich the GHL record** (read-only lookups via the GHL CLI to confirm what exists) and prepare the fields/notes/tags sales needs — but **do not write to GHL** unless the user explicitly approves the specific update, and never touch live member/contact data without the OK.
4. **Output** a one-screen brief: score + reasons, the best hook/angle, suggested next action, and any enrichment to add to the record (as a proposed change, not an auto-applied one).

## Rules
- GHL access is **read-only (GET)** by default; any write is a separate, explicitly-approved action. See the GHL CLI + "test contacts only" rules.
- Base the score on real evidence and show it. Flag low-confidence calls instead of guessing.
- A model score is a prioritization aid, not a decision — keep a human in the loop for anything that affects a real contact.
