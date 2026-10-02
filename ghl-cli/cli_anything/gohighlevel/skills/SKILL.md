---
name: "cli-anything-gohighlevel"
description: "CLI interface for GoHighLevel CRM/Marketing API: contacts, opportunities, calendars, workflows, conversations, email campaigns and smart lists, payments and subscriptions, agency SaaS sub-accounts, forms, funnels, documents and contracts, social media, locations"
triggers:
  - gohighlevel
  - ghl cli
  - ghl contacts
  - ghl workflows
  - ghl calendars
---

# cli-anything-gohighlevel

CLI interface for the GoHighLevel (GHL) CRM and Marketing API. Manage contacts, pipeline opportunities, calendars, workflows, conversations, emails, payments, forms, social media posts, and locations from the command line or interactive REPL.

For checkout price hiding and iframe probes, `funnels checkout-assets` and
`funnels serve-probe` are local helpers: they generate the CSS, JS and iframe
HTML and serve it on loopback. Pasting the code into a checkout, publishing, and
creating or deleting coupons stay in the GHL browser UI; the CLI adds no API for
them.

## Prerequisites

- Python 3.10+
- `GHL_API_KEY` environment variable set with your GHL API bearer token
- `GHL_LOCATION_ID` environment variable — your sub-account's location ID (the long ID in your GHL URL)
- `GHL_AGENCY_API_KEY` environment variable for agency SaaS reads. Save it in the profile resolved by the `ghl` wrapper or explicitly export it for one command. A normal location token is not sufficient for these company-scoped endpoints.

## Installation

From the root of this repo (wherever you cloned or unzipped it):

```bash
./install.sh
```

The installer creates a `.venv/`, installs the package, and initializes
`~/.config/ghl/config` plus `~/.config/ghl/profiles/default.env` without
overwriting existing config or profiles. Set `GHL_CONFIG_DIR` to use another
root. Add `GHL_API_KEY` and `GHL_LOCATION_ID` to the resolved profile, then run
commands via the `./ghl` wrapper. The wrapper resolves `GHL_PROFILE`, the nearest
`.ghlprofile`, then `default_profile` in the config file and exits if none is
configured.

## Usage

### CLI Mode (one-shot commands)
```bash
ghl contacts list --json
ghl contacts get <contact_id>
ghl contacts create --email user@example.com --first-name John --last-name Doe
ghl opportunities list --status open
ghl calendars list
ghl workflows list
ghl conversations list --status unread
ghl payments transactions
ghl --json payments subscriptions --status active
ghl --json payments subscription <subscription_id>
ghl --json saas locations --company-id <company_id>
ghl --json saas subscription <location_id> --company-id <company_id>
ghl forms list
ghl --experimental --json forms get <form_id>
ghl social posts
ghl locations get
```

### REPL Mode (interactive)
```bash
ghl
# or
cli-anything-gohighlevel
```

### Global Options
- `--json` — Output as machine-readable JSON (recommended for agents)
- `--location-id <ID>` — Override GHL_LOCATION_ID for this command
- `--version` — Show CLI version
- `--help` — Show help

## Command Groups

| Group | Description | Key Commands |
|-------|-------------|--------------|
| `contacts` | Contact management | list, get, create, update, delete, search, add-tag, remove-tag |
| `opportunities` | Pipeline deals | list, get, create, update, delete, pipelines |
| `calendars` | Scheduling | list, get, slots, appointments, book, groups |
| `workflows` | Automation workflows | list |
| `conversations` | Messaging (SMS, email, chat) | list, get, messages, send |
| `emails` | Broadcast campaigns/templates | campaigns, templates, get-campaign, create-campaign, delete-campaign *(experimental)* |
| `smartlists` | Saved contact filters | list, get, create, delete *(experimental)* |
| `payments` | Location financial operations | transactions, subscriptions, subscription, orders, invoices, create-invoice |
| `forms` | Form management | list, submissions, get, create, delete *(write/full-read experimental)* |
| `funnels` | Funnel/page building and local checkout probes | list, pages, export-page, create-page, set-content, checkout-assets, serve-probe |
| `social` | Social media posting | accounts, posts, create-post |
| `locations` | Sub-account management | get, search, tags, custom-fields, custom-values |
| `saas` | Audit and manage agency SaaS sub-accounts | audit, locations, find-location, subscription, plans, plan, pause, disable, delete |
| `documents` | Documents, contracts, templates | list, templates, send-template, get-template, export-template, get-redirect, set-redirect, create-template, update-template, add-field *(authoring experimental)* |

### Subscriptions and SaaS sub-accounts

