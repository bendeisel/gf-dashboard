# Subscription and SaaS sub-account management

The CLI exposes two different GoHighLevel subscription concepts. Payment
subscription commands remain read-only. The agency SaaS surface also provides
single-account lifecycle commands behind an approval wall.

| Surface | Meaning | Authentication |
|---|---|---|
| `payments subscription(s)` | Recurring purchases collected inside one location | Location-scoped `GHL_API_KEY` and `GHL_LOCATION_ID` |
| `saas` | The agency SaaS subscription, plan, and Stripe mapping for a sub-account | Agency/company-scoped `GHL_AGENCY_API_KEY` |

These records are not interchangeable. A payment subscription belongs to a
contact in one location. A SaaS subscription describes how the agency bills and
provisions the sub-account itself.

## Authentication

Keep the existing location token in `GHL_API_KEY`. For persistent use, add the
agency/company-scoped token to the profile resolved by the `ghl` wrapper. The
default install location is `~/.config/ghl/profiles/default.env`:

```env
GHL_API_KEY=pit-location-token
GHL_LOCATION_ID=location-id
GHL_AGENCY_API_KEY=pit-agency-token
```

Profile precedence is an explicit `GHL_PROFILE`, the nearest `.ghlprofile`, then
`default_profile` in `~/.config/ghl/config` or `$GHL_CONFIG_DIR/config`. The
wrapper exits if none resolves. For a one-off command, explicitly export
`GHL_AGENCY_API_KEY` in the invoking shell instead of saving it.

Requests under `/saas/` use `GHL_AGENCY_API_KEY` when it is set and otherwise
fall back to `GHL_API_KEY`. Lifecycle commands require the agency token
explicitly and do not fall back to the location token. A normal location
Private Integration Token is not authorized for these agency SaaS endpoints.
SaaS operations use the API's required `Version: v3` header.

## Payment subscriptions in a location

List and filter recurring payment subscriptions:

```bash
ghl --json payments subscriptions
ghl --json payments subscriptions --contact-id CONTACT_ID --limit 50 --offset 0
ghl --json payments subscriptions --status active
```

Read one subscription:

```bash
ghl --json payments subscription SUBSCRIPTION_ID
```

`--status` is intentionally a free-form pass-through. It was validated against
the live API for `active` and `canceled` on 2026-08-30, but GoHighLevel's current
public parameter table does not list the field or publish a complete status
enum. An unsupported value is rejected by the server instead of being silently
accepted by the CLI.

### Inspect an applied payment discount

```bash
ghl --json payments subscription-discount SUBSCRIPTION_ID \
  --expect-contact-id CONTACT_ID --expect-coupon-code COUPON_CODE
```

This GET-only command verifies the returned subscription ID and location, plus
the exact contact ID and `coupon.code` when supplied. Missing or mismatched
expected fields produce a nonzero exit. It returns the complete subscription
unchanged, including GHL's coupon, schedule, product and provider snapshots.
The public schema leaves these nested objects largely unspecified, so the CLI
does not derive a next charge, discount end date or number of free cycles from
them. A null Stripe discount does not establish that the GHL discount ended.

There is no `--apply` or subscription discount write route. For an explicitly
approved adjustment, use the subscription's own screen in real Chrome signed
in as the owner. Verify every supplied target value before changing anything:
location, contact identity, subscription IDs, status, creation time, product,
price and applied coupon terms. API evidence supplements this UI check.

Prefer editing only the applied discount's duration. If the UI supports replacing
the applied coupon, create a replacement only with explicit authorization for
its code, percentage, duration, product scope, usage limit and expiry, and only
when the UI clearly confirms no charge today. Stop if it offers only removal,
or mentions immediate charges, proration or an invoice. Do not modify the shared
coupon definition, subscription status, product, price or SaaS sub-account.

Save before and after subscription screenshots to the requested evidence
directory. The after screenshot must show the approved duration or end date,
and the next charge date and amount must be reported exactly as GHL displays
them. If no supported control exists, report the controls offered with screenshots
and leave the subscription unchanged. An inspection result is never proof that
the discount was changed. Keep customer-specific exports and evidence outside Git.

In one live UI review on 2026-09-14, the Update subscription dialog showed the
applied coupon as static text, a disabled start date, an editable subscription
end date and product/quantity controls. It also showed a "Next invoice" preview.
No discount-duration or coupon-replacement control was visible, so the review
stopped without changes under the owner's no-invoice condition. A subscription
end date is not a discount end date. This observation does not establish that
every HighLevel account or future UI has the same controls.

## Agency SaaS sub-accounts and plans

Read commands in this group include:

