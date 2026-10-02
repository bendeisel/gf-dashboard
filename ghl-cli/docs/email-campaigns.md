# Email campaigns and smart lists

Reference for `ghl --experimental emails …` and `ghl --experimental smartlists …`.

Everything here rides GHL's **internal** API (`backend.leadconnectorhq.com`), so it needs
`--experimental` and a Firebase token — see [`get-firebase-token.md`](get-firebase-token.md).
All internal email routes require the header `Version: 2021-07-28`; omit it and you get
`401 version header was not found`, which reads like an auth failure but isn't.

---

## The one thing to know first

**Creating a campaign and sending it are different endpoints.**

| | Endpoint |
|---|---|
| Create draft | `POST /emails/schedule` |
| Save draft settings | `PATCH /emails/schedule/{loc}/{id}` — the payload with `isSave: true` |
| **Send** | `POST /emails/schedule/start` — the same payload with `isSave: false` |

The CLI wraps the first two and **not** the third. No `ghl` invocation can dispatch mail;
every campaign it makes stops at `draft` for a human to send from the UI.

Do not add a send command "for completeness". A single request to `/emails/schedule/start`
goes to the entire bound list, however large that is. Verify your recipient scope before
allowing any send flow via the UI.

---

## Quickstart

```bash
# What can I send to?
ghl --experimental --json smartlists list

# Draft a campaign against one of them
ghl --experimental emails create-campaign \
  --name "August newsletter" \
  --subject "{{contact.first_name}}, three deliverability checks" \
  --ab-subject "The 10-minute deliverability audit" \
  --from-name "Your Name" \
  --from-email sender@example.com \
  --html-file body.html \
  --smart-list <smartListId>

# Inspect / remove
ghl --experimental --json emails get-campaign <campaignId>
ghl --experimental emails delete-campaign <campaignId> --template-id <templateId>
```

`create-campaign` prints the `campaignId`, `templateId`, a Firebase `previewUrl` for the
rendered HTML, and an `editUrl` that opens the draft in GHL.

The draft's UI route is:

```
https://<app domain>/location/<locationId>/emails/campaigns/create/<campaignId>/schedule
```

No `/v2` segment, and campaigns sit under `emails/campaigns/create/`, not `marketing/emails/`.
Corrected 2026-09-15: the CLI had built a `/v2/location/.../marketing/emails/schedule/<id>` URL
that matches no route, and it was handed to Jay as the one click that sends a campaign. Other GHL
screens **do** use `/v2/location/<loc>/...` (contacts, workflows, payments), so the wrong form
looked right next to them.


---

## Defaults that are on unless you turn them off

These encode house style. Where a default can't be satisfied, the command **errors**
rather than quietly producing the lesser thing.

| Default | Turn off with | Notes |
|---|---|---|
| **Subject-line A/B** | `--no-ab-test` | At least one `--ab-subject` is required — a one-variation "test" is not a test |
| **UTM tracking** | `--no-utm` | Sets `hasUtmTracking`; appends the location's default UTM params |
| **First-name fallback** | `--first-name-fallback "..."` | Every `{{contact.first_name}}` is rewritten to the safe form (below) |
| Click tracking **off** | `--click-tracking` | Matches how these campaigns are actually sent |

Copy containing no first-name merge field at all is rejected; pass
`--allow-no-personalization` if that is genuinely intended.

A/B knobs: `--ab-test-size` (percent of list used for the test, default 50),
`--ab-test-hours` (default 4), `--ab-winning-criteria` (`openRate` | `clickRate`).

---

## Merge fields: always use the `default` helper

GHL registers a Handlebars `default` helper. This is valid anywhere GHL renders:

```handlebars
{{default contact.first_name "there"}}
```

It substitutes the fallback when the value is `null`, `undefined` **or the empty string**.
That last case is the one that actually bites: a contact with a *blank* `first_name` is far
more common than one missing the field, and a bare `{{contact.first_name}}` renders
`Hi ,` in their subject line.

You don't need to write the helper yourself. Write `{{contact.first_name}}` in the subject,
preview text or body and `create-campaign` rewrites it — idempotently, so re-running on
already-converted copy is safe.

> GHL's UI records the same intent out-of-band in `scheduleOptions.fieldDefaults`, keyed
> `"<variable>:<occurrenceIndex>"` under `fromName` / `subjectLine` / `previewText` /
> `fromAddress`. Writing the helper inline is equivalent, additionally covers the **body**
> (which `fieldDefaults` does not), and doesn't depend on that bookkeeping staying in sync.

---

## A campaign is two records

Not one. This is the single most useful thing to internalize:

1. **Template** — `POST /emails/builder` → `{redirect: id}`. Owns the HTML.
2. **Body** — `POST /emails/builder/data` → uploads to Firebase Storage, returns `previewUrl`.
3. **Campaign** — `POST /emails/schedule` → `{id}`, points at the template via `templateId`.
4. **Settings** — `PATCH /emails/schedule/{loc}/{id}` with subject, sender, recipients.

