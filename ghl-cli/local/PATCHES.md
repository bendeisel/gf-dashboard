# Local patches (Growth Factor, 2026-10-01) — reapply if the skill zip is reinstalled
Originals backed up as *.orig when patched. Verified live on Demo Account + bundled 216 unit tests pass.

1. `contacts remove-tag` — never sent the tags (DELETE had no body → 422). Now sends {"tags": [...]}; `ghl_client.delete()` gained a `data=` arg.
2. `calendars slots` — sent YYYY-MM-DD + calendarId query (422). Now converts to epoch ms in the --timezone given.
3. `calendars appointments` — called nonexistent /calendars/events/appointments (401 IAM). Now GET /calendars/events per calendar, default window ±30 days.
4. `social posts` — wrong body (422). Now skip/limit as strings + fromDate/toDate ±90d.
5. Firebase token cached to ~/.cache/ghl/firebase-<profile>.json (0600, 50 min). Previously every command minted a new token → Google 429 "Token exchange per minute" on bursts.

Live test: `python3 local/live_demo_test.py` (Demo profile only; creates/deletes ZZ CLI TEST objects; leaves one draft workflow).
