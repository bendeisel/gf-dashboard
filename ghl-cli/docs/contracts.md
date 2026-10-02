# Contract template authoring

GoHighLevel's public Documents & Contracts API supports listing and sending
templates, but it does not publish template authoring endpoints. The commands
on this page use the same UI service and native element schema as the current
GoHighLevel template builder. They are unsupported by GoHighLevel, can change
without notice, and are therefore gated by `--experimental`.

These commands never publish or send a template. Writes are followed by a
fresh read so the CLI returns the persisted record, not the submitted payload.

## New-draft signer fields

`create-template` always saves five required fields on the final page:

- Company Date, a native `DateField` assigned to `assignedSender` / `users`
- Company Signature, a native version 2 `Signature` assigned to the sender
- Contractor Full name, a native `TextField` assigned to `assignedContact` / `contacts`
- Contractor Date, a native `DateField` assigned to the contractor
- Contractor Signature, a native version 2 `Signature` assigned to the contractor

Both Date fields use `yyyy-MM-dd`; both Signature fields use `showName: true`.
The defaults are idempotent: correctly assigned matching fields already on the
final page keep their ids, positions, assignments, and styling. Contact fields
cannot satisfy sender defaults, and sender fields cannot satisfy contractor
defaults. Matching optional fields are promoted to required. Unassigned native
semantic matches are repaired to the contractor placeholder.

Missing fields are placed at top positions 650, 692, 790, 832, and 874 on a
Letter page. The company fields appear before the contractor fields visually.
The current template builder displays `assignedContact` as order 1 and
`assignedSender` as order 2, but these are editor-only placeholders and a
template does not persist the sequential-signing switch. After converting the
template into a standalone document, select the contractor as the primary
contact, enable **Set signing order**, keep the contractor first and the sender
second, and save the draft. Creating a template with no JSON file still performs
a content update and a fresh read to verify the five fields persisted.

## Authentication

Template authoring needs the Firebase session and nothing else:

- `GHL_FIREBASE_REFRESH_TOKEN` and `GHL_FIREBASE_API_KEY` provide `token-id`.
- `GHL_IAM_TOKEN` is **optional** and normally unset.

This page previously said an IAM bearer was required. Measured against the live
proposal service on 2026-08-24 with a read-only template GET:

| headers sent | result |
|---|---|
| `token-id` only, no `Authorization` | **200**, full template |
| `token-id` + Firebase ID as bearer | 200, full template |
| Firebase ID as bearer, no `token-id` | 401 `Error calling IAM service` |

`token-id` is what authenticates. The requirement was never tested because the
client raised before sending a request, so the assumption could not be
contradicted by anything. A *stale* IAM token is worse than none, since the
service tries to resolve a bearer whenever it receives one: if a contract
command 401s and `GHL_IAM_TOKEN` is set, unset it and retry before hunting for
a fresh one.

Two things that do bite, and are not credentials:

- **Cloudflare 1010** on a non-browser User-Agent. The client sends a Chrome UA;
  a hand-rolled `curl` or `urllib` call to this service will 403 with `error
  code: 1010` and read exactly like an auth failure.
- These routes are on `services.leadconnectorhq.com`, not the `backend.` host
  most internal routes use.

Follow [get-firebase-token.md](get-firebase-token.md). Use these credentials
only on your own agency account and treat them like a password.

Fresh template shells do not include a timezone even though GoHighLevel
requires one on update. The CLI uses the computer's timezone by default. Set
`GHL_CONTRACT_TIMEZONE` to an IANA zone such as `America/New_York` when the
location uses a different timezone.

## Commands

```bash
ghl --experimental --json documents get-template TEMPLATE_ID
ghl --experimental documents export-template TEMPLATE_ID --output backup.json
ghl --experimental --json documents create-template --name "Client Agreement"
ghl --experimental --json documents create-template \
  --name "Client Agreement" \
  --from-json examples/contract-template.example.json
ghl --experimental --json documents update-template TEMPLATE_ID --from-json changes.json
ghl --experimental --json documents get-redirect TEMPLATE_ID
ghl --experimental --json documents set-redirect TEMPLATE_ID \
  --url https://yourdomain.com/welcome-call \
  --target existing-tab
ghl --experimental --json documents add-field TEMPLATE_ID \
  --type signature --page 1 --top 850 --left 80 --recipient CONTACT_ID
```

