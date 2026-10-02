"""GoHighLevel REST API client with bearer token authentication."""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import requests

BASE_URL = "https://services.leadconnectorhq.com"

# Path-based API version routing — different GHL endpoints require different versions
VERSION_MAP = {
    "/conversations/": "2021-04-15",
    "/calendars/": "2021-04-15",
    "/contacts/": "2021-07-28",
    "/opportunities/": "2021-07-28",
    "/workflows/": "2021-07-28",
    "/campaigns/": "2021-07-28",
    "/invoices/": "2021-07-28",
    "/payments/": "2021-07-28",
    "/emails/": "2021-07-28",
    "/forms/": "2021-07-28",
    "/locations/": "2021-07-28",
    "/social-media-posting/": "2021-07-28",
    "/proposals/": "2021-07-28",
    "/saas/": "v3",
}
DEFAULT_VERSION = "2021-07-28"


def _version_for_path(path: str) -> str:
    """Resolve API version based on request path prefix."""
    for prefix, version in VERSION_MAP.items():
        if path.startswith(prefix):
            return version
    return DEFAULT_VERSION


def _get_token(path: str = "", agency: bool = False) -> str:
    """Get the correct bearer token for a public API path.

    SaaS endpoints are company scoped. Let operators provide an agency token
    without replacing the location-scoped token used by every other command.
    """
    if path.startswith("/saas/") or agency:
        agency_token = os.environ.get("GHL_AGENCY_API_KEY", "").strip()
        if agency_token:
            return agency_token
    token = os.environ.get("GHL_API_KEY", "").strip()
    if not token:
        print(
            "Error: GHL_API_KEY environment variable is not set.\n"
            "Set it with: export GHL_API_KEY='your-api-key-here'",
            file=sys.stderr,
        )
        sys.exit(1)
    return token


def _get_location_id() -> str:
    """Get location ID from the GHL_LOCATION_ID env var.

    Deliberately has no default. This used to fall back to a hardcoded
    production location, which meant an unset or misspelled env var silently
    targeted that account instead of failing — including for writes.
    """
    location_id = os.environ.get("GHL_LOCATION_ID", "").strip()
    if not location_id:
        print(
            "Error: GHL_LOCATION_ID environment variable is not set.\n"
            "Set it with: export GHL_LOCATION_ID='your-location-id'\n"
            "Or invoke via the ./ghl wrapper, which loads a credential profile.",
            file=sys.stderr,
        )
        sys.exit(1)
    return location_id


def _headers(
    version: str | None = None,
    path: str = "",
    agency: bool = False,
) -> dict[str, str]:
    """Build request headers with auth and auto-resolved version."""
    return {
        "Authorization": f"Bearer {_get_token(path, agency=agency)}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Version": version or _version_for_path(path),
    }


# --- Rate limiting -----------------------------------------------------------
# GHL throttles per-location. Without this, a bulk run just fails partway
# through with a 429 and no indication of how far it got.
MAX_ATTEMPTS = 4
BACKOFF_BASE_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


def _retry_delay(resp: "requests.Response", attempt: int) -> float:
    """Seconds to wait before retrying: honor Retry-After, else exponential."""
    retry_after = resp.headers.get("Retry-After")
    if retry_after:
        try:
            return min(float(retry_after), MAX_BACKOFF_SECONDS)
        except ValueError:
            pass  # GHL can send an HTTP-date; fall through to exponential
    return min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)


def _request(method: str, path: str, **kwargs: Any) -> "requests.Response":
    """Issue a request, retrying on 429 and transient 5xx."""
    url = f"{BASE_URL}{path}"
    version = kwargs.pop("version", None)
    agency = kwargs.pop("agency", False)
    headers = _headers(version, path, agency=agency)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        if resp.status_code not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
            resp.raise_for_status()
            return resp
        delay = _retry_delay(resp, attempt)
        print(
            f"GHL {resp.status_code} on {method} {path} — "
            f"retrying in {delay:.1f}s (attempt {attempt}/{MAX_ATTEMPTS - 1})",
            file=sys.stderr,
        )
        time.sleep(delay)

    return resp  # unreachable; keeps type checkers happy


def get(
    path: str,
    params: dict[str, Any] | None = None,
    version: str | None = None,
    agency: bool = False,
) -> dict:
    """Make a GET request to the GHL API."""
    return _request("GET", path, params=params, version=version, agency=agency).json()


def post(
    path: str,
    data: dict[str, Any] | None = None,
    version: str | None = None,
    agency: bool = False,
) -> dict:
    """Make a POST request to the GHL API."""
    return _request("POST", path, json=data or {}, version=version, agency=agency).json()


def put(path: str, data: dict[str, Any] | None = None, version: str | None = None) -> dict:
    """Make a PUT request to the GHL API."""
    return _request("PUT", path, json=data or {}, version=version).json()


def delete(
    path: str,
    params: dict[str, Any] | None = None,
    version: str | None = None,
    agency: bool = False,
    data: dict[str, Any] | None = None,
) -> dict:
    """Make a DELETE request to the GHL API."""
    kwargs: dict[str, Any] = {"params": params, "version": version, "agency": agency}
    if data is not None:
        kwargs["json"] = data
    resp = _request("DELETE", path, **kwargs)
    try:
        return resp.json()
    except (json.JSONDecodeError, requests.exceptions.JSONDecodeError):
        return {"status": "deleted", "statusCode": resp.status_code}


def format_output(data: Any, as_json: bool = False) -> str:
    """Format API response for display."""
    if as_json:
        return json.dumps(data, indent=2, default=str)
    if isinstance(data, dict):
        return _format_dict(data)
    if isinstance(data, list):
        return _format_list(data)
    return str(data)


def _format_dict(d: dict, indent: int = 0) -> str:
    """Format a dict for human-readable display."""
    lines = []
    prefix = "  " * indent
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{prefix}{k}:")
            lines.append(_format_dict(v, indent + 1))
        elif isinstance(v, list):
            lines.append(f"{prefix}{k}: [{len(v)} items]")
            for i, item in enumerate(v[:5]):
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title") or item.get("id", f"item {i}")
                    lines.append(f"{prefix}  - {name}")
                else:
                    lines.append(f"{prefix}  - {item}")
            if len(v) > 5:
                lines.append(f"{prefix}  ... and {len(v) - 5} more")
        else:
            lines.append(f"{prefix}{k}: {v}")
    return "\n".join(lines)


def _format_list(items: list, indent: int = 0) -> str:
    """Format a list for human-readable display."""
    lines = []
    prefix = "  " * indent
    for i, item in enumerate(items):
        if isinstance(item, dict):
            name = item.get("name") or item.get("title") or item.get("id", f"item {i}")
            lines.append(f"{prefix}{i + 1}. {name}")
            for k, v in item.items():
                if k not in ("name", "title") and not isinstance(v, (dict, list)):
                    lines.append(f"{prefix}   {k}: {v}")
        else:
            lines.append(f"{prefix}{i + 1}. {item}")
    return "\n".join(lines)
