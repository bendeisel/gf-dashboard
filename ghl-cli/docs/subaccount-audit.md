# SaaS sub-account billing audit

`ghl saas audit` is a read-only reconciliation of two separate HighLevel
records:

1. The agency SaaS subscription attached to a sub-account.
2. The payment subscription created by the sale funnel in the billing
   location.

Canceling the payment subscription does not prove that the sub-account was
paused or removed. The audit keeps both sides visible so a human can review the
difference.

## Authentication

The command requires two Private Integration Tokens with read scopes:

- `GHL_AGENCY_API_KEY`: agency token used for SaaS and agency location reads.
- `GHL_API_KEY`: billing-location token used for payment subscriptions and
  transactions.

The local wrapper reads these from the selected profile under
`~/.config/ghl/profiles/`. If the agency token is stored in Doppler under a
different variable name, map it for the command without printing it:

```bash
GHL_AGENCY_API_KEY="$(doppler secrets get GHL_AGENCY_API --plain \
  --project web-builder --config prd)" \
  ghl saas audit --company-id kCaHCjCY7SAmYVjtV8Vo
```

## Usage

```bash
# Complete table
ghl saas audit --company-id kCaHCjCY7SAmYVjtV8Vo

# Structured report
ghl --json saas audit --company-id kCaHCjCY7SAmYVjtV8Vo | jq .

# Add an authoritative comp ledger export
ghl saas audit --company-id kCaHCjCY7SAmYVjtV8Vo \
  --comped-emails-file deal-grants.txt
```

The billing location defaults to `GHL_LOCATION_ID` and the payment product to
`GHL_SAAS_PRODUCT_ID`; pass `--billing-location-id` or `--product-id` to override
either. `--comped-emails-file` accepts one email per line or a JSON list of
strings. Internal domains come from `GHL_INTERNAL_DOMAINS` (comma-separated) or
repeated `--internal-domain` flags. Set `GHL_SAAS_BASELINE` to your expected
`subscriptions/contacts`, for example `280/250`, to turn on the population check;
without it the check reports `unchecked`.

## Join and evidence rules

The two subscription IDs are not the same identifier. A live read on
2026-08-31 found zero overlap between the 165 agency SaaS subscription IDs and
the 281 funnel payment subscription IDs in the reference account. The audit therefore:

- preserves both IDs;
- **joins on the GoHighLevel contact id**, taken from `customerId` on the SaaS
  subscription detail;
- falls back to an exact normalized-email match only when a location carries no
  contact id, and records which key each row actually used in `join.method`;
- never joins by name or fuzzy text;
- lists unmatched payment records as diagnostics instead of inventing a
  location row.

### Why contact id, and where it stops

Email is the wrong key, and this audit exists because of it. On 2026-08-30 a member
took a second free sub-account under a second address, and nothing keyed on email
could see the two were one person. GoHighLevel had already resolved that identity:
it **merges contacts on phone**, so both subscriptions hung off one contact id. That
id is on the SaaS subscription record, so the join needs no lookup and no fuzzy
matching.

Merging cuts both ways. Two unrelated people sharing a phone number land on one
contact, and that contact can then own several SaaS locations. Attributing one
active subscription to all of them would invent a payment that is not there. So when
a contact owns more than one location:

1. if the location's **own** SaaS subscription is `active` or `trialing`, that is
   per-location evidence and the shared contact is irrelevant;
2. otherwise the contact's active payment subscriptions must number at least as many
   as its locations;
3. failing both, the row is `unknown`. Which location is covered is genuinely not
   knowable from here, and a guess would be the one error that gets a paying
   customer paused.

Rule 1 is not an optimisation. Without it the first live run demoted a paying
account to `unknown`, because the shared-contact check counted only payment
subscriptions and that location was paid through its own SaaS subscription.

The last invoice fields come from the latest successful live payment
transaction returned for the matched payment subscription. A missing invoice
ID remains null. The transaction date and amount are still retained as the
read evidence.

When a payment subscription list row omits its product ID, the audit fresh-reads
the linked order and uses the internal product ID from its items. If that read
still cannot prove exactly one product, the population check fails and every
classification is withheld.

## Classifications

- `active-paid`: the location is live and either subscription side is `active`
  or `trialing`.
- `active-unpaid`: the location is live and neither side is active.
- `active-past-due`: neither side is active, but one is `past_due`. Held apart from
  `active-unpaid` deliberately. A failed card is not a decision to leave, it is
  recoverable revenue, and pausing the account deletes its phone numbers and A2P
  registrations after 14 days.
- `active-comped`: no side is active, but the exact email is present in the
  supplied comp ledger or uses an exact internal domain.
- `paused/deleted`: a returned lifecycle or subscription field explicitly says
  `paused` or `deleted`.
- `unknown`: a required read failed, the list and detail reads disagreed, the
  exact-email join was not one-to-one, lifecycle evidence was blank, or an
  undocumented status was returned.

No classification says that an account should be closed. The report is review
evidence, not an action queue.

The public SaaS list does not return deleted locations, so the command cannot
enumerate locations already removed from HighLevel. It states that limitation
in every report.

## Population safety check

The 2026-08-30 baseline is 281 payment subscriptions across 249 contacts. The
report records the baseline and current counts. Counts between 75 and 150
percent of both baselines are marked `near`; a larger difference is `failed`.
On failure, the command still emits diagnostic rows but withholds the
classification summary and exits nonzero. This prevents a bad product filter
or response join from being presented as a business finding.

## Safety boundary

The audit command only performs GET requests. It has no `--apply`, bulk action,
billing, refund, or cancellation path. Separate single-account pause, disable,
and delete commands are documented in
[`subaccount-lifecycle.md`](subaccount-lifecycle.md). They consume the same
target evidence but remain dry-run by default and require action-time approval.