## Reading a SIGNED document, which no command does yet (2026-09-11)

`documents list --query <name>` finds the sent copies (public API, `status: completed`,
`recipients[].hasCompleted`), but returns no page text. The text a client actually signed
comes from the same UI service as the template commands, at the **singular** path:

```
GET {PROPOSAL_SERVICE_URL}/document/{DOCUMENT_ID}?locationId={LOCATION_ID}
```

`/documents/{id}` (plural) 404s. The response wraps the record as `{"document": {...}}` with
`recipients[].hasCompleted`, `fillableFields[].value` (the typed name and the date) and the
pages, so the text can be diffed against the template a later session would otherwise assume
was signed. Verified on a January 2026 signature against the `High Ticket 2025 - Link Copy`
template: the signed copy had no §6 Non-Disparagement and one fewer clause on the parties
line. Until a `documents get` command exists, call it from the skill's venv:

```python
from cli_anything.gohighlevel.utils.ghl_internal_client import (
    PROPOSAL_SERVICE_URL, InternalGHLClient, TokenManager)
client = InternalGHLClient(TokenManager(), LOCATION_ID)
doc = client._proposal_request("GET", f"{PROPOSAL_SERVICE_URL}/document/{DOC_ID}?locationId={LOCATION_ID}")["document"]
```

Two related limits met the same day: `documents templates --limit` rejects anything over
**21** (`422: limit must not be greater than 21`), and `forms submissions` returned only the
most recent 40 for the High Ticket intake, so a January submission was absent. The answers
are still on the contact: `forms get FORM_ID` (experimental) gives field id to label, and the
contact's `customFields` carry the values. Custom fields are shared across forms, so a later
intake on the same contact can overwrite them.

`set-redirect` writes the builder-native completed-document redirect and then
fresh-reads the template. It fails if GHL accepts the request without persisting
the URL, enabled flag, or tab target. `export-template` always includes those
three `redirectSettings` fields, even when redirection is disabled, so a JSON
round trip cannot silently drop the setting.

Supported compact field types are `name`, `text`, `signature`, `date`,
`initials`, and `checkbox`. `name` is a friendly alias for GoHighLevel's native
`TextField` with a `Full name` placeholder. GoHighLevel has no separate name
element type. When no recipient is supplied, fields are assigned to GHL's
dynamic template contact (`assignedContact`), matching the template editor.
Fields in the input are additive. If the input omits any of the five default
fields, `create-template` adds the missing party-specific fields on the final page.
The required `--name` option is authoritative and overrides a top-level `name`
inside `--from-json`, keeping the shell and persisted record consistent.
For uploaded PDF drafts assembled in the browser, add the same five required
fields immediately before saving and fresh-read the draft to verify persistence.

Common field properties:

```json
{
  "type": "text",
  "page": 1,
  "label": "Legal business name",
  "placeholder": "Enter legal business name",
  "fieldId": "legal_name",
  "recipient": "contact-or-role-id",
  "entityName": "contacts",
  "required": true,
  "top": 700,
  "left": 80,
  "width": 240,
  "height": 26
}
```

For a safe native workflow, export first, edit the exported JSON, and pass it
to `update-template`. The CLI uses the current builder's explicit PUT root
whitelist and preserves unknown nested fields inside those supported roots.
Response-only metadata and unknown root properties are not replayed because
GoHighLevel rejects them.

Signer-field and ordinary content edits are supported. Native edits that add,
remove, or change `ProductList` elements are rejected because GoHighLevel's
browser builder also recalculates pricing and payment metadata during those
changes. Make product-table changes in the GoHighLevel editor.
