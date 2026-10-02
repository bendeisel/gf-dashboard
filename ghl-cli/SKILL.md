---
name: "gohighlevel-cli"
description: "Build and manage GoHighLevel from the command line: contacts, workflows, native forms, round-robin calendars, two-step funnels, landing pages, broadcast email campaigns, smart lists, contract templates, SaaS sub-account audits, conversations, payments, and real-preview visual QA."
triggers:
  - gohighlevel
  - ghl cli
  - ghl contacts
  - ghl workflows
  - ghl calendars
  - ghl opportunities
  - ghl conversations
  - ghl payments
  - ghl locations
  - ghl emails
  - ghl email campaign
  - ghl broadcast
  - ghl smartlists
  - ghl smart list
  - ghl list building
  - ghl create workflow
  - ghl read emails
  - ghl funnels
  - ghl landing page
  - ghl form builder
---

## Step 0 — Prerequisites

Before any operation, work from the installed `gohighlevel-cli` skill folder
and verify the requirements below. If any required check fails, stop and tell
the user how to fix it. Do not generate placeholder commands or continue with
partial credentials.

| Requirement | Check | Where to get it |
|---|---|---|
| Python 3.10+ | `python3 -c 'import sys; assert sys.version_info >= (3,10)'` | [python.org/downloads](https://www.python.org/downloads/) |
| Installed CLI wrapper | `test -x ./ghl && ./ghl --help >/dev/null` | Re-run `bash install.sh` in this skill folder |
| Public API credentials for public commands | `./ghl locations get >/dev/null` succeeds | Set `GHL_API_KEY` and `GHL_LOCATION_ID` in your profile file (see Install) |
| Browser setup values for `--experimental` commands | `GHL_FIREBASE_API_KEY` and `GHL_FIREBASE_REFRESH_TOKEN` are set in the same profile file | Run the no-network helper in `docs/get-firebase-token.md` |

The fourth row is required only for the `--experimental` commands: workflow
creation, form and survey builders, funnel builders, **email campaigns, and
smart lists**. If anything required for the requested operation is missing, STOP.

# GoHighLevel CLI v3.1

Command-line interface for GoHighLevel that lets you or Claude Code build and
manage CRM data, automations, forms, calendars, complete funnel pages, broadcast
email campaigns, and segmented smart lists from the terminal. Built with the
CLI-Anything framework (Click + interactive REPL).

**v3 additions:** broadcast email campaign authoring (subject-line A/B testing and
UTM tracking on by default, enforced first-name fallbacks) and smart-list building
with real filter support. Both ride the internal API, which is the only way to
reach them: the public GoHighLevel API cannot create campaigns or smart lists at all.

**v3.1 additions (2026-09-21):** contract template authoring, subscription and
SaaS sub-account reads with a read-only billing audit, guarded single-target
pause/disable/delete for SaaS sub-accounts, checkout code helpers, and a fix that
stops workflow edits from wiping the workflow's sender address.

**v3 builds drafts, never sends.** See "The one thing to know first" below.

## Install (60 seconds)

Everything the CLI needs ships in this skill folder. Requirements: **Python 3.10+** and a GoHighLevel sub-account.

```bash
cd ~/.config/claude-accounts/gf-account/skills/gohighlevel-cli
./install.sh
```

The installer creates a local `.venv/`, installs the package, and creates a
credential profile at `~/.config/ghl/profiles/default.env` from `.env.example`.
It prints the exact path when it finishes. The marketplace installer already
runs this step for you; if it printed "post-install complete", go straight to
filling in the profile.

Open the profile file and fill in your credentials:

```env
GHL_API_KEY=pit-xxxxxxxx-...        # GHL Settings -> Private Integrations
GHL_LOCATION_ID=YOUR_LOCATION_ID    # the long ID in your GHL URL
```

Credentials live in the profile, not in a `.env` next to the wrapper. `./ghl`
reads `$GHL_PROFILE`, then the nearest `.ghlprofile` file, then `default_profile`
in `~/.config/ghl/config`. To run against a second sub-account, add another file
such as `~/.config/ghl/profiles/client-a.env` and call
`GHL_PROFILE=client-a ./ghl ...`.

Smoke test:

```bash
./ghl contacts list --limit 5
```

You should see contacts from your account. Run `./ghl` with no arguments for an interactive REPL with autocomplete.

## Requirements

- Python 3.10+ (the venv lives at `.venv/` inside this skill folder)
- `GHL_API_KEY` env var — Private Integration Token (bearer) for the public API
- `GHL_LOCATION_ID` env var — your sub-account's location ID
- `GHL_FIREBASE_REFRESH_TOKEN` env var — only for `--experimental` commands (internal API). Grab it with the DevTools console snippet in `docs/get-firebase-token.md`.

- `GHL_AGENCY_API_KEY` env var, optional: an agency-level token, needed only for the `saas` commands.

All of them live in your profile file (`~/.config/ghl/profiles/<profile>.env`); the `./ghl` wrapper loads it.

## Command Groups

| Group | Commands | Status |
|-------|----------|--------|
| `contacts` | list, get, create, update, delete, search, add-tag, remove-tag | LIVE |
| `opportunities` | list, get, create, update, delete, pipelines | LIVE |
| `calendars` | list, get, slots, appointments, book, groups, create, update, delete | LIVE |
| `workflows` | list, enroll, remove | LIVE |
| `workflows` | create, create-step, create-n8n | EXPERIMENTAL |
| `conversations` | list (--type), get, messages (--type), get-email, send | LIVE |
| `emails` | list-campaigns | LIVE |
| `emails` | campaigns, templates, create-campaign, get-campaign, delete-campaign | EXPERIMENTAL |
| `smartlists` | list, get, create, delete | EXPERIMENTAL |
| `payments` | transactions, orders, invoices, create-invoice, subscriptions, subscription, subscription-discount | LIVE |
| `saas` | locations, plans, plan, subscription, find-location, audit | LIVE (read-only, agency token) |
| `saas` | pause, disable, delete | LIVE (single target, dry run unless `--apply`) |
| `locations` | get, search, tags, custom-fields, custom-values, set-custom-value | LIVE |
| `forms` | list, submissions | NEEDS SCOPE |
| `forms` | create, delete | EXPERIMENTAL |
| `surveys` | list, create, delete | EXPERIMENTAL |
| `funnels` | templates, init-template, lint, preview, checkout-assets, serve-probe | LOCAL |
| `funnels` | list, create, pages, export-page, create-page, set-content, delete, elements, export-element, export-global-sections, set-global-sections | EXPERIMENTAL |
| `social` | accounts, posts, create-post | NEEDS SCOPE |
| `documents` | list, send, templates, send-template | NEEDS SCOPE |
| `documents` | create-template, get-template, update-template, export-template, add-field, get-redirect, set-redirect | EXPERIMENTAL |

"NEEDS SCOPE" = enable that scope on your Private Integration Token in GHL Settings.

## Agent Usage

Always use `--json` for programmatic output:

```bash
./ghl --json contacts list --limit 50
./ghl --json contacts search "john"
./ghl --json opportunities list --status open
./ghl --json opportunities pipelines
./ghl --json calendars list
./ghl --json calendars slots <cal_id> --start 2026-03-25 --end 2026-03-30
./ghl --json workflows list
./ghl --json conversations list --type Email --limit 10
./ghl --json payments transactions --limit 20
./ghl --json locations get
./ghl --json locations custom-fields
./ghl --experimental --json smartlists list
./ghl --experimental --json emails campaigns
```

`--json` works on most read commands and pipes cleanly into `jq`.

## Key Patterns

### Email Campaigns and Smart Lists (v3 — Experimental, Internal API)

Full reference with the endpoint map and every trap: **`docs/email-campaigns.md`**.
Requires `--experimental` and `GHL_FIREBASE_REFRESH_TOKEN`.

#### The one thing to know first

**Creating a campaign and sending it are different endpoints.** The CLI wraps
create and save-settings. It does **not** wrap `POST /emails/schedule/start`.

No `ghl` invocation can dispatch mail. Every campaign it builds stops at `draft`
in Marketing > Emails for a human to review and send from the UI. This is
deliberate — a single send request goes to the entire bound list. **Do not add a
send command "for completeness."**

#### Build a campaign

```bash
# What can I send to?
./ghl --experimental --json smartlists list

# Draft a campaign against one of them
./ghl --experimental emails create-campaign \
  --name "August newsletter" \
  --subject "{{contact.first_name}}, three deliverability checks" \
  --ab-subject "The 10-minute deliverability audit" \
  --from-name "Your Brand" \
  --from-email you@yourdomain.com \
  --html-file body.html \
  --smart-list <smartListId>

# Inspect / remove
./ghl --experimental --json emails get-campaign <campaignId>
./ghl --experimental emails delete-campaign <campaignId> --template-id <templateId>
```

`create-campaign` prints the `campaignId`, `templateId`, a `previewUrl` for the
rendered HTML, and an `editUrl` that opens the draft in GHL.

#### Defaults that are on unless you turn them off

These encode direct-response house style. Where a default cannot be satisfied,
the command **errors** rather than quietly producing the lesser thing.

| Default | Turn off with | Notes |
|---|---|---|
| **Subject-line A/B** | `--no-ab-test` | At least one `--ab-subject` is required. A one-variation "test" is not a test |
| **UTM tracking** | `--no-utm` | Appends the location's default UTM params |
| **First-name fallback** | `--first-name-fallback "..."` | Every `{{contact.first_name}}` is rewritten to the safe form |
| Click tracking **off** | `--click-tracking` | Off matches how broadcasts are normally sent |

Copy containing no first-name merge field at all is rejected; pass
`--allow-no-personalization` if that is genuinely intended.

A/B knobs: `--ab-test-size` (percent of list used for the test, default 50),
`--ab-test-hours` (default 4), `--ab-winning-criteria` (`openRate` | `clickRate`).

#### Merge fields: always use the `default` helper

GHL registers a Handlebars `default` helper:

```handlebars
{{default contact.first_name "there"}}
```

It substitutes the fallback when the value is `null`, `undefined` **or the empty
string**. That last case is the one that bites: a contact with a *blank*
`first_name` is far more common than one missing the field, and a bare
`{{contact.first_name}}` renders `Hi ,` in their subject line.

You do not need to write the helper yourself. Write `{{contact.first_name}}` and
`create-campaign` rewrites it, idempotently, so re-running on already-converted
copy is safe.

#### Smart lists

```bash
./ghl --experimental smartlists create --name "Mailable" \
  --filter email:exists \
  --filter valid_email:eq:true \
  --filter dnd:not_eq:true \
  --filter tags:not_eq:blacklist,unsubbed
```

`--filter` is `field:operator[:value]`, repeatable, ANDed. A comma-separated
value becomes an array with `minimumMatch: 1`; `true`/`false` become real
booleans; colons inside values survive, so URLs work. Fields may be dotted
(`dnd_settings.Email.status`).

Nesting matters and is handled for you: GHL wants **OR-group → AND-group →
leaves**. A flat filter array is accepted and silently matches everything.

**With no `--filter` the list matches every contact.** Verify a filter actually
narrows by comparing counts before trusting it.

#### Recipients are bound on the campaign, not at send time

| Flag | Result |
|---|---|
| `--smart-list ID` | the list's own filter leaves |
| `--tag a --tag b` | a tags filter matching either |
| neither | **every contact** |

`create-campaign` warns on stderr if the smart list you named has no filters,
because that is indistinguishable from "send to everyone".

### Funnel and Landing-Page Builds (Mandatory Completion Gate)

The CLI can create the native form, calendar, funnel, and page content for a
complete two-step lead-generation funnel. Use built-in templates as the base,
then keep the result in draft until the user explicitly approves publishing.

```bash
# Create the native assets
./ghl --experimental forms create --from-json form.json
./ghl --json calendars create --from-json calendar.json

# Build and validate the page specs locally
./ghl funnels templates
./ghl funnels init-template optin --theme modern --output step-1.json
./ghl funnels lint step-1.json
./ghl funnels preview step-1.json --output step-1-preview.html

# Back up and write the actual GHL drafts
./ghl --experimental funnels export-page <page-id> --output backup.json
./ghl --experimental funnels set-content <page-id> --from-json step-1.json
```

`set-content` automatically backs up the current draft before replacement.
Never add `--publish` without explicit user authorization.

For every landing page, the real served GHL draft is the source of truth. Wait
for native forms, calendars, and fonts to settle, then personally inspect
full-page captures at 1440x900, 768x1024, and 393x852. Run every CTA, form, and
calendar path twice without submitting a lead or booking a call. Check for
literal escaped markup, horizontal overflow, mobile/WebKit failures, and
above-fold conversion controls. Local `funnels preview`, DOM snapshots, lint
scores, and worker prose are supporting evidence only.

Default page typography is Inter 700 for headlines and Roboto 400/500 for body
copy. True single-column sections center every child block; native field labels
remain left-aligned for usability. See `docs/landing-page-design-system.md` and
`docs/reference-funnel-patterns.md` for the complete guardrails.

Treat GHL builder metadata as intent, not rendered proof. Mark brand images with
`role: "logo"`, set `align: "center"`, and preserve runtime CSS that centers both
the wrapper and `<img>`. Keep at least 12px of explicit vertical space after any
logo, image, or primary media block (20-24px is the normal rhythm). When an
embedded calendar is the primary action, place it directly after the booking
copy and omit a redundant jump button. Compact URL buttons must use
`action: "url"`; `visit-website` is not a valid compact action.

Native multi-step surveys require a rendered footer check. GHL can keep
`.ghl-footer` at 50px while the padded child contains a 52px button, and an
invisible `.ghl-btn-placeholder` can steal width. The design system normalizes
the footer/buttons and hides that placeholder. Verify the first slide and a
later Back + Continue slide in the real preview; a clean first screen alone is
not sufficient.

### Email Reading (Conversation Filtering)

Emails in GHL flow through the Conversations API, not a separate inbox. Three-step workflow:

```bash
# Step 1: List email conversations
./ghl --json conversations list --type Email --limit 10

# Step 2: Get messages from a conversation (email only)
./ghl --json conversations messages <conversation_id> --type Email

# Step 3: Get full email details (subject, body HTML, headers, attachments)
./ghl --json conversations get-email <email_message_id>
```

Available `--type` choices: `Email`, `SMS`, `WhatsApp`, `GMB`, `IG`, `FB`, `Live_Chat`, `Custom`

### Workflow Enrollment (Public API)

```bash
./ghl workflows enroll --contact-id <contact_id> --workflow-id <workflow_id>
./ghl workflows remove --contact-id <contact_id> --workflow-id <workflow_id>
```

### Workflow Creation (Experimental — Internal API)

Requires the `--experimental` flag and `GHL_FIREBASE_REFRESH_TOKEN` set. All workflows are created as **draft** — never auto-published.

```bash
# Create a workflow from campaign JSON
./ghl --experimental workflows create --name "My Campaign" --from-json campaign.json

# Build steps incrementally
./ghl --experimental workflows create-step --type email --name "Welcome" \
  --subject "Welcome!" --body "Thanks for signing up." --output-file steps.json
./ghl --experimental workflows create-step --type wait --name "Pause" \
  --value 2 --unit days --output-file steps.json

# Create an n8n bridge workflow (tag trigger → webhook to n8n)
./ghl --experimental workflows create-n8n --name "Lead Notify" \
  --webhook-url "https://your-n8n.example.com/webhook/lead-notify" \
  --tag "new-lead"
```

Step types: `email`, `sms`, `imessage`, `wait`, `tag`, `webhook`, `ai`, `goal`

`--type goal` adds a terminal `workflow_goal` exit step (`--tags` = comma-separated exit tags; the contact leaves the workflow when any is added).

### Branching (If/Else) workflows

`create-step` builds **linear** flows only. To build an If/Else branch (e.g. "has tag X → email A, else → email B"), write a builder script using the helpers in `cli_anything/gohighlevel/utils/workflow_builder.py`:

- `if_else_nodes(name, branch_name, conditions, x, y)` → the 3-node GHL branch; wire children via the returned `yes_id`/`no_id`.
- `tag_condition([tags], has=True)` / `field_condition(field_id, value)` → branch conditions.
- `goal_step(name, tags)` → a `workflow_goal` exit.
- Build via `CampaignBuilder` with `"graph": True` in the workflow def so branch wiring / canvas positions are preserved.

A runnable reference build lives at `builders/example-nurture-builder.py` — study it before writing your own.

### Contact Management

```bash
./ghl contacts create --email lead@co.com --first-name Jane --last-name Smith --tag "hot-lead" --tag "webinar"
./ghl contacts add-tag <contact_id> hot-lead qualified
./ghl contacts remove-tag <contact_id> cold
./ghl contacts search "john doe"
```

### Calendar Scheduling & Management

```bash
./ghl --json calendars slots <calendar_id> --start 2026-03-25 --end 2026-03-30
./ghl calendars book --calendar-id <id> --contact-id <id> --slot-id <id> \
  --start "2026-03-26T10:00:00" --end "2026-03-26T10:30:00"

# Manage the calendar object itself
./ghl --json calendars create --name "Strategy Call" --calendar-type round_robin \
  --team-member <userId> --slot-duration 30 --slot-duration-unit mins --slug strategy-call --active
./ghl --json calendars update <calendar_id> --name "Renamed Call" --inactive
./ghl calendars delete <calendar_id>          # interactive confirm; --yes to skip
```

> **WARNING:** GHL does not audit-log calendar-object deletions — a deleted calendar cannot be recovered without escalating to GHL Support.

### Contract Templates (Experimental, Internal API)

Build and edit document/contract templates from a JSON spec instead of dragging
fields around the GHL editor. `create-template` starts from
`examples/contract-template.example.json`, `add-field` places signature, date and
text fields, and `get-redirect` / `set-redirect` control where a signer lands
after signing. Full reference: `docs/contracts.md`.

### Subscriptions and SaaS Sub-accounts

```bash
./ghl --json payments subscriptions --contact-id <contact_id>
./ghl --json payments subscription-discount <subscription_id>   # read-only coupon evidence
./ghl --json saas locations --company-id <company_id>            # needs GHL_AGENCY_API_KEY
./ghl --json saas audit --company-id <company_id>                # read-only billing reconciliation
```

`saas audit` joins each SaaS sub-account to its payment subscription by contact
ID and classifies it (paid, past due, unpaid, comped, paused, unknown). It never
writes. Configure it in your profile: `GHL_SAAS_PRODUCT_ID` (the product your
SaaS plan is sold under), `GHL_INTERNAL_DOMAINS` (your team's email domains) and,
optionally, `GHL_SAAS_BASELINE` (expected `subscriptions/contacts`, which turns on
a population sanity check). See `docs/subaccount-audit.md`.

`saas pause`, `disable` and `delete` act on one sub-account at a time. Without
`--apply` they only print what they would change. With `--apply` they still ask
for confirmation and re-read the result. Your own location (`GHL_PROTECTED_LOCATION_ID`,
or `GHL_LOCATION_ID` when that is unset) is always refused. Read
`docs/subaccount-lifecycle.md` and `docs/subscriptions.md` before using them.

## Workflow Best Practices

1. **Always confirm trigger + goal** before building — what starts the workflow (tag, form, event) and what exit removes contacts (purchase, booking, tag change).
2. **End every workflow with a Goal Event step** (`workflow_goal`) so contacts exit the moment the goal is met, wherever they are in the sequence.
3. **Keep workflows simple** — Wait → Email → Wait → Email → Goal. Don't sprinkle tracking tags between steps unless asked.
4. **Verify all links** in email copy before shipping — never include checkout URLs or resources you haven't confirmed exist.

## Known Gotchas (real bugs, encode the workaround)

1. **GET → mutate → PUT on a workflow WIPES canvas positions.** Every step you write back must include `advanceCanvasMeta = {"position": {"x": ..., "y": ...}}` or the GHL canvas renders empty.
2. **Builder scripts don't load your profile.** Export it first (`set -a && source ~/.config/ghl/profiles/default.env && set +a`) before `python3 builders/foo.py`; the `./ghl` wrapper does this for you.
3. **Workflow UI URL format** is `https://app.gohighlevel.com/location/{loc}/workflow/{wf_id}` (some whitelabel domains vary).
4. **`triggers` comes back empty on migrated workflows** — the trigger record lives at `triggersFilePath`; don't re-create it.
5. **NEVER add fallback syntax to GHL merge tags.** `{{contact.first_name || "there"}}` renders literally in the sent email. Use the bare merge tag, or the `default` helper documented above.
6. **NEVER embed a manual footer (address + unsubscribe) in GHL email HTML.** GHL auto-appends one; a hand-coded footer ships a double footer.
7. **Email fonts must be uniform** — put `font-family`/`font-size` on `<span>`s and render bold/italic as styled spans, not `<strong>`/`<em>` (GHL resets those to Verdana). GHL also flattens styled `<a>` buttons to plain links.
8. **Reuse workflow folders by id**, not name — creating by `folder_name` can duplicate folders. List folders at `GET /workflow/{loc}/directory`.
9. **A smart list's display name is `listName`, not `name`.** There is no `name` key, so reading one prints empty and every list looks unnamed. Sort by `displayOrder`.
10. **All internal email routes require the header `Version: 2021-07-28`.** Omit it and you get `401 version header was not found`, which reads like an auth failure but is not.
11. **`abTestInfo` spellings are not guessable and wrong ones are accepted silently.** `testType` is `"emailSubject"` (camelCase); `testDuration` is in **seconds**; `testSize` is a percent. The API stores unknown keys without complaint, so a guessed spelling produces a campaign the UI cannot interpret, with no error anywhere. When a payload shape is uncertain, read an existing UI-created record.
12. **GHL list endpoints are eventually consistent.** Never confirm a write with an immediate read-back; a successfully deleted record still appears in a list for seconds.
13. **A workflow PUT that leaves out `senderAddress` clears it.** GHL resets top-level workflow fields a PUT omits, and every email step with a blank From then sends as the contact's assigned user. The internal client now copies the current sender into any workflow PUT that leaves it out (fixed in v3.1). If you write your own PUT, send `senderAddress` explicitly, and pass `null` only when you mean to clear it.

## Architecture

```
gohighlevel-cli/            (this skill folder)
├── install.sh              # One-shot installer (.venv + package + credential profile)
├── ghl                     # Shell wrapper (activates venv, loads your profile)
├── setup.py                # Package config (cli-anything)
├── .env.example            # Credential template, copied into your profile
├── builders/               # example-nurture-builder.py — workflow-builder reference
├── examples/               # Landing-page spec examples
├── docs/                   # email-campaigns.md, contracts.md, subaccount-audit.md, ...
└── cli_anything/
    └── gohighlevel/
        ├── gohighlevel_cli.py         # Main CLI (Click-based)
        └── utils/
            ├── ghl_client.py          # Public API client (bearer token, version routing)
            ├── ghl_internal_client.py # Internal API client (Firebase JWT) [EXPERIMENTAL]
            ├── form_survey_builder.py # Native form/survey payload builder
            ├── funnel_page_builder.py # Compact spec -> GHL builder content
            ├── landing_page_design.py # Templates, themes, lint, local preview
            ├── merge_fields.py        # Handlebars `default` rewriting for merge tags
            ├── workflow_builder.py    # Step builders + CampaignBuilder [EXPERIMENTAL]
            ├── contract_template_builder.py # Contract template specs [EXPERIMENTAL]
            ├── saas_audit.py          # Read-only SaaS billing reconciliation
            ├── saas_lifecycle.py      # Guards for pause/disable/delete
            ├── checkout_probe.py      # Local checkout CSS/JS/iframe helpers
            └── repl_skin.py           # Interactive REPL (prompt-toolkit)
```

## API Details

### Public API (stable)
- **Base URL:** `https://services.leadconnectorhq.com`
- **Auth:** Bearer token via `GHL_API_KEY`
- **Version header:** auto-routed by path (`2021-04-15` for conversations/calendars, `2021-07-28` for everything else)

### Internal API (experimental)
- **Base URL:** `https://backend.leadconnectorhq.com`
- **Auth:** Firebase JWT via `token-id` header (NOT `Authorization: Bearer`), auto-refreshed every ~50 min from `GHL_FIREBASE_REFRESH_TOKEN`
- **Capabilities:** workflow + folder create/delete, step saving, trigger creation (incl. multi-tag), tag creation, email campaign authoring, smart-list creation
- **Only use against your own agency account** — never a client sub-account. Use Snapshots for clients.

## Known Limitations

- **The CLI cannot send email.** Campaign creation stops at draft by design; sending is done by a human in the GHL UI.
- Public Workflows API is read-only (list only) — creation requires `--experimental`
- Email campaigns and smart lists exist only on the internal API — the public API cannot create either, so both require `--experimental`
- Documents/Proposals require templates (no create-from-scratch)
- Social media posting requires OAuth-connected accounts
- Forms, Social, and Documents scopes need enabling on the Private Integration Token
- Firebase refresh tokens can be revoked — grab a fresh one via `docs/get-firebase-token.md` if auth fails
- The internal API may change without notice (mitigated by `--experimental` + draft-only creation)
