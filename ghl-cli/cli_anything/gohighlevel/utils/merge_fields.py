"""GHL merge fields and their fallbacks.

GHL renders email copy through Handlebars and registers a `default` helper:

    {{default contact.first_name "there"}}

The helper substitutes the fallback when the value is null, undefined **or the
empty string** — which is the case that matters, because a contact with a blank
`first_name` is far more common than one missing the field entirely. A bare
`{{contact.first_name}}` on such a contact renders "Hi ," in the subject line.

So: never emit a bare first-name token. `ensure_fallbacks` rewrites any it finds
into the `default` form, and leaves already-wrapped ones alone.

(GHL's UI tracks the same thing out-of-band in `scheduleOptions.fieldDefaults`,
keyed `"<variable>:<occurrenceIndex>"` per field. Writing the helper inline is
equivalent, applies to the body as well as the four header fields, and does not
depend on that bookkeeping staying in sync.)
"""
from __future__ import annotations

import re

FIRST_NAME_VARIABLE = "contact.first_name"

# Variables that personalize by first name, in rough order of preference.
FIRST_NAME_VARIABLES = (
    "contact.first_name",
    "contact.firstName",
)

DEFAULT_FALLBACK = "there"

# A bare {{ contact.first_name }} — NOT one already inside {{default ...}}.
_BARE_TOKEN = re.compile(
    r"\{\{\s*(" + "|".join(re.escape(v) for v in FIRST_NAME_VARIABLES) + r")\s*\}\}"
)

# An already-wrapped {{default contact.first_name "..."}}.
_WRAPPED_TOKEN = re.compile(
    r"\{\{\s*default\s+(?:" + "|".join(re.escape(v) for v in FIRST_NAME_VARIABLES) + r")\s",
    re.IGNORECASE,
)


def _escape_fallback(value: str) -> str:
    """Escape for a Handlebars double-quoted string argument.

    Mirrors the app's own escaper: backslashes first, then double quotes.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def has_first_name(text: str) -> bool:
    """True if the text personalizes by first name, wrapped or not."""
    if not text:
        return False
    return bool(_BARE_TOKEN.search(text) or _WRAPPED_TOKEN.search(text))


def count_bare_first_name(text: str) -> int:
    return len(_BARE_TOKEN.findall(text or ""))


def ensure_fallbacks(text: str, fallback: str = DEFAULT_FALLBACK) -> str:
    """Give every bare first-name token a fallback. Idempotent."""
    if not text:
        return text
    escaped = _escape_fallback(fallback)
    return _BARE_TOKEN.sub(
        lambda m: '{{default %s "%s"}}' % (m.group(1), escaped), text
    )
