"""Pure helpers for the read-only SaaS sub-account billing audit.

The agency SaaS subscription and the funnel payment subscription are different
objects. Live LGJ evidence showed zero overlap between their subscription IDs,
so both sides remain separate and are associated only by exact normalized
email.
"""
from __future__ import annotations

import os

import json
from pathlib import Path
from typing import Any, Iterable

ACTIVE_STATUSES = frozenset({"active", "trialing"})
KNOWN_INACTIVE_STATUSES = frozenset({"canceled", "past_due", "paused", "deleted", "incomplete_expired"})
HANDLED_STATUSES = frozenset({"paused", "deleted"})
LIVE_MODES = frozenset({"active", "activated"})
DEFAULT_INTERNAL_DOMAINS = tuple(
    d.strip().lower().lstrip("@")
    for d in os.environ.get("GHL_INTERNAL_DOMAINS", "").split(",")
    if d.strip()
)


def baseline() -> tuple[int, int] | None:
    """Expected (subscriptions, contacts) from GHL_SAAS_BASELINE, e.g. "281/249".

    Unset means there is nothing to compare against, and the population check
    reports "unchecked" rather than failing every agency whose numbers differ
    from someone else's.
    """
    raw = os.environ.get("GHL_SAAS_BASELINE", "").strip()
    if not raw:
        return None
    subs, _, contacts = raw.partition("/")
    return int(subs), int(contacts)


def normalized_email(value: Any) -> str:
    return str(value or "").strip().lower()


def normalized_status(value: Any) -> str:
    return str(value or "").strip().lower()


def load_comped_emails(path: str | None) -> set[str]:
    if not path:
        return set()
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        values = json.loads(text)
        if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
            raise ValueError("Comped email JSON must be a list of strings.")
    else:
        values = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    return {normalized_email(value) for value in values if normalized_email(value)}


def extract_saas_page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = payload.get("data") or {}
    pagination = data.get("pagination")
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("locations"), list)
        or not isinstance(pagination, dict)
        or not all(key in pagination for key in ("page", "limit", "total", "totalPages", "hasNext"))
    ):
        raise ValueError("Unexpected SaaS locations response envelope.")
    return data["locations"], pagination


