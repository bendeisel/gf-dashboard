-- ============================================================
-- Growth Factor — central data + agent logging (Supabase/Postgres)
-- Training principle: keep lead / campaign / reply history and agent
-- operations in one database so later optimization uses real results.
--
-- Apply: Supabase SQL editor, or `psql "$DATABASE_URL" -f schema.sql`,
-- or drop into supabase/migrations and `supabase db push`.
-- Idempotent: safe to re-run.
-- ============================================================

create extension if not exists pgcrypto;   -- gen_random_uuid()
create extension if not exists citext;      -- case-insensitive email

-- updated_at helper -------------------------------------------------
create or replace function set_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end; $$;

-- ============================================================
-- leads — the central lead store
-- ============================================================
create table if not exists leads (
  id            uuid primary key default gen_random_uuid(),
  source        text,                       -- where it came from (scrape, form, referral…)
  full_name     text,
  company       text,
  email         citext,
  phone         text,
  domain        text,
  status        text not null default 'new',-- new|qualified|enriched|contacted|replied|booked|won|lost|disqualified
  fit_score     int  check (fit_score  between 0 and 100),
  intent_score  int  check (intent_score between 0 and 100),
  hook          text,                       -- the real personalization angle
  enrichment    jsonb not null default '{}'::jsonb,
  dedupe_key    text unique,                -- app-set, e.g. lower(domain)||'|'||lower(email)
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
create index if not exists leads_email_idx   on leads (email);
create index if not exists leads_domain_idx  on leads (domain);
create index if not exists leads_status_idx  on leads (status);
drop trigger if exists leads_set_updated on leads;
create trigger leads_set_updated before update on leads
  for each row execute function set_updated_at();

-- ============================================================
-- campaigns + membership
-- ============================================================
create table if not exists campaigns (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  channel     text not null default 'email', -- email|sms|linkedin|instagram|call
  offer       text,
  status      text not null default 'draft', -- draft|active|paused|done
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
drop trigger if exists campaigns_set_updated on campaigns;
create trigger campaigns_set_updated before update on campaigns
  for each row execute function set_updated_at();

create table if not exists campaign_leads (
  campaign_id uuid not null references campaigns(id) on delete cascade,
  lead_id     uuid not null references leads(id)     on delete cascade,
  status      text not null default 'pending',       -- pending|sent|replied|bounced|skipped
  added_at    timestamptz not null default now(),
  sent_at     timestamptz,
  primary key (campaign_id, lead_id)
);
create index if not exists campaign_leads_lead_idx on campaign_leads (lead_id);

-- ============================================================
-- lead_events — every outreach / reply / signal (the history)
-- ============================================================
create table if not exists lead_events (
  id          uuid primary key default gen_random_uuid(),
  lead_id     uuid not null references leads(id) on delete cascade,
  campaign_id uuid references campaigns(id) on delete set null,
  channel     text,                                   -- email|sms|linkedin|call|web
  direction   text check (direction in ('outbound','inbound','system')),
  event_type  text,                                   -- sent|open|click|reply|bounce|booked|note
  body        text,
  meta        jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  created_at  timestamptz not null default now()
);
create index if not exists lead_events_lead_idx on lead_events (lead_id, occurred_at desc);

-- ============================================================
-- agent_runs — log of agent / skill operations (maintain agents as software)
-- ============================================================
create table if not exists agent_runs (
  id          uuid primary key default gen_random_uuid(),
  agent       text not null,                          -- hermes|claude-code|skill:<name>
  action      text,                                   -- what it did
  status      text not null default 'running',        -- running|success|error|blocked
  session_id  text,
  summary     text,
  detail      jsonb not null default '{}'::jsonb,
  cost_usd    numeric(10,4),
  error       text,
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  created_at  timestamptz not null default now()
);
create index if not exists agent_runs_agent_idx on agent_runs (agent, started_at desc);
create index if not exists agent_runs_status_idx on agent_runs (status);

-- ============================================================
-- enrichment_cache — pay once, reuse (control enrichment cost)
-- ============================================================
create table if not exists enrichment_cache (
  key         text primary key,                       -- lower(domain) or lower(email)
  kind        text,                                   -- domain|email|company|person
  provider    text,
  data        jsonb not null default '{}'::jsonb,
  cost_usd    numeric(10,4),
  fetched_at  timestamptz not null default now(),
  expires_at  timestamptz
);
create index if not exists enrichment_cache_expires_idx on enrichment_cache (expires_at);

-- ============================================================
-- Row-Level Security
-- Enable RLS on everything. With RLS on and NO policies, the anon and
-- authenticated roles get ZERO access — only the service_role key
-- (server-side only) can read/write, which is what we want. If you ever
-- expose these to logged-in users, add scoped policies (example below).
-- Reminder: a successful login does NOT prove data isolation — test RLS.
-- ============================================================
alter table leads            enable row level security;
alter table campaigns        enable row level security;
alter table campaign_leads   enable row level security;
alter table lead_events      enable row level security;
alter table agent_runs       enable row level security;
alter table enrichment_cache enable row level security;

-- Example scoped policy (commented — enable only if adding per-user access):
-- create policy "owner can read leads" on leads for select
--   to authenticated using (auth.uid() = owner_id);
