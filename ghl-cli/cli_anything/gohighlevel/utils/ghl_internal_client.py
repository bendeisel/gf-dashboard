"""GoHighLevel internal API client for workflow creation.

Uses Firebase JWT auth against backend.leadconnectorhq.com.
Adapted from ghl-superspeed-v3-main/lib/engine.py (2026-03-25).

EXPERIMENTAL: Gated behind --experimental flag in CLI.
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

BASE_URL = "https://backend.leadconnectorhq.com"
PROPOSAL_SERVICE_URL = "https://services.leadconnectorhq.com/proposals"
# The Firebase web key is read from GHL_FIREBASE_API_KEY at call time and is
# deliberately NOT vendored here — a distributed build must not carry account
# values of the person who packaged it. docs/get-firebase-token.md tells the
# operator how to read both this and the refresh token out of their own session.
CTX = ssl.create_default_context()

# Sentinel: "this 401 is retryable with a fresh token". Distinct from None so a
# genuine auth failure can never be mistaken for an empty result set.
_AUTH_RETRY = object()


def _redact_diagnostic(value: str, *secrets: str) -> str:
    """Remove caller credentials from an error string before it reaches stderr."""
    redacted = value
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    return redacted

CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Keys to strip from GET responses before PUT (avoids validation errors)
STRIP_KEYS = frozenset([
    "_id", "id", "__v", "createdAt", "updatedAt", "companyId", "locationId",
    "companyAge", "creationSource", "originType", "deleted",
    "isTriggerBucketMigrated", "permissionMeta",
])

_INTERNAL_WARNING_SHOWN = False


def _warn_internal_api_once() -> None:
    """Print a one-time stderr warning before the internal API is first used.

    The internal API authenticates with your full Firebase session token — your
    entire GHL login, not a scoped key — against GHL's unofficial backend. This
    fires once per process and covers BOTH the CLI's --experimental commands and
    the builders/ scripts (which use TokenManager directly). It is non-blocking;
    silence it with GHL_SUPPRESS_INTERNAL_WARNING=1.
    """
    global _INTERNAL_WARNING_SHOWN
    if _INTERNAL_WARNING_SHOWN:
        return
    _INTERNAL_WARNING_SHOWN = True
    if os.environ.get("GHL_SUPPRESS_INTERNAL_WARNING", "").strip():
        return
    print(
        "⚠ Internal GHL API: authenticating with your full Firebase session token\n"
        "  (your entire GHL login, not a scoped key) against the UNOFFICIAL\n"
        "  GHL's unofficial UI services. Run this only on YOUR OWN agency account.\n"
        "  never a client's. No SLA; the unofficial API may change or break without\n"
        "  notice. (suppress: GHL_SUPPRESS_INTERNAL_WARNING=1)",
        file=sys.stderr,
    )


class TokenManager:
    """Firebase refresh token management with auto-refresh.

    Token sources (in priority order):
    1. Cached token (if < 50 minutes old)
    2. Firebase refresh token (from GHL_FIREBASE_REFRESH_TOKEN env var)
    3. Direct Firebase token (from GHL_FIREBASE_TOKEN env var)
    """

    def __init__(self):
        self._token: Optional[str] = None
        self._token_time: float = 0
        self._load_disk_cache()

    # Each `ghl` run is a new process, so an in-memory cache alone mints a new
    # ID token per command and bursts trip Google's per-minute token-exchange
    # quota (HTTP 429). Persist the short-lived ID token per profile, 0600.
    def _cache_path(self) -> str:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
        profile = os.environ.get("GHL_PROFILE", "default")
        return os.path.join(base, "ghl", f"firebase-{profile}.json")

    def _load_disk_cache(self) -> None:
        try:
            with open(self._cache_path()) as f:
                c = json.load(f)
            if c.get("token") and (time.time() - float(c.get("time", 0))) < 3000:
                self._token, self._token_time = c["token"], float(c["time"])
        except Exception:  # noqa: BLE001
            pass

    def _save_disk_cache(self) -> None:
        try:
            path = self._cache_path()
            os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump({"token": self._token, "time": self._token_time}, f)
        except Exception:  # noqa: BLE001
            pass

    def get_token(self) -> str:
        """Get a valid Firebase JWT token."""
        _warn_internal_api_once()
        # 1. Check if current token is still fresh (< 50 min)
        if self._token and (time.time() - self._token_time) < 3000:
            return self._token

        # 2. Try Firebase refresh token
        refresh_token = os.environ.get("GHL_FIREBASE_REFRESH_TOKEN", "").strip()
        if refresh_token:
            firebase_web_key = os.environ.get("GHL_FIREBASE_API_KEY", "").strip()
            if not firebase_web_key:
                print(
                    "Error: GHL_FIREBASE_REFRESH_TOKEN is set but "
                    "GHL_FIREBASE_API_KEY is missing.\n"
                    "Run the no-network DevTools helper in "
                    "docs/get-firebase-token.md and paste both values into .env.",
                    file=sys.stderr,
                )
                sys.exit(1)
            token = self._refresh_firebase(refresh_token, firebase_web_key)
            if token:
                self._token = token
                self._token_time = time.time()
                self._save_disk_cache()
                return token
            print(
                "Error: Firebase refresh token is set but token refresh failed.\n"
                "The refresh token may be revoked or expired.\n"
                "Get a new one with the DevTools snippet in docs/get-firebase-token.md.",
                file=sys.stderr,
            )
            sys.exit(1)

        # 3. Try direct Firebase token from env
        token = os.environ.get("GHL_FIREBASE_TOKEN", "").strip()
        if token:
            self._token = token
            self._token_time = time.time()
            return token

        print(
            "Error: No Firebase token available for internal API.\n"
            "Set GHL_FIREBASE_REFRESH_TOKEN (preferred) or GHL_FIREBASE_TOKEN.\n"
            "Get the refresh token with the DevTools snippet in docs/get-firebase-token.md.",
            file=sys.stderr,
        )
        sys.exit(1)

    def force_refresh(self) -> str:
        """Force token refresh (called on 401)."""
        self._token = None
        self._token_time = 0
        return self.get_token()

    def get_user_id(self) -> Optional[str]:
        """Extract the logged-in user's id from the Firebase JWT claims.

        The internal funnel-delete endpoint requires a userId; it is carried in
        the token's `user_id`/`sub` claim, so no extra API call is needed.
        """
        import base64

        token = self.get_token()
        try:
            payload = token.split(".")[1]
            payload += "=" * (-len(payload) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload))
            return claims.get("user_id") or claims.get("sub")
        except Exception:
            return None

    def _refresh_firebase(self, refresh_token: str,
                          firebase_web_key: str) -> Optional[str]:
        """Exchange Firebase refresh token for a fresh ID token.

        Retries with backoff. Google throttles bursts of refreshes -- several
        short-lived processes in a row, or a thread pool starting cold, each
        mint their own token -- and a throttled exchange is indistinguishable
        from a revoked token unless the reason is printed. It used to swallow
        every exception and return None, so a transient 429 was reported to the
        user as "the refresh token may be revoked or expired".
        """
        last_reason = ""
        for attempt in range(3):
            if attempt:
                time.sleep(1.5 * attempt)
            try:
                body = f"grant_type=refresh_token&refresh_token={refresh_token}"
                req = urllib.request.Request(
                    f"https://securetoken.googleapis.com/v1/token?key={firebase_web_key}",
                    data=body.encode(),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    method="POST",
                )
                with urllib.request.urlopen(req, context=CTX, timeout=10) as r:
                    data = json.loads(r.read())
                    token = data.get("id_token", "")
                    if token:
                        return token
                    last_reason = "response carried no id_token"
            except urllib.error.HTTPError as exc:
                detail = ""
                try:
                    detail = json.loads(exc.read()).get("error", {}).get("message", "")
                except Exception:  # noqa: BLE001
                    pass
                last_reason = f"HTTP {exc.code} {detail}".strip()
                # A revoked or malformed token is final; retrying cannot help.
                if detail in ("TOKEN_EXPIRED", "USER_DISABLED", "INVALID_REFRESH_TOKEN",
                              "USER_NOT_FOUND"):
                    break
            except Exception as exc:  # noqa: BLE001
                last_reason = f"{type(exc).__name__}: {exc}"
        if last_reason:
            safe_reason = _redact_diagnostic(last_reason, refresh_token, firebase_web_key)
            print(f"  (token refresh failed: {safe_reason})", file=sys.stderr)
        return None


class InternalGHLClient:
    """GHL internal UI API client.

    Most routes use a Firebase JWT in token-id. Some current UI services also
    require a short-lived IAM bearer token, supplied explicitly per request.
    """

    def __init__(self, token_mgr: TokenManager, location_id: str):
        self.token_mgr = token_mgr
        self.location_id = location_id
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Optional[dict]:
        """Make an API request with auto-retry on 401.

        extra_headers merges into the default header set. The forms/surveys/
        funnels internal services require {"Version": "2021-07-28"}; the workflow
        endpoints do not, so it is opt-in per call rather than always sent.
        """
        token = self.token_mgr.get_token()
        body = self._keep_workflow_sender(method, path, body, token)
        result = self._do_request(method, path, body, token, extra_headers)

        # A 401 means the cached ID token went stale — mint a fresh one and
        # retry once. Anything else is returned as-is.
        if result is _AUTH_RETRY:
            token = self.token_mgr.force_refresh()
            result = self._do_request(method, path, body, token, extra_headers)

        # Still unauthorized after a fresh token: the token is fine, this
        # account just can't see this resource. Report it — returning None
        # here made a cross-account 403 look identical to an empty result.
        if result is _AUTH_RETRY:
            return {
                "_error": True,
                "code": 401,
                "message": (
                    "Unauthorized after token refresh. The Firebase token does not "
                    "grant access to this location. Confirm GHL_FIREBASE_REFRESH_TOKEN "
                    "was grabbed while logged into the account that owns this location."
                ),
            }

        return result

    def _keep_workflow_sender(
        self, method: str, path: str, body: dict | None, token: str
    ) -> dict | None:
        """Carry the workflow's current senderAddress into a PUT that omits it.

        GHL resets a top-level field a workflow PUT leaves out, so a PUT that only
        meant to change steps or triggers also cleared the sender, and every
        blank-From email in that workflow then went out as the contact's assigned
        user. Pass `senderAddress: None` to clear it on purpose.
        """
        if method != "PUT" or not isinstance(body, dict) or "senderAddress" in body:
            return body
        parts = path.split("?")[0].strip("/").split("/")
        if len(parts) != 3 or parts[0] != "workflow" or parts[2] == "trigger":
            return body
        current = self._do_request("GET", path, None, token)
        if not isinstance(current, dict) or current.get("_error") or "senderAddress" not in current:
            return body
        return {**body, "senderAddress": current["senderAddress"]}

    def _do_request(
        self,
        method: str,
        path: str,
        body: dict | None,
        token: str,
        extra_headers: dict[str, str] | None = None,
    ) -> Optional[dict]:
        self._call_count += 1
        safe_token = token.encode("ascii", "ignore").decode("ascii").strip()
        headers = {
            "token-id": safe_token,
            "channel": "APP",
            "source": "WEB_USER",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": CHROME_UA,
        }
        if extra_headers:
            headers.update(extra_headers)
        # GHL splits the internal surface across hosts: most routes live on
        # backend.leadconnectorhq.com, but some (e.g. /smartlist/delete) are on
        # api.leadconnectorhq.com. Callers pass an absolute URL for those.
        url = path if path.startswith("http") else f"{BASE_URL}{path}"
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
                text = resp.read().decode().strip()
                if not text:
                    return {}
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    # Some routes answer 2xx with a non-JSON body. That is a
                    # success, not a failure — parsing it as an error turned a
                    # completed delete into an error message.
                    #
                    # `body` stays truncated so a stray HTML blob can't flood a
                    # terminal, but `bodyFull`/`bodyLength` are kept: verifying a
                    # template upload means checking the returned HTML, and a
                    # silently-clipped body made that check pass on nothing.
                    return {
                        "status": "ok",
                        "statusCode": resp.status,
                        "body": text[:200],
                        "bodyFull": text,
                        "bodyLength": len(text),
                        "truncated": len(text) > 200,
                    }
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return _AUTH_RETRY  # stale ID token — caller refreshes and retries
            error_body = e.read().decode() if e.fp else ""
            if e.code == 403:
                # Token is valid but this account cannot reach the resource —
                # almost always a location belonging to a different GHL company.
                return {
                    "_error": True,
                    "code": 403,
                    "message": (
                        "Forbidden. The Firebase token is valid but has no access to "
                        "this location — check that the profile's location and "
                        "GHL_FIREBASE_REFRESH_TOKEN belong to the same GHL account. "
                        f"{error_body[:200]}"
                    ).strip(),
                }
            return {"_error": True, "code": e.code, "message": error_body[:200]}
        except Exception as ex:
            return {"_error": True, "message": str(ex)}

    def create_location_tag(self, tag: str) -> bool:
        """Create a tag at location level (required before using in triggers)."""
        result = self.request(
            "POST", f"/workflow/{self.location_id}/tags/create", {"tag": tag}
        )
        return bool(result and not result.get("_error"))

    # -- Forms / surveys / funnels (require the Version header) --------------
    # These services live behind backend.leadconnectorhq.com and reject the
    # workflow header set; they need token-id + Version together.

    _V = {"Version": "2021-07-28"}

    def _proposal_headers(self) -> dict[str, str]:
        """Return the headers the proposal service actually needs.

        `GHL_IAM_TOKEN` is OPTIONAL. This used to raise without one, on the
        belief that the template builder's dual auth was required. Measured
        against the live service on 2026-08-24 with a read-only template GET:

            token-id only, no Authorization  -> 200 OK, full template
            token-id + Firebase ID as bearer -> 200 OK, full template
            Firebase ID as bearer, no token-id -> 401 "Error calling IAM service"

        So `token-id` is what authenticates and the Authorization header is
        surplus. The belief survived because the raise fired before any request
        was made, so the assumption was never once tested against the service.

        A stale or foreign IAM token is worse than none — case three shows the
        service tries to resolve a bearer when it gets one — so an explicitly
        supplied token is still passed through, but nothing is invented.
        """
        headers = {"Version": "2021-07-28"}
        iam_token = os.environ.get("GHL_IAM_TOKEN", "").strip()
        if iam_token:
            if iam_token.lower().startswith("bearer "):
                iam_token = iam_token.split(None, 1)[1].strip()
            headers["Authorization"] = f"Bearer {iam_token}"
        return headers

    def _proposal_request(
        self, method: str, url: str, body: dict[str, Any] | None = None
    ) -> Optional[dict]:
        """Call the proposal service with accurate 401 guidance."""
        result = self.request(
            method, url, body, extra_headers=self._proposal_headers()
        )
        if isinstance(result, dict) and result.get("code") == 401:
            result = dict(result)
            if os.environ.get("GHL_IAM_TOKEN", "").strip():
                result["message"] = (
                    "Unauthorized. GHL_IAM_TOKEN is set and the service tried "
                    "to resolve it. This service does not need one — unset "
                    "GHL_IAM_TOKEN and retry on token-id alone before hunting "
                    "for a fresh bearer."
                )
                return result
            result["message"] = (
                "Unauthorized after Firebase refresh. GHL_IAM_TOKEN may be "
                "expired, or the Firebase/IAM session may not grant access to "
                "this location. Copy a fresh IAM token from the template "
                "builder and retry."
            )
        return result

    def create_contract_template(
        self, name: str, *, template_type: str = "proposal",
        is_public_document: bool = False,
    ) -> Optional[dict]:
        """Create an empty template shell through GHL's current UI service."""
        return self._proposal_request(
            "POST",
            f"{PROPOSAL_SERVICE_URL}/templates",
            {
                "name": name,
                "type": template_type,
                "locationId": self.location_id,
                "isPublicDocument": is_public_document,
            },
        )

    def get_contract_template(self, template_id: str) -> Optional[dict]:
        """Fetch the full native template, including pages and field elements."""
        query = urllib.parse.urlencode({"locationId": self.location_id})
        safe_id = urllib.parse.quote(template_id, safe="")
        return self._proposal_request(
            "GET",
            f"{PROPOSAL_SERVICE_URL}/templates/{safe_id}?{query}",
        )

    def update_contract_template(
        self, template_id: str, payload: dict[str, Any]
    ) -> Optional[dict]:
        """Replace template content with a lossless native update payload."""
        safe_id = urllib.parse.quote(template_id, safe="")
        return self._proposal_request(
            "PUT",
            f"{PROPOSAL_SERVICE_URL}/templates/{safe_id}",
            payload,
        )

    def create_form(self, name: str, form_data: dict | None = None) -> Optional[dict]:
        """Create a form with its full content in one POST. Returns the form dict.

        Unlike surveys, forms accept complete formData at create time — there is
        no update-by-id route, so re-POSTing would create a duplicate.
        """
        body = {"locationId": self.location_id, "name": name}
        if form_data is not None:
            body["formData"] = form_data
        r = self.request("POST", "/forms/", body, extra_headers=self._V)
        return (r or {}).get("form") if isinstance(r, dict) else r

    def get_form(self, form_id: str) -> Optional[dict]:
        safe_id = urllib.parse.quote(form_id, safe="")
        r = self.request("GET", f"/forms/{safe_id}", extra_headers=self._V)
        if isinstance(r, dict) and r.get("_error"):
            return r
        return (r or {}).get("form") if isinstance(r, dict) else r

    def delete_form(self, form_id: str) -> bool:
        r = self.request("DELETE", f"/forms/{form_id}", extra_headers=self._V)
        return bool(r and not (isinstance(r, dict) and r.get("_error")))

    def create_survey(self, name: str) -> Optional[dict]:
        """Create an empty survey shell, then wait until it is readable.

        The survey shell is NOT immediately readable/writable after create — a
        subsequent update_survey call races the backend and only partially
        persists. We poll get_survey until the record propagates (usually one
        retry) so the follow-up content write lands cleanly.
        """
        r = self.request("POST", "/surveys/", {"locationId": self.location_id, "name": name},
                         extra_headers=self._V)
        survey = (r or {}).get("survey") if isinstance(r, dict) else r
        if not survey or not survey.get("_id"):
            return survey
        survey_id = survey["_id"]
        for _ in range(10):
            if self.get_survey(survey_id):
                break
            time.sleep(0.5)
        return survey

    def update_survey(self, survey_id: str, name: str, form_data: dict) -> Optional[dict]:
        """Push full formData to a survey. Body must NOT include locationId."""
        return self.request("POST", f"/surveys/{survey_id}",
                            {"name": name, "formData": form_data}, extra_headers=self._V)

    def get_survey(self, survey_id: str) -> Optional[dict]:
        r = self.request("GET", f"/surveys/{survey_id}", extra_headers=self._V)
        return (r or {}).get("survey") if isinstance(r, dict) else r

    def delete_survey(self, survey_id: str) -> bool:
        r = self.request("DELETE", f"/surveys/{survey_id}", extra_headers=self._V)
        return bool(r and not (isinstance(r, dict) and r.get("_error")))

    def create_funnel(self, name: str, funnel_type: str = "funnel") -> Optional[dict]:
        """Create a funnel shell. Add pages with create_funnel_step_page()."""
        return self.request("POST", "/funnels/funnel/create",
                            {"locationId": self.location_id, "name": name, "type": funnel_type},
                            extra_headers=self._V)

    def delete_funnel(self, funnel_id: str, user_id: str | None = None) -> bool:
        uid = user_id or self.token_mgr.get_user_id()
        r = self.request("POST", "/funnels/funnel/delete",
                        {"locationId": self.location_id, "funnelId": funnel_id, "userId": uid},
                        extra_headers=self._V)
        return bool(r and not (isinstance(r, dict) and r.get("_error")))

    def list_funnel_pages(self, funnel_id: str, limit: int = 20) -> Optional[dict]:
        """List page records for a funnel (metadata only)."""
        return self.request(
            "GET",
            f"/funnels/page?locationId={self.location_id}&funnelId={funnel_id}&limit={limit}&offset=0",
            extra_headers=self._V,
        )

    def get_funnel_page(self, page_id: str) -> Optional[dict]:
        """Fetch a page record, including signed draft/live content URLs."""
        return self.request("GET", f"/funnels/page/{page_id}", extra_headers=self._V)

    def get_funnel(self, funnel_id: str) -> Optional[dict]:
        """Fetch one funnel record, including global-section artifact metadata."""
        result = self.request("GET", f"/funnels/funnel/fetch/{funnel_id}", extra_headers=self._V)
        if isinstance(result, dict) and isinstance(result.get("data"), dict):
            return result["data"]
        return result

    def save_global_sections(self, funnel_id: str, sections: list,
                             version: int) -> Optional[dict]:
        """Store a new global-section artifact for a funnel."""
        return self.request("POST", f"/funnels/builder/global-sections/{funnel_id}",
                            {"version": version, "sectionData": sections},
                            extra_headers=self._V)

    def create_funnel_step_page(self, funnel_id: str, step: dict) -> Optional[dict]:
        """Create a step and its initial blank page in one operation."""
        return self.request("POST", "/funnels/funnel/create-step",
                            {"step": step, "funnelId": funnel_id},
                            extra_headers=self._V)

    def save_funnel_page(
        self,
        page_id: str,
        funnel_id: str,
        page_data: dict,
        *,
        page_version: int = 1,
        publish: bool = False,
        manual_save: bool = True,
        meta: dict | None = None,
    ) -> Optional[dict]:
        """Save full builder-v2 page data as a draft or live version."""
        body = {
            "funnelId": funnel_id,
            "pageData": page_data,
            "pageVersion": page_version,
            "pageType": "live" if publish else "draft",
            "manualSave": manual_save,
            "integrations": {},
        }
        if meta is not None:
            body["meta"] = meta
        return self.request("POST", f"/funnels/builder/autosave/{page_id}", body,
                            extra_headers=self._V)
