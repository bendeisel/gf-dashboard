---
title: Automate a browser task
category: Websites
description: Drive a headless browser to scrape data, fill or test a form, or capture screenshots / PDFs of a page.
tags: browser, scrape, qa, screenshot
input: The page URL and what to do — data to extract, a form/flow to test, or what to capture.
---
You automate a real browser to get a web task done: pull data off a page, exercise a form or booking flow, or capture a screenshot/PDF for a report. Use Playwright with headless Chromium (`npx -y playwright@latest ...`, or write a small Node/Python Playwright script and run it). Install the browser once with `npx playwright install chromium` if it is missing.

## Workflow
1. **Navigate** to the URL and wait for network idle.
2. **Snapshot** the page — list the interactive elements (inputs, buttons, links) with stable selectors before you act. Re-snapshot after every navigation or DOM change; never reuse stale selectors.
3. **Interact** using those selectors: fill, click, select, press, scroll.
4. **Verify** after each step — check the URL, a success message, or the extracted value — don't assume a step worked.
5. **Capture / extract** what was asked: structured data (save as JSON/CSV), a screenshot (`--full` for full page), or a PDF.

## Rules
- **Read-only by default.** Scraping, screenshots, and read navigation are fine. Do NOT submit a form, book, log in, or write anything on a live client/member site without the user's explicit OK for that specific action — and never against real members or contacts (use a test record or a staging page). See the "test contacts only" rule.
- Respect the site: reasonable pacing, no credential stuffing, no bypassing paywalls/auth you weren't given access to.
- Save outputs to a clear path and report where. For extracted data, show a short sample and the row count. Don't invent values — if a field is missing, say so.
- Close the browser when done.
