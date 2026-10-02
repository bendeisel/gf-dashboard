"""Safety helpers for single-target SaaS sub-account lifecycle commands."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable



def protected_location_id() -> str:
    """The agency's own location, which lifecycle commands must never touch.

    GHL_PROTECTED_LOCATION_ID wins; otherwise the profile's GHL_LOCATION_ID, the
    location the CLI is pointed at, is treated as the one to protect.
    """
    return (
        os.environ.get("GHL_PROTECTED_LOCATION_ID", "").strip()
        or os.environ.get("GHL_LOCATION_ID", "").strip()
    )

ACTIVE_STATUSES = frozenset({"active", "trialing"})
PAUSED_STATUSES = frozenset({"paused"})
DISABLED_MODES = frozenset({"disabled", "inactive"})
MIN_REASON_LENGTH = 12
WALLET_PAGE_LIMIT = 1000
WALLET_PAGE_CAP = 100

PAUSE_CONSEQUENCES = (
    "Location admins and users lose login; agency users keep access.",
    "Published funnel pages and live automations move to Draft.",
    "Phone numbers and A2P registrations are deleted after 14 days and are not restored by unpausing.",
    "Reselling, marketplace, and SaaS subscriptions are canceled and must be resubscribed.",
)


def normalized_status(value: Any) -> str:
    return str(value or "").strip().lower()


def has_active_subscription(target: dict[str, Any]) -> bool:
    if normalized_status((target.get("saas") or {}).get("status")) in ACTIVE_STATUSES:
        return True
    return any(
        normalized_status(item.get("status")) in ACTIVE_STATUSES
        for item in (target.get("payment") or {}).get("subscriptions", [])
    )


def is_paused(target: dict[str, Any]) -> bool:
    return (
        normalized_status(target.get("saasMode")) in PAUSED_STATUSES
        or normalized_status((target.get("saas") or {}).get("status")) in PAUSED_STATUSES
    )


def is_disabled(detail: dict[str, Any]) -> bool:
    """Return true only for an explicit disabled lifecycle mode.

    ``isSaaSV2`` identifies the SaaS implementation version. It does not say
    whether SaaS is enabled, so it must never be used as disable evidence.
    """
    return normalized_status(detail.get("saasMode")) in DISABLED_MODES


def extract_wallet_transactions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("transactions", "walletTransactions"):
            if isinstance(data.get(key), list):
                return data[key]
    for key in ("transactions", "walletTransactions"):
        if isinstance(payload.get(key), list):
            return payload[key]
    raise ValueError("Unexpected wallet transaction response envelope.")


def read_wallet_export(
    get: Callable[..., dict], post: Callable[..., dict], company_id: str, location_id: str,
) -> dict[str, Any]:
    balance = get(
        f"/saas-api/public-api/companies/{company_id}/locations/{location_id}/wallet-balance",
        version="v3", agency=True,
    )
    transactions: list[dict[str, Any]] = []
    seen_pages: set[str] = set()
    for page in range(WALLET_PAGE_CAP):
        skip = page * WALLET_PAGE_LIMIT
        payload = post(
            f"/saas/locations/{location_id}/wallet-transactions",
            data={"skip": skip, "limit": WALLET_PAGE_LIMIT}, version="v3", agency=True,
        )
        batch = extract_wallet_transactions(payload)
        fingerprint = json.dumps(batch, sort_keys=True, default=str)
        if batch and fingerprint in seen_pages:
            raise ValueError("Wallet transaction pagination repeated a page.")
        seen_pages.add(fingerprint)
        transactions.extend(batch)
        if len(batch) < WALLET_PAGE_LIMIT:
            return {"walletBalance": balance, "walletTransactions": transactions}
    raise ValueError("Wallet transaction pagination exceeded its safety cap.")


def write_wallet_export(payload: dict[str, Any], export_dir: str, location_id: str) -> str:
    directory = Path(export_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = directory / f"ghl-wallet-{location_id}-{stamp}.json"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
            handle.write("\n")
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    if (path.stat().st_mode & 0o777) != 0o600:
        try:
            path.unlink()
        except OSError:
            pass
        raise OSError("Wallet export permissions are not 0600.")
    return str(path)
