# SaaS sub-account lifecycle commands

The CLI exposes three single-account lifecycle actions through HighLevel's
documented public v3 API:

- `saas pause` pauses one sub-account.
- `saas disable` disables SaaS mode for one sub-account.
- `saas delete` deletes one sub-account from the agency.

These commands are available, but writes sit behind an approval wall. Dry-run
is the default. `--apply` is necessary but not sufficient: the operator must
also approve the exact target interactively. There is no bulk mode or approval
bypass. `--json` is supported for dry runs, but is rejected with `--apply`
because an applied action must use the human-readable interactive approval.

## Shared target evidence

Every command reads and prints the target before it can write:

- location ID, exact name, and creation date;
- SaaS mode, SaaS subscription ID, and SaaS subscription status;
- matched billing-location payment subscription IDs and statuses;
- latest successful live payment date and amount;
- any join or read errors.

The billing relationship follows the audit's contact-ID-first join. Exact
normalized email is only a fallback when the SaaS record has no GoHighLevel
contact ID. Any unresolved or ambiguous evidence blocks an applied action.

Your own location is protected from all three commands: `GHL_PROTECTED_LOCATION_ID`
if set, otherwise the profile's `GHL_LOCATION_ID`.

## Pause

```bash
ghl saas pause LOCATION_ID --company-id COMPANY_ID
ghl saas pause LOCATION_ID --company-id COMPANY_ID --apply
```

The command prints these consequences before both dry runs and applied actions:

1. Location admins and users lose login access; agency users retain access.
2. Published funnel pages and live automations are moved to Draft.
3. Phone numbers and A2P registrations are deleted after 14 days, and unpausing
   after that point does not restore them.
4. Reselling, marketplace, and SaaS subscriptions are canceled and require new
   subscriptions to resume.

After an approved write, a fresh read must show the location as paused.

## Disable SaaS mode

```bash
ghl saas disable LOCATION_ID --company-id COMPANY_ID
ghl saas disable LOCATION_ID --company-id COMPANY_ID --apply
```

Disabling SaaS can remove wallet transaction history and forfeit remaining
balance or credits. Before an applied write, the CLI therefore reads the wallet
balance and every page of the location wallet ledger, saves both to a unique
private JSON file, and prints its path. The write is not attempted if the read,
pagination, or file export fails.

After approval, the command disables only the one supplied location ID and
fresh-reads agency state. It reports success only after the location is no
longer SaaS-enabled while the underlying location still exists.

## Delete

```bash
ghl saas delete LOCATION_ID --company-id COMPANY_ID \
  --reason "Approved account closure" --keep-twilio-account

ghl saas delete LOCATION_ID --company-id COMPANY_ID --apply \
  --reason "Approved account closure" --delete-twilio-account
```

The operator must explicitly choose whether the HighLevel delete request also
deletes the Twilio account. Delete additionally refuses to apply unless:

- the target is already paused;
- neither the SaaS side nor the billing-location payment side is active;
- the reason meets the minimum length;
- the operator types the exact location name at the final prompt.

After the approved write, a fresh agency read must prove that the location is
absent. A successful write response alone is never treated as completion.

## Public endpoint map

| Action | Endpoint |
|---|---|
| Pause | `POST /saas/pause/{locationId}` |
| Disable SaaS | `POST /saas/bulk-disable-saas/{companyId}` |
| Delete sub-account | `DELETE /locations/{locationId}` |
| Wallet balance | `GET /saas-api/public-api/companies/{companyId}/locations/{locationId}/wallet-balance` |
| Location wallet ledger | `POST /saas/locations/{locationId}/wallet-transactions` |

References: [pause](https://marketplace.gohighlevel.com/docs/ghl/saas-api/pause-location/index.html),
[disable SaaS](https://marketplace.gohighlevel.com/docs/ghl/saas-api/bulk-disable-saas/index.html),
[delete sub-account](https://marketplace.gohighlevel.com/docs/ghl/locations/delete-location/index.html),
[wallet balance](https://marketplace.gohighlevel.com/docs/ghl/saas/get-location-wallet-balance/),
and [wallet ledger](https://marketplace.gohighlevel.com/docs/ghl/saas-api/list-location-wallet-transactions/index.html).

## Boundary

These actions do not cancel the separate payment subscription created by the
billing-location funnel. GoHighLevel does not document a public cancel route
for that payment record. The CLI does not infer that pause, disable, or delete
has canceled billing, and it does not use Stripe as a workaround.