`delete-campaign --template-id` removes both; without the flag the template is orphaned.

### Recipients

Bound on the campaign, not at send time:

| Flag | Stored as |
|---|---|
| `--smart-list ID` | `filters: {filters: <the list's own leaves>, id: ID, assigned_to}` |
| `--tag a --tag b` | `filters: {filters: [{field:"tags",operator:"eq",value:[a,b]}], assigned_to}` |
| neither | `filters: {filters: [], assigned_to}` — **every contact** |

`create-campaign` warns on stderr if the smart list you named has no filters, because that
is indistinguishable from "send to everyone".

---

## Endpoint map

| Verb + path | Purpose |
|---|---|
| `POST /emails/builder` | create template shell |
| `POST /emails/builder/data` | save HTML → `{previewUrl, templateDataDownloadUrl}` |
| `GET /emails/builder/html/{loc}/{id}/{ver}` | rendered HTML (**raw HTML, not JSON**) |
| `DELETE /emails/builder/{loc}/{id}` | delete template |
| `POST /emails/schedule` | create campaign |
| `GET /emails/schedule/{loc}/{id}` | campaign incl. `meta.filters`, `meta.abTestInfo` |
| `PATCH /emails/schedule/{loc}/{id}` | save draft settings |
| `PUT /emails/schedule/meta/{id}` | rename only |
| `DELETE /emails/schedule/{loc}/{id}` | delete campaign |
| `PUT /emails/schedule/action/{pause\|resume}/{loc}/{id}` | pause / resume |
| `PUT /emails/schedule/action/cancel/{loc}/{id}` | cancel a scheduled send |
| `PUT /emails/schedule/action/toggle-archive/{loc}/{id}` | archive |
| `POST /emails/schedule/clone` | duplicate |
| `POST /emails/schedule/create-ab-variation` | variation with its own body |
| `GET /contacts/smartlist/search?locationId=&userId=&globals=true&transform=true` | smart-list collection |
| `POST /contacts/smartlist` | create smart list |
| `POST https://api.leadconnectorhq.com/smartlist/delete` | delete — **different host**, `{smartlist_id}` |
| `POST /contacts/search/2` | count contacts matching a filter set |

⛔ Not in this table on purpose: `POST /emails/schedule/start`.

---

## Smart lists

```bash
ghl --experimental smartlists create --name "Mailable" \
  --filter email:exists \
  --filter valid_email:eq:true \
  --filter dnd:not_eq:true \
  --filter tags:not_eq:blacklist,unsubbed
```

`--filter` is `field:operator[:value]`, repeatable, ANDed. A comma-separated value becomes
an array with `minimumMatch: 1`; `true`/`false` become real booleans; colons inside values
survive, so URLs work. Fields may be dotted (`dnd_settings.Email.status`).

Nesting matters and is handled for you: GHL wants **OR-group → AND-group → leaves**. A flat
filter array is accepted and silently matches everything.

**With no `--filter` the list matches every contact** — which is what the GHL UI does for a
brand-new list, but it is not a smart list. Verify a filter actually narrows by comparing
counts before trusting it.

---

## Traps

Each of these produced a wrong result that looked like a right one.

- **`abTestInfo` spellings are not guessable, and wrong ones are accepted silently.**
  `testType` is `"emailSubject"` (camelCase, not `email_subject`); `testDuration` is in
  **seconds**; `testSize` is a percent; `winningCriteria` is `openRate`/`clickRate`; an
  undecided test carries `winningVariationIndex: -1`. The API stores unknown keys without
  complaint, so a guessed spelling produces a campaign the UI cannot interpret and no error
  anywhere. **When a payload shape is uncertain, read an existing UI-created record.**

- **`documentId` is absent from the create response.** It appears only on the next `GET`.
  Reading it off the create response writes `null` into every A/B variation — variants with
  no body.

- **`/emails/builder/html/...` returns raw HTML.** A client that assumes JSON, or truncates
  non-JSON bodies, will "verify" an upload against nothing. Verify via the `previewUrl`
  returned by the save call instead.

- **GHL list endpoints are eventually consistent.** Never confirm a write with an immediate
  read-back; a successfully deleted record still appears in a list for seconds.

- **The email UI is a cross-origin iframe** (`email-home-prod.leadconnectorhq.com`), so a
  fetch interceptor injected into the parent page never sees these calls, and the iframe
  renders blank if loaded directly (it needs the parent's postmate handshake). The whole
  surface above was recovered by reading the app's own JS bundles
  (`/assets/index-*.js` on `email-home-prod` and `email-builder-prod`) — faster than UI
  clicking, complete rather than whatever one flow happens to call, and with no risk of
  triggering a send while probing.