`payments subscriptions` reads recurring purchases inside the current location.
The separate `saas` group reads how the agency bills and provisions sub-accounts.
Payment subscription commands remain read-only. SaaS lifecycle writes use
documented public endpoints, default to dry-run, and require `--apply` plus an
interactive approval. SaaS commands require an agency/company-scoped token.
For persistent use, put it in the resolved profile under
`~/.config/ghl/profiles/` or `$GHL_CONFIG_DIR/profiles/`. An explicitly exported
value overrides the profile default.

```bash
ghl --json payments subscriptions --contact-id CONTACT_ID --status active
ghl --json payments subscription SUBSCRIPTION_ID
ghl --json saas locations --company-id COMPANY_ID --page 1
ghl --json saas find-location --company-id COMPANY_ID --subscription-id STRIPE_SUBSCRIPTION_ID
ghl --json saas subscription LOCATION_ID --company-id COMPANY_ID
ghl --json saas audit --company-id COMPANY_ID
ghl --json saas plans --company-id COMPANY_ID
ghl --json saas plan PLAN_ID --company-id COMPANY_ID
ghl saas pause LOCATION_ID --company-id COMPANY_ID
ghl saas disable LOCATION_ID --company-id COMPANY_ID
ghl saas delete LOCATION_ID --company-id COMPANY_ID \
  --reason "Approved account closure" --keep-twilio-account
```

The payment `--status` option is a server pass-through. It works live for known
statuses but is not listed in the current official parameter table, so do not
assume a closed enum. There is no cancellation command because no documented
public cancellation endpoint exists and the exact internal request has not been
captured. Never guess a money-moving route. See `docs/subscriptions.md`.

`saas audit` reconciles every returned SaaS location with the separate payment
subscriptions created by the billing-location funnel. Live validation showed
that the agency SaaS and payment subscription IDs do not overlap, so the audit
preserves both and joins by the SaaS detail's GoHighLevel contact ID, with exact
normalized email only when the contact ID is absent. It never joins by name.
It also fresh-reads each location's SaaS subscription and the latest
successful live transaction for matched payment records. Any required read
failure or unknown status makes that row `unknown`.
Ambiguous shared-contact or email evidence is also `unknown`; a warning alone
is not enough evidence for a business finding.

Set `GHL_SAAS_BASELINE` (for example `280/250`, subscriptions/contacts) and a
large population difference makes the command exit nonzero and withhold its
classification totals. Without it the check reports `unchecked`. Provide an authoritative `deal_grant` export through
`--comped-emails-file`; without one, the report warns that only exact internal
domains can be identified as comped. Read `docs/subaccount-audit.md` before
using the output for account review. This command is GET-only and has no apply
path.

Lifecycle commands are single-target only. Without `--apply` they print the
target, both subscription sides, and last payment, then exit without a write.
With `--apply`, they still require interactive approval and fresh-read the
result. `--json` is for dry runs and is rejected with `--apply`. The protected
location (`GHL_PROTECTED_LOCATION_ID`, else `GHL_LOCATION_ID`) is never writable. Disable must export the
wallet balance and complete wallet transaction history first. Delete additionally
requires a paused location, no active subscription on either side, a reason,
an explicit Twilio choice, and typed confirmation of the exact location name.
Read `docs/subaccount-lifecycle.md` before approving one of these actions.

### Contract templates (experimental)

Template authoring uses GHL's unsupported UI service and requires Firebase
session credentials only. `GHL_IAM_TOKEN` is optional and normally unset — the
proposal service authenticates on `token-id` alone, measured 2026-08-24. It
never publishes or sends.
Every new draft includes company Date and Signature fields assigned to
`assignedSender` / `users`, plus contractor Full name, Date, and Signature
fields assigned to `assignedContact` / `contacts`, all required on the final
page. Company fields appear first visually. The template editor displays the
contractor placeholder as order 1 and sender as order 2, but templates do not
persist sequential-signing enforcement. For each standalone document, select
the contractor as primary, enable **Set signing order**, keep the contractor
first and sender second, save as a draft, and fresh-read the document to verify
the persisted toggle and order. Party-specific matches are retained without
duplication and matching optional fields are promoted to required. For
uploaded PDF drafts assembled in the browser, add the same five required fields before saving and
fresh-read the saved draft to verify persistence.
Unassigned native matches are repaired to the contractor placeholder.
`--name` overrides a top-level `name` in `--from-json`.

```bash
ghl --experimental --json documents create-template --name "Agreement"
ghl --experimental --json documents get-redirect TEMPLATE_ID
ghl --experimental --json documents set-redirect TEMPLATE_ID \
  --url https://example.com/complete --target existing-tab
ghl --experimental --json documents create-template --name "Custom Agreement" --from-json examples/contract-template.example.json
ghl --experimental --json documents add-field TEMPLATE_ID --type signature --page 1
ghl --experimental documents export-template TEMPLATE_ID --output backup.json
```