def extract_saas_detail(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if not isinstance(data, dict) or not data.get("locationId"):
        raise ValueError("Unexpected SaaS subscription response envelope.")
    return data


def extract_location_page(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("locations")
    if not isinstance(rows, list):
        raise ValueError("Unexpected agency locations response envelope.")
    return rows


def extract_payment_page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    rows, total = payload.get("data"), payload.get("totalCount")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise ValueError("Unexpected payment subscriptions response envelope.")
    return rows, total


def extract_transaction_page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    rows, total = payload.get("data"), payload.get("totalCount")
    if not isinstance(rows, list) or not isinstance(total, int):
        raise ValueError("Unexpected payment transactions response envelope.")
    return rows, total


def product_ids(row: dict[str, Any]) -> set[str]:
    """Return the live-proven internal product ID from a subscription row."""
    values: set[str] = set()
    recurring = ((row.get("recurringProduct") or {}).get("product") or {})
    if isinstance(recurring, dict) and recurring.get("_id"):
        values.add(str(recurring["_id"]))
    return values


def product_id(row: dict[str, Any]) -> Any:
    values = product_ids(row)
    return next(iter(values)) if len(values) == 1 else None


def order_product_ids(order: dict[str, Any]) -> set[str]:
    """Read internal HighLevel product IDs from a fresh order detail."""
    values: set[str] = set()
    for item in order.get("items") or []:
        if not isinstance(item, dict):
            continue
        product = item.get("product") or {}
        if isinstance(product, dict) and product.get("_id"):
            values.add(str(product["_id"]))
    return values


def population_check(subscription_count: int, contact_count: int) -> dict[str, Any]:
    expected = baseline()
    if expected is None:
        return {
            "status": "unchecked",
            "observedSubscriptions": subscription_count,
            "observedContacts": contact_count,
            "baselineSubscriptions": None,
            "baselineContacts": None,
            "subscriptionRatio": None,
            "contactRatio": None,
        }
    BASELINE_SUBSCRIPTIONS, BASELINE_CONTACTS = expected
    sub_ratio = subscription_count / BASELINE_SUBSCRIPTIONS
    contact_ratio = contact_count / BASELINE_CONTACTS
    if subscription_count == BASELINE_SUBSCRIPTIONS and contact_count == BASELINE_CONTACTS:
        status = "exact"
    elif 0.75 <= sub_ratio <= 1.50 and 0.75 <= contact_ratio <= 1.50:
        status = "near"
    else:
        status = "failed"
    return {
        "status": status,
        "observedSubscriptions": subscription_count,
        "observedContacts": contact_count,
        "baselineSubscriptions": BASELINE_SUBSCRIPTIONS,
        "baselineContacts": BASELINE_CONTACTS,
        "subscriptionRatio": round(sub_ratio, 4),
        "contactRatio": round(contact_ratio, 4),
    }


def _known_status(value: Any) -> bool:
    status = normalized_status(value)
    return bool(status) and (status in ACTIVE_STATUSES or status in KNOWN_INACTIVE_STATUSES)


def resolve_joins(
    saas_locations: Iterable[dict[str, Any]],
    saas_details: dict[str, dict[str, Any]],
    payments_by_contact: dict[str, list[dict[str, Any]]],
    payments_by_email: dict[str, list[dict[str, Any]]],
    location_profiles: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Match each SaaS location to its payment subscriptions, contact id first.

    Email is the wrong key and this audit exists because of it. A member took two free
    sub-accounts on two addresses and no email join could see they were one person.
    GoHighLevel had already resolved that identity: it merges contacts on phone, so both
    subscriptions hung off one contact id. The SaaS subscription detail carries that id as
    `customerId`, so the join needs no lookup and no fuzzy matching -- the field was being
    fetched and discarded.

    Merging cuts both ways, though. Two unrelated people sharing a phone number land on one
    contact, and that contact can then own several SaaS locations. Attributing one active
    subscription to all of them would invent a payment relationship. So when a contact owns
    more than one location, the subscriptions only cover them if there are at least as many
    active ones as there are locations. Fewer, and which location is covered is unknowable
    from here: that is an honest `unknown`, not a guess.

    Returns (candidates_by_location, join_by_location, join_errors).
    """
    profiles = location_profiles or {}
    locations_by_contact: dict[str, set[str]] = {}
    contact_by_location: dict[str, str] = {}
    for source in saas_locations:
        location_id = str(source.get("locationId") or "")
        detail = saas_details.get(location_id) or {}
        contact_id = str(detail.get("customerId") or source.get("customerId") or "")
        if contact_id:
            contact_by_location[location_id] = contact_id
            locations_by_contact.setdefault(contact_id, set()).add(location_id)

    locations_by_email: dict[str, set[str]] = {}
    for source in saas_locations:
        location_id = str(source.get("locationId") or "")
        email = normalized_email(
            source.get("email") or (profiles.get(location_id) or {}).get("email")
        )
        if email:
            locations_by_email.setdefault(email, set()).add(location_id)

    candidates_by_location: dict[str, list[dict[str, Any]]] = {}
    join_by_location: dict[str, dict[str, Any]] = {}
    join_errors: dict[str, list[str]] = {}

    for source in saas_locations:
        location_id = str(source.get("locationId") or "")
        errors: list[str] = []
        contact_id = contact_by_location.get(location_id, "")

        if contact_id:
            candidates = list(payments_by_contact.get(contact_id, []))
            siblings = locations_by_contact.get(contact_id, {location_id})
            join: dict[str, Any] = {
                "method": "contactId",
                "contactId": contact_id,
                "cardinality": len(candidates),
                "locationsOnContact": len(siblings),
            }
            detail = saas_details.get(location_id) or {}
            own_saas_status = normalized_status(
                detail.get("subscriptionStatus")
                or (source.get("subscriptionInfo") or {}).get("subscriptionStatus")
            )
            if len(siblings) > 1 and own_saas_status in ACTIVE_STATUSES:
                # A shared contact says nothing here. The SaaS subscription is attached to
                # THIS location and it is active, which is per-location evidence that owes
                # nothing to how the contact's payment records distribute.
                join["sharedContactResolved"] = True
                join["resolvedBy"] = "own-active-saas-subscription"
            elif len(siblings) > 1:
                active = [
                    item for item in candidates
                    if normalized_status(item.get("status")) in ACTIVE_STATUSES
                ]
                join["activeOnContact"] = len(active)
                if len(active) >= len(siblings):
                    # Enough active subscriptions to cover every location on this contact.
                    join["sharedContactResolved"] = True
                else:
                    errors.append(
                        f"contact {contact_id} owns {len(siblings)} SaaS locations but only "
                        f"{len(active)} active subscriptions; cannot say which is covered"
                    )
                    join["sharedContactResolved"] = False
        else:
            email = normalized_email(
                source.get("email") or (profiles.get(location_id) or {}).get("email")
            )
            candidates = list(payments_by_email.get(email, [])) if email else []
            join = {"method": "email", "cardinality": len(candidates)}
            if not email:
                errors.append("SaaS location has no contact id and no email join key")
            else:
                join["email"] = email
                if len(locations_by_email.get(email, set())) > 1:
                    errors.append("email fallback is ambiguous across multiple SaaS locations")
                if len(candidates) > 1:
                    errors.append(
                        "email fallback is ambiguous across multiple payment subscriptions"
                    )

        candidates_by_location[location_id] = candidates
        join_by_location[location_id] = join
        if errors:
            join_errors[location_id] = errors

    return candidates_by_location, join_by_location, join_errors


def classify_row(row: dict[str, Any], comped_emails: set[str], internal_domains: set[str]) -> str:
    if row.get("errors"):
        return "unknown"
    saas_status = normalized_status((row.get("saas") or {}).get("status"))
    saas_mode = normalized_status(row.get("saasMode"))
    payment_statuses = [normalized_status(item.get("status")) for item in (row.get("payment") or {}).get("subscriptions", [])]
    if (
        not _known_status(saas_status)
        or any(not _known_status(status) for status in payment_statuses)
        or saas_mode not in LIVE_MODES.union(HANDLED_STATUSES)
    ):
        return "unknown"
    if saas_mode in HANDLED_STATUSES or saas_status in HANDLED_STATUSES:
        return "paused/deleted"
    if saas_status in ACTIVE_STATUSES or any(status in ACTIVE_STATUSES for status in payment_statuses):
        return "active-paid"
    # past_due is a failed card, not a decision to leave, and it is recoverable revenue.
    # Folding it in with people who deliberately cancelled invites the wrong action: pausing
    # deletes their phone numbers and A2P registrations after 14 days.
    if saas_status == "past_due" or any(status == "past_due" for status in payment_statuses):
        return "active-past-due"
    email = normalized_email(row.get("email"))
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    if email in comped_emails or domain in internal_domains:
        return "active-comped"
    return "active-unpaid"


def build_rows(
    saas_locations: Iterable[dict[str, Any]], saas_details: dict[str, dict[str, Any]],
    location_profiles: dict[str, dict[str, Any]],
    candidates_by_location: dict[str, list[dict[str, Any]]],
    transaction_evidence: dict[str, dict[str, Any] | None], read_errors: dict[str, list[str]],
    comped_emails: set[str], internal_domains: set[str],
    join_by_location: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    joins = join_by_location or {}
    rows = []
    for source in saas_locations:
        location_id = str(source.get("locationId") or "")
        detail = saas_details.get(location_id) or {}
        profile = location_profiles.get(location_id) or {}
        email = normalized_email(source.get("email") or profile.get("email"))
        candidates = candidates_by_location.get(location_id, [])
        subscriptions = [{
            "id": item.get("subscriptionId"), "recordId": item.get("_id"), "status": item.get("status"),
            "amount": item.get("amount"), "currency": item.get("currency"),
            "contactId": item.get("contactId"), "contactEmail": item.get("contactEmail"),
        } for item in candidates]
        evidence = [transaction_evidence.get(str(item.get("subscriptionId"))) for item in candidates]
        successful = sorted((item for item in evidence if item), key=lambda item: str(item.get("createdAt") or ""), reverse=True)
        latest = successful[0] if successful else None
        info = source.get("subscriptionInfo") or {}
        row = {
            "locationId": location_id, "name": source.get("name") or profile.get("name"), "email": email,
            "createdAt": profile.get("dateAdded"), "saasMode": detail.get("saasMode", source.get("saasMode")),
            "join": joins.get(location_id, {"method": "email", "cardinality": len(candidates)}),
            "saas": {
                "subscriptionId": detail.get("subscriptionId", source.get("subscriptionId")),
                "status": detail.get("subscriptionStatus", info.get("subscriptionStatus")),
                "planId": detail.get("saasPlanId", info.get("saasPlanId")),
                "productId": detail.get("productId", info.get("productId")),
                "priceId": detail.get("priceId", info.get("priceId")),
                "listSubscriptionId": source.get("subscriptionId"),
                "listStatus": info.get("subscriptionStatus"),
            },
            "payment": {"subscriptions": subscriptions, "lastInvoice": None if latest is None else {
                "date": latest.get("createdAt"), "amount": latest.get("amount"), "currency": latest.get("currency"),
                "invoiceId": latest.get("invoiceId"),
                "transactionId": latest.get("_id") or latest.get("id")}},
            "errors": list(read_errors.get(location_id, [])),
        }
        row["classification"] = classify_row(row, comped_emails, internal_domains)
        rows.append(row)
    return rows


def classification_counts(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "active-paid", "active-past-due", "active-unpaid", "active-comped",
        "paused/deleted", "unknown",
    )
    return {key: sum(row.get("classification") == key for row in rows) for key in keys}


def latest_successful_transaction(rows: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    successful = [
        row for row in rows
        if normalized_status(row.get("status")) == "succeeded" and row.get("liveMode") is True
    ]
    return max(successful, key=lambda row: str(row.get("createdAt") or ""), default=None)


def render_table(report: dict[str, Any]) -> str:
    headers = ("CLASS", "LOCATION", "NAME", "CREATED", "SAAS STATUS / ID", "PAYMENT STATUS / ID", "LAST INVOICE", "AMOUNT")
    matrix = [headers]
    for row in report["rows"]:
        payments = row["payment"]["subscriptions"]
        payment_text = ", ".join(f"{item.get('status') or '-'} / {item.get('id') or '-'}" for item in payments) or "-"
        invoice = row["payment"].get("lastInvoice") or {}
        amount = invoice.get("amount")
        if amount is not None and invoice.get("currency"):
            amount = f"{amount} {invoice['currency']}"
        matrix.append((row["classification"], row["locationId"], row.get("name") or "-", row.get("createdAt") or "-",
                       f"{row['saas'].get('status') or '-'} / {row['saas'].get('subscriptionId') or '-'}",
                       payment_text, invoice.get("date") or "-", str(amount) if amount is not None else "-"))
    widths = [max(len(str(values[i])) for values in matrix) for i in range(len(headers))]
    lines = ["  ".join(str(value).ljust(widths[i]) for i, value in enumerate(values)) for values in matrix]
    lines.insert(1, "  ".join("-" * width for width in widths))
    check = report["populationCheck"]
    lines.extend(["", f"Population check: {check['status']} ({check['observedSubscriptions']} subscriptions, {check['observedContacts']} contacts; baseline {check['baselineSubscriptions']}/{check['baselineContacts']})"])
    if check["status"] == "failed":
        lines.append("POPULATION CHECK FAILED: classification summary withheld.")
    else:
        summary = report["summary"]["classifications"]
        lines.append("Classification summary: " + ", ".join(f"{key}={value}" for key, value in summary.items()))
    lines.extend(f"Warning: {warning}" for warning in report.get("warnings", []))
    return "\n".join(lines)
