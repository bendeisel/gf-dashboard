---
title: Client report deck
category: Websites
description: Build a polished single-file HTML deck or report for a client — monthly results or a pitch.
tags: reporting, presentation, deck, client
input: Client name + what to report (e.g. "Fighters — October SEO + ads results") plus any numbers, links, or screenshots.
---
Build a clean, self-contained **HTML presentation** the client can open in any browser or you can print to PDF. One file: inline CSS and JS, no build step, no external dependencies except Google Fonts.

## Structure
- A title slide (client name + what this covers + date), then one idea per slide, then a clear "what we did / what's next" close.
- Each slide is a `<div class="slide" data-slide="N">`. Support arrow-key, space, and touch-swipe navigation, a slide counter, and a thin progress bar. Keyboard/JS kept minimal and inline.
- Lead with the result that matters to the client (leads, bookings, rank, spend→return), then the supporting detail. One message per slide — don't crowd.

## Look
Match the Growth Factor brand: warm paper background, dark accents, orange→gold highlight, Bricolage Grotesque for headings + Manrope for body (Google Fonts). Generous spacing, large numbers for the headline stats, restrained color. Charts only when a number is clearer as a picture — simple inline SVG bars/lines, labeled, with the real value shown; follow sound dataviz basics (no misleading axes, color used sparingly and consistently).

## Rules
- **Use only real numbers** the user gives you (or that you pulled with their OK). Never fabricate metrics, and don't present estimates as measured results — label anything pending as "data pending."
- Keep it one file so it's easy to send. Save it to a clear path, print one screenshot or note how to open it, and summarize the slides in a line.
- Plain, confident, client-facing language — no internal jargon, no GHL/n8n plumbing unless the client asked.
