# GoHighLevel CLI

A command-line interface for GoHighLevel that lets you (or an agent) drive your CRM from the terminal: contacts, opportunities, calendars, conversations, workflows, emails, payments, forms, funnels, social media, locations, agency SaaS subscriptions, and documents.

Built by [Lead Gen Jay](https://leadgenjay.com).

---

## What you get

- **15 command groups** covering contacts, opportunities, calendars, workflows, conversations, emails, smart lists, payments, forms, surveys, funnels, social, locations, agency SaaS subscriptions, and documents.
- **Email campaign authoring** — draft a broadcast with A/B subject lines, personalization fallbacks and UTM tracking, bound to a smart list. It creates drafts and *cannot send*; see [`docs/email-campaigns.md`](docs/email-campaigns.md).
- **A REPL** — type `ghl` with no args and you get an interactive shell with autocomplete.
- **Checkout probe helpers** — `funnels checkout-assets` generates scoped CSS, Monthly-selection JS, and iframe HTML locally; `funnels serve-probe` serves only that HTML on loopback.
- **Workflow builders** — Python scripts that take a markdown file and turn it into a live GHL workflow (see `builders/`).
- **A one-line token helper** — a DevTools console snippet that exports the Firebase token you need for the "internal" GHL API (the public API can't create workflows; the internal one can). See [`docs/get-firebase-token.md`](docs/get-firebase-token.md).
- **A Claude Code skill** at `cli_anything/gohighlevel/skills/SKILL.md` so Claude can use the CLI on your behalf.

---

## Install (60 seconds)

Requirements: **Python 3.10+** and a GoHighLevel sub-account.

```bash
git clone <this repo> gohighlevel-cli
cd gohighlevel-cli
./install.sh
```

The installer creates a `.venv/`, installs the package, and initializes a
default credential profile at `~/.config/ghl/profiles/default.env` plus its
selector at `~/.config/ghl/config`. Set `GHL_CONFIG_DIR` to use a different
config root. Existing config files and profiles are left unchanged.

Open the resolved profile and fill in:

```env
GHL_API_KEY=pit-xxxxxxxx-...        # GHL Settings → Private Integrations
GHL_LOCATION_ID=YOUR_LOCATION_ID    # the long ID in your GHL URL
GHL_AGENCY_API_KEY=pit-xxxxxxxx-... # optional, agency SaaS reads only
```

The `ghl` wrapper resolves a profile from `GHL_PROFILE`, the nearest
`.ghlprofile`, or `default_profile` in the config file, in that order. It exits
if none resolves. For a one-off agency read, you can explicitly export
`GHL_AGENCY_API_KEY` instead of saving it in the profile.

Smoke test:

```bash
./ghl contacts list --limit 5
```

You should see 5 contacts (or an empty list, depending on the account). Done.

---

## Quickstart examples

```bash
# Contacts
./ghl contacts search --query "jay@"
./ghl contacts create --first-name Jay --last-name Test --email jay@test.com
./ghl contacts tags add --contact-id <id> --tag trial

# Workflows
./ghl --json workflows list
./ghl workflows enroll --contact-id <id> --workflow-id <id>

# Opportunities
./ghl opportunities list --pipeline-id <id>

# Conversations
./ghl conversations list --contact-id <id>

# Recurring payment subscriptions inside the current location
./ghl --json payments subscriptions --status active
./ghl --json payments subscription <subscription-id>

# Agency SaaS sub-account subscriptions and plans
./ghl --json saas locations --company-id <company-id>
./ghl --json saas subscription <location-id> --company-id <company-id>
./ghl saas audit --company-id <company-id>

# Lifecycle commands are dry-run by default. --apply still requires approval.
./ghl saas pause <location-id> --company-id <company-id>
./ghl saas disable <location-id> --company-id <company-id>
./ghl saas delete <location-id> --company-id <company-id> \
  --reason "Approved account closure" --keep-twilio-account

# Smart lists
./ghl --experimental --json smartlists list
./ghl --experimental smartlists create --name "Mailable" \
  --filter email:exists --filter tags:not_eq:blacklist,unsubbed

# Email campaigns — creates a DRAFT, never sends
./ghl --experimental emails create-campaign \
  --name "August newsletter" \
  --subject "{{contact.first_name}}, three deliverability checks" \
  --ab-subject "The 10-minute deliverability audit" \
  --from-name "Your Name" --from-email you@yourdomain.com \
  --html-file body.html --smart-list <smartListId>

# REPL (no args = interactive shell with autocomplete)
./ghl
```

`--json` works on most read commands and pipes cleanly into `jq`.

Payment subscriptions and agency SaaS subscriptions are separate records with
different credentials. SaaS reads are available directly, while lifecycle
writes are dry-run by default and require `--apply` plus interactive approval. See
[`docs/subscriptions.md`](docs/subscriptions.md) for the command and endpoint map,
token scopes, lifecycle safeguards, and the cancellation safety boundary.

## Testing

Install the development extra and run the suite with the Python interpreter
from this checkout. This single command works from a clean clone:

```bash
./install.sh --dev && .venv/bin/python -m pytest -q
```

Do not use the virtual environment from the separately installed skill as test
evidence for this checkout.

## Landing-page building (experimental)

The CLI can now create a funnel step, generate GHL builder-v2 page data from a compact
JSON design, save a draft, export full-fidelity builder JSON, and restore or clone an
export. It uses the same unofficial internal API and full-session Firebase credential
described below, so it is restricted to your own agency account.

New pages can start from an opinionated design system instead of a blank schema. It
includes simple and application VSLs, long-form sales letters, personalized roadmaps,
qualification applications, premium memberships, pricing, opt-in, calendar, and
onboarding/intake compositions; Otter, editorial, modern, and warm themes;
responsive previews; and a scored quality gate.

```bash
./ghl funnels templates
./ghl funnels init-template pricing --theme otter --output pricing.json
./ghl funnels lint pricing.json
./ghl funnels preview pricing.json --output pricing-preview.html
```

The rules for typography, spacing, alignment, graphics, icons, forms, pricing cards,
and accessible popups are in
[`docs/landing-page-design-system.md`](docs/landing-page-design-system.md).
The source-page audit and offer-matched funnel patterns are in
[`docs/reference-funnel-patterns.md`](docs/reference-funnel-patterns.md).

```bash
# Inspect the compact authoring format
cat examples/landing-page.example.json

# List pages and export a known-good page before changing it
./ghl --experimental --json funnels pages <funnel-id>
./ghl --experimental funnels export-page <page-id> --output page-backup.json

# Create a new step and draft page from compact JSON
./ghl --experimental funnels create-page <funnel-id> \
  --from-json examples/landing-page.example.json

# Replace an existing draft; add --publish only after visual review
./ghl --experimental funnels set-content <page-id> \
  --from-json examples/landing-page.example.json
```

Compact specs support `heading`, `subHeading`, `paragraph`, `bulletList`, `button`,
`image`, `video`, `divider`, `form`, `survey`, `calendar`, `countdown`, `timer`, `faq`,
`logoShowcase`, `customCode`, `oneStepOrder`, `twoStepOrder`, and
`orderConfirmation`. They also support page popups, background images/video, sticky
and responsive containers, custom CSS, tracking code, and native style/mobile
overrides.

Every current or future GHL element is available through the `native` escape hatch:

```bash
./ghl --experimental --json funnels elements <page-id>
./ghl --experimental funnels export-element <page-id> <element-id> --output native.json
```

Place that exported object in a compact spec's `elements` list. The builder assigns a
fresh ID while preserving its complete native schema. Global sections have matching
`export-global-sections` and guarded `set-global-sections --yes` commands.
See [`examples/landing-page-kitchen-sink.example.json`](examples/landing-page-kitchen-sink.example.json)
for a comprehensive example. `export-page` remains the lossless full-page path.
See [`docs/landing-page-spec.md`](docs/landing-page-spec.md) and
[`docs/funnel-page-internal-api.md`](docs/funnel-page-internal-api.md).

---

## Workflow building

Almost everything in this CLI runs on the official, scoped **Private Integration Token** (`GHL_API_KEY`) against GHL's public API — that's the safe default and all you need for contacts, opportunities, calendars, conversations, payments, enrolling contacts in existing workflows, and more.

The public API cannot create/update workflows or write page-builder content. There are two ways to handle that:

### Recommended: build once, ship a Snapshot

Build the workflow once in the GHL UI, then save it to a **Snapshot**. New sub-accounts inherit the workflow when you provision them from that Snapshot — no token, no internal API, nothing to leak. **This is the right path for provisioning client accounts**, and it covers the large majority of real use cases.

### Advanced (experimental): programmatic creation via the internal API

If you genuinely need to create workflows *programmatically* (e.g. generating sequences from markdown), the CLI can drive GHL's **internal** API. This is powerful but comes with real trade-offs — read the warning before you use it.

> ⚠️ **Use this on YOUR OWN agency account only.**
> - The Firebase refresh token is **your entire GHL login** (full account access), **not** a scoped key. Anyone who gets it can do anything you can.
> - **Never** paste a *client's* token, and never run the internal API against client sub-accounts. Provision client workflows with Snapshots instead.
> - It talks to GHL's **unofficial** internal API (`backend.leadconnectorhq.com`) — no SLA, may change or break without notice, and may run against GHL's ToS. Workflows are always created as **draft**.
> - Treat the token like a password. Prefer sourcing it from a secret manager or OS keychain rather than leaving it in the resolved profile. See [`docs/get-firebase-token.md`](docs/get-firebase-token.md).

### Step 1 — grab the token

Open `app.gohighlevel.com` (logged in), open DevTools (**⌘⌥J** / **Ctrl-Shift-J**), and paste this into the Console:

```js
(async () => {
  const db = await new Promise((res, rej) => {
    const r = indexedDB.open("firebaseLocalStorageDb");
    r.onsuccess = e => res(e.target.result);
    r.onerror = () => rej("Cannot open IndexedDB");
  });
  const entries = await new Promise((res, rej) => {
    const tx = db.transaction("firebaseLocalStorage", "readonly");
    const all = tx.objectStore("firebaseLocalStorage").getAll();
    all.onsuccess = () => res(all.result);
    all.onerror = () => rej("Failed to read store");
  });
  for (const e of entries) {
    const stm = (e?.value || e)?.stsTokenManager;
    if (stm?.refreshToken) {
      copy(stm.refreshToken); // DevTools copy() → clipboard
      console.log("✓ Refresh token copied. Paste into the resolved GHL profile as GHL_FIREBASE_REFRESH_TOKEN=");
      return;
    }
  }
  console.warn("No refresh token found — make sure you're logged into GHL.");
})();
```

It copies your refresh token to the clipboard. Paste it into the resolved
profile as `GHL_FIREBASE_REFRESH_TOKEN=...`. Full walkthrough:
[`docs/get-firebase-token.md`](docs/get-firebase-token.md).

### Step 2 — build a workflow

`builders/` has example builders that turn a markdown email-sequence doc into a live workflow:

```bash
# Course Interest sequence (10 emails, 14 days)
python builders/wf1-course-interest-builder.py

# High Ticket Interest sequence (5 emails + 1 SMS)
python builders/wf5-ht-interest-builder.py

# Post-Call Sales (3 tag-triggered branch workflows)
python builders/wf6-post-call-sales-builder.py

# Consulti free-trial nurture (8 emails)
python builders/consulti-nurture-builder.py

# Post-purchase nurture (6 emails)
python builders/post-purchase-nurture-builder.py
```

Each builder supports `--update` to re-deploy without creating a duplicate workflow.

---

## Project layout

```
gohighlevel-cli/
├── ghl                         # the executable wrapper
├── setup.py                    # package definition
├── install.sh                  # one-shot installer
├── scripts/
│   └── publish-installed-skill.sh  # checked revision publisher
├── .env.example                # credential profile template
│
├── cli_anything/               # the actual Python package
│   ├── gohighlevel/            # GHL commands (the main thing)
│   │   ├── gohighlevel_cli.py  # the CLI (all command groups)
│   │   ├── utils/              # API clients (public + internal + workflow builder)
│   │   └── skills/SKILL.md     # Claude Code skill manifest
│   ├── nextcloud/              # bonus: Nextcloud CLI
│   └── blotato/                # bonus: Blotato CLI
│
├── docs/
│   ├── get-firebase-token.md   # DevTools snippet for the internal-API token
│   └── email-campaigns.md      # campaigns, smart lists, and why send is not wired
│
└── builders/                   # example workflow builders
    ├── wf1-course-interest-builder.py
    ├── wf5-ht-interest-builder.py
    ├── wf6-post-call-sales-builder.py
    ├── consulti-nurture-builder.py
    ├── post-purchase-nurture-builder.py
    ├── email-sequences-doc-builder.py
    └── _email_sequences_parser.py
```

---

## Using it with Claude Code

The repo includes a Claude Code skill so Claude can call the CLI on your behalf:

1. Copy `cli_anything/gohighlevel/skills/SKILL.md` into a Claude Code skills directory (e.g. `~/.config/claude-accounts/gf-account/skills/gohighlevel-cli/SKILL.md`).
2. Add `ghl` to your shell's PATH (or symlink the `ghl` wrapper somewhere on PATH).
3. In any Claude Code session, say "use the gohighlevel-cli skill" and Claude will be able to run `ghl ...` for you.

## Publishing to the installed skill

The canonical source is this Git repository. The runtime used by the local
`ghl` symlink is a separate installed directory, normally
`~/.config/claude-accounts/gf-account/skills/gohighlevel-cli`, so merging a commit does not update it by
itself.

Inspect drift against an exact commit first. This is the default and does not
modify the target:

```bash
scripts/publish-installed-skill.sh --ref COMMIT_SHA
```

Publish that exact tracked revision only after the check is understood:

```bash
scripts/publish-installed-skill.sh --ref COMMIT_SHA --apply
scripts/publish-installed-skill.sh --ref COMMIT_SHA --check
```

Use `--target /absolute/path` for a non-default installation or a disposable
test target. Check mode can inspect any safe absolute target. Apply mode accepts
a custom target only when it is missing, empty, or already owned by a
`.published-git-revision` marker; it refuses repository paths and their
ancestors. A nonempty markerless default runtime may be bootstrapped only when
the logical default path is not a symlink and both installed identity files,
`SKILL.md` and `manifest.yaml`, are present. The publisher manages the tracked runtime, documentation,
examples, and tests. It deliberately preserves populated credentials (`.env`
and variants other than the tracked `.env.example`), `.venv`, caches, egg-info,
private `builders/`, the installed root `SKILL.md`, and `manifest.yaml`. It
never publishes to the separately curated
`~/.agents/skills/gohighlevel-cli` skill. The check compares the managed files
to the requested commit and verifies the installed revision marker.

After publishing, install dependencies and test inside the installed copy:

```bash
cd ~/.config/claude-accounts/gf-account/skills/gohighlevel-cli
./install.sh --dev
.venv/bin/python -m pytest -q
```

## Contract template authoring (experimental)

The CLI can create, read, export, update, and add signer fields to Documents &
Contracts templates. Supported compact fields are name/text, signature, date,
initials, and checkbox. Authoring uses GoHighLevel's unsupported UI service, so
it requires `--experimental` and a Firebase session. `GHL_IAM_TOKEN` is optional
and normally unset; see [docs/contracts.md](docs/contracts.md) for the measured
header behaviour.

Every `create-template` command saves five required fields on the final page:
company Date and Signature fields assigned to `assignedSender` / `users`, then
contractor Full name, Date, and Signature fields assigned to
`assignedContact` / `contacts`. The template editor displays the dynamic
contractor placeholder as order 1 and the sender placeholder as order 2, but a
template cannot enforce sequential signing. On each standalone document,
enable **Set signing order** and keep the contractor first and sender second
before saving or sending.
Existing correctly assigned matches are kept without duplication, matching
optional fields are promoted to required, and unassigned native matches are
repaired to the contractor placeholder.
The explicit `--name` overrides a top-level `name` in `--from-json`.

```bash
ghl --experimental --json documents create-template --name "Client Agreement"
ghl --experimental --json documents create-template \
  --name "Custom Agreement" --from-json examples/contract-template.example.json
ghl --experimental documents add-field TEMPLATE_ID --type signature --page 1
ghl --experimental documents export-template TEMPLATE_ID --output backup.json
ghl --experimental --json documents get-redirect TEMPLATE_ID
ghl --experimental --json documents set-redirect TEMPLATE_ID \
  --url https://example.com/complete --target existing-tab
```

Template exports always include the native completed-document redirect fields,
and redirect writes are fresh-read and verified. The commands create drafts only
and never publish or send automatically. See
[`docs/contracts.md`](docs/contracts.md) for authentication, the compact schema,
and safe native export/edit/import usage.

---

## Two layers of GHL API

The CLI talks to two APIs:

| API | What it can do | How it authenticates |
|-----|----------------|----------------------|
| **Public** (`services.leadconnectorhq.com`) | Read everything, create contacts/opportunities/etc. **Workflows are GET-only here.** | `GHL_API_KEY` (Private Integration Token) |
| **Internal UI services** | GHL UI operations including **creating workflows, forms, surveys, builder-v2 funnel pages, and contract templates**. Hidden behind `--experimental`. | Firebase JWT (`GHL_IAM_TOKEN` optional, normally unset) |

You only need session tokens for experimental internal-API builders. Everything else works with just the API key.

---

## Security notes

- The public API uses a **scoped Private Integration Token** (`GHL_API_KEY`) — revocable in the GHL dashboard without touching the rest of your session. Prefer it; it's all most workflows need.
- The Firebase refresh token is **your entire GHL login** (full account access), not a scoped key. **Use it on your own agency account only — never a client's**, and prefer Snapshots for provisioning client workflows (see [Workflow building](#workflow-building)).
- Treat the Firebase token like a password. Credential profiles live outside the repo and must never be committed. Prefer sourcing the token from a secret manager or OS keychain over leaving it at rest in a profile.
- The internal API (`backend.leadconnectorhq.com`) is **unofficial**: no SLA, may change or break without notice, and may run against GHL's ToS. It's gated behind `--experimental`, and the CLI prints a one-time warning when it's used (suppress with `GHL_SUPPRESS_INTERNAL_WARNING=1`).
- The token-grab snippet only **reads** from your own browser's IndexedDB on the GHL tab and uses the built-in DevTools `copy()` helper — it makes no network calls. See [`docs/get-firebase-token.md`](docs/get-firebase-token.md).

---

## License

Private / personal use.