```bash
# List SaaS-enabled sub-accounts
ghl --json saas locations --company-id COMPANY_ID --page 1

# Read the SaaS subscription attached to one location
ghl --json saas subscription LOCATION_ID --company-id COMPANY_ID

# Map a Stripe identifier back to a location
ghl --json saas find-location --company-id COMPANY_ID \
  --subscription-id STRIPE_SUBSCRIPTION_ID
ghl --json saas find-location --company-id COMPANY_ID \
  --customer-id STRIPE_CUSTOMER_ID

# Inspect agency plans
ghl --json saas plans --company-id COMPANY_ID
ghl --json saas plan PLAN_ID --company-id COMPANY_ID
```

`saas find-location` requires at least one Stripe customer or subscription ID.
This avoids an accidental broad lookup when the operator intended to resolve a
single billing record.

## Sub-account lifecycle commands

Pause, disable, and delete are available through documented public APIs. Each
command targets one literal location ID, prints the complete target evidence,
and defaults to a dry run. A write requires `--apply`, then an interactive
approval. There is no `--yes`, bulk input, file input, or glob mode. JSON is
available for dry runs; `--json --apply` is rejected so approval remains human
readable and interactive.

```bash
# Preview only
ghl saas pause LOCATION_ID --company-id COMPANY_ID
ghl saas disable LOCATION_ID --company-id COMPANY_ID
ghl saas delete LOCATION_ID --company-id COMPANY_ID \
  --reason "Approved account closure" --keep-twilio-account

# Write only after the target preview and interactive approval
ghl saas pause LOCATION_ID --company-id COMPANY_ID --apply
ghl saas disable LOCATION_ID --company-id COMPANY_ID --apply
ghl saas delete LOCATION_ID --company-id COMPANY_ID --apply \
  --reason "Approved account closure" --delete-twilio-account
```

Every lifecycle command refuses your protected location
(`GHL_PROTECTED_LOCATION_ID`, or `GHL_LOCATION_ID` when that is unset). Disable exports the current wallet balance and complete
location wallet ledger to a private JSON file before it sends the write. Delete
requires an already paused account, no active subscription on either billing
side, an explicit Twilio choice, a meaningful reason, and typed confirmation of
the exact location name. A fresh read must prove the resulting state before the
command reports success. See [`subaccount-lifecycle.md`](subaccount-lifecycle.md).

## Endpoint map

| Command | Official endpoint |
|---|---|
| `payments subscriptions` | `GET /payments/subscriptions` |
| `payments subscription ID` | `GET /payments/subscriptions/{subscriptionId}` |
| `saas locations` | `GET /saas/saas-locations/{companyId}` |
| `saas find-location` | `GET /saas/locations` |
| `saas subscription` | `GET /saas/get-saas-subscription/{locationId}` |
| `saas plans` | `GET /saas/agency-plans/{companyId}` |
| `saas plan` | `GET /saas/saas-plan/{planId}` |
| `saas pause` | `POST /saas/pause/{locationId}` |
| `saas disable` | `POST /saas/bulk-disable-saas/{companyId}` |
| `saas delete` | `DELETE /locations/{locationId}` |
| disable wallet balance preflight | `GET /saas-api/public-api/companies/{companyId}/locations/{locationId}/wallet-balance` |
| disable wallet ledger preflight | `POST /saas/locations/{locationId}/wallet-transactions` |

Official references:

- [List payment subscriptions](https://marketplace.gohighlevel.com/docs/ghl/payments/list-subscriptions/index.html)
- [Get a payment subscription](https://marketplace.gohighlevel.com/docs/ghl/payments/get-subscription-by-id/)
- [SaaS API overview](https://marketplace.gohighlevel.com/docs/ghl/saas-api/saa-s/index.html)
- [Pause a location](https://marketplace.gohighlevel.com/docs/ghl/saas-api/pause-location/index.html)
- [Disable SaaS](https://marketplace.gohighlevel.com/docs/ghl/saas-api/bulk-disable-saas/index.html)
- [Delete a sub-account](https://marketplace.gohighlevel.com/docs/ghl/locations/delete-location/index.html)

## Cancellation boundary

This release does not add a cancel command. GoHighLevel does not document a
public cancellation route for location payment subscriptions, and the exact UI
service request has not been captured. The CLI does not guess money-moving API
paths. Route discovery can itself cancel a real subscription, so it requires a
separately approved active target and a dedicated safety pass.

Direct Stripe cancellation is not a supported workaround. A read-only-key
attempt on 2026-08-30 returned `more_permissions_required` because the live
restricted key did not have `subscription_write`. Expanding a live money key's
permissions requires the account owner's explicit approval. Even with that permission,
cancelling in Stripe could leave GoHighLevel's SaaS subscription record out of
sync with its billing state. GoHighLevel remains the system of record for SaaS
sub-accounts, so until the GHL cancellation request is captured and safely
implemented, cancellations must be performed in the GoHighLevel UI only.

Any future cancellation command must default to dry-run, require an explicit
apply flag, refuse non-active records, confirm the subscriber email, target one
ID only, and fresh-read the subscription after the write before reporting
success.