See `docs/contracts.md` before using these commands.

## Agent Usage Notes

- Always use `--json` flag for programmatic consumption
- Contact search uses `contacts search <query>` for name-based search
- Workflow enrollment is done via `contacts` group (not workflows): the GHL API triggers workflows through contact endpoints
- Social media posting requires OAuth-connected accounts
- All endpoints require valid `GHL_API_KEY` bearer token
- Agency SaaS endpoints require `GHL_AGENCY_API_KEY` with company scope
- API base URL: `https://services.leadconnectorhq.com`
- API version header: `2021-07-28` (internal email/smartlist routes require it too —
  omitting it returns `401 version header was not found`, which looks like an auth failure)
- Never verify a write with an immediate read-back; GHL list endpoints are eventually
  consistent and will report a successful delete as still present

## Email campaigns — drafts only, by design

`emails create-campaign` builds the template, uploads the HTML, creates the campaign and
saves its subject/sender/recipients. It stops at `draft`.

**Sending is a separate endpoint (`POST /emails/schedule/start`) and is deliberately not
wrapped.** Do not add it and do not call it by hand — one request goes to the entire bound
list. Treat "the draft is ready, a human sends it" as the end of the task.

Defaults, each of which errors rather than quietly degrading:

- **Subject-line A/B** — at least one `--ab-subject` required (`--no-ab-test` opts out)
- **UTM tracking on** — `--no-utm` opts out
- **First-name fallback** — write `{{contact.first_name}}`; it is rewritten to
  `{{default contact.first_name "there"}}`, which covers *blank* names as well as missing
  ones. Copy with no first-name field is rejected (`--allow-no-personalization` overrides).

Full reference, endpoint map and traps: `docs/email-campaigns.md`.

## Builders (experimental — unofficial internal API)

The public API is read-only for workflows (`workflows list` only). Creating/updating
workflows and builder content requires the `--experimental` flag, which uses GHL's **unofficial** internal
API (`backend.leadconnectorhq.com`) authenticated with `GHL_FIREBASE_REFRESH_TOKEN`.

**Surface this to the user before using it:**
- That Firebase token is the user's **entire GHL login** (full account access), not a
  scoped key. Use it **only on the user's own agency account — never a client's**.
- To provision workflows for client sub-accounts, prefer **Snapshots** (build once in
  the UI, sub-accounts inherit it) — no token, no internal API.
- The internal API has no SLA and may change/break without notice. Workflows are
  created as draft. The CLI prints a one-time warning on use
  (`GHL_SUPPRESS_INTERNAL_WARNING=1` to silence).

Landing-page commands:

```bash
ghl funnels templates
ghl funnels init-template pricing --theme otter --output page.json
ghl funnels lint page.json
ghl funnels preview page.json --output page-preview.html
ghl --experimental --json funnels pages <funnel-id>
ghl --experimental funnels export-page <page-id> --output backup.json
ghl --experimental funnels create-page <funnel-id> --from-json examples/landing-page.example.json
ghl --experimental funnels set-content <page-id> --from-json page.json
ghl --experimental --json funnels elements <page-id>
ghl --experimental funnels export-element <page-id> <element-id> --output native.json
ghl --experimental funnels export-global-sections <funnel-id> --output globals.json
```

Do not add `--publish` until the generated draft has been inspected in GHL. Raw JSON
from `export-page` is accepted for full-fidelity backup/restore. First-class compact
elements include text, bulletList, button, image, video, divider, form, survey,
calendar, timer, faq, logoShowcase, customCode, checkout, and order confirmation.
Use `native` nodes exported with `export-element` for every other current or future
GHL widget. `class`, `styles`, `extra`, `wrapper`, and `mobileStyles` can be supplied
as advanced overrides.

For new pages, prefer a built-in template and resolve every lint error before
saving a GHL draft. Inspect the local preview and the real GHL draft at desktop and
mobile widths. Full visual rules are in `docs/landing-page-design-system.md`; the
reference audit and offer-matched copy sequences are in
`docs/reference-funnel-patterns.md`.

## Examples

```bash
# List contacts as JSON
ghl --json contacts list --limit 50

# Create a contact with tags
ghl contacts create --email lead@company.com --first-name Jane --last-name Smith --tag "hot-lead" --tag "webinar"

# Search contacts
ghl contacts search "john"

# List pipeline opportunities
ghl --json opportunities list --status open

# Get available calendar slots
ghl calendars slots <calendar_id> --start 2026-03-25 --end 2026-03-30

# Send SMS in conversation
ghl conversations send <conversation_id> --type SMS --message "Thanks for your interest!"

# List transactions
ghl --json payments transactions --limit 50

# Create social post
ghl social create-post --account-id <id> --text "New blog post!" --schedule "2026-03-26T10:00:00Z"
```
