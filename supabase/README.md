# Growth Factor — Supabase (central data + agent logging)

One database for lead / campaign / reply history and agent operations, so later
optimization uses real results instead of guesses. This folder is **infra-as-code**:
`schema.sql` is the source of truth. No secrets live here.

## Tables
| Table | Purpose |
|---|---|
| `leads` | central lead store (fit/intent scores, personalization hook, enrichment JSON, dedupe key) |
| `campaigns` | outreach campaigns (channel, offer, status) |
| `campaign_leads` | which leads are in which campaign + per-lead send status |
| `lead_events` | every outreach / open / click / reply / booking / note (the history) |
| `agent_runs` | log of agent + skill operations (agent, action, status, cost, timing, error) |
| `enrichment_cache` | pay-once cache keyed by domain/email so paid lookups don't repeat |

## Apply it
You need a Supabase project first (create one at supabase.com — this is the part that
needs your account; the schema here is ready to run the moment you have it).

```bash
# Option A — Supabase SQL editor: paste schema.sql and run.
# Option B — psql:
psql "$DATABASE_URL" -f supabase/schema.sql
# Option C — Supabase CLI (schema as a migration):
#   cp schema.sql supabase/migrations/0001_init.sql && supabase db push
```

`schema.sql` is idempotent — safe to re-run after edits.

## Connecting from the app (later)
Set these as env vars (**never commit them** — use `.env` locally, Doppler in prod):

```
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service role key>   # server-side ONLY
```

- Use the **service role** key **only on the server** (it bypasses RLS). Never ship it to the browser.
- RLS is enabled on every table with **no policies**, so anon/authenticated roles get zero
  access by default — exactly what we want for server-only data. If you ever expose rows to
  logged-in users, add scoped policies (there's a commented example in `schema.sql`) and
  **test them** — a successful login does not prove data isolation.

## How the skills use it
- `lead-enrichment` / `sales-lead-score` → write/read `leads` + `enrichment_cache` (cache hits avoid paid re-lookups).
- cold-email / reactivation campaigns → `campaigns`, `campaign_leads`, `lead_events`.
- Hermes + dashboard skill sessions → write `agent_runs` so operations are auditable.

See the `leadgenjay-training` notes for the principles behind this (centralize data,
control enrichment cost, maintain agents as monitored software).
