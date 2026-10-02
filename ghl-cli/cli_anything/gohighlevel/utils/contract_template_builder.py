"""Builders for GoHighLevel Documents & Contracts template payloads.

The native schema is taken from the currently shipped GHL template builder.
These helpers preserve unknown nested document data inside the builder's
explicit PUT whitelist so exported templates can be edited safely.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import os
from typing import Any, Iterator
from urllib.parse import urlparse
from uuid import uuid4
from zoneinfo import ZoneInfo


class ContractTemplateError(ValueError):
    """Raised when a compact or native template payload is invalid."""


UPDATE_ROOT_KEYS = frozenset({
    "name", "locationId", "pages", "groups", "variables", "timezone",
    "grandTotal", "recipients", "roles", "fillableFields", "pricingTables",
    "paymentInfo", "enableDirectPayment", "enableAutoSendInvoice",
    "paymentLiveMode", "customValueLinkage", "notificationSettings",
    "redirectSettings", "fontsToLoad", "thumbnail", "emailAttachments",
})
PAYMENT_INFO_KEYS = frozenset({
    "invoiceType", "schedule", "generateInvoiceOnSigning",
    "paymentDepositSettings", "enableAutoPayment",
})
GRAND_TOTAL_KEYS = frozenset({
    "currency", "amount", "discountPercentage", "discounts",
})
FIELD_TYPES = {
    "name": "TextField",
    "text": "TextField",
    "signature": "Signature",
    "date": "DateField",
    "initials": "InitialsField",
    "checkbox": "Checkbox",
}
COMPONENT_NAMES = {
    "TextField": "Text Field Element",
    "Signature": "Signature Element",
    "DateField": "Text Field Element",  # Matches GHL's current factory.
    "InitialsField": "Initials Field Element",
    "Checkbox": "Checkbox Field Element",
}
DEFAULT_DIMENSIONS = {
    "TextField": (165, 26),
    "Signature": (190, 68),
    "DateField": (131, 26),
    "InitialsField": (130, 50),
    "Checkbox": (25, 25),
}
FIELD_PREFIXES = {
    "TextField": "text_field",
    "Signature": "signature",
    "DateField": "date_field",
    "InitialsField": "initials_field",
    "Checkbox": "checkbox_field",
}
FILLABLE_TYPES = frozenset({"TextField", "DateField", "Checkbox", "SaveCardDetails"})
ASSIGNED_CONTACT_ID = "assignedContact"
ASSIGNED_SENDER_ID = "assignedSender"
REDIRECT_TYPES = frozenset({"existingTab", "newTab"})
DYNAMIC_SIGNING_ORDER = {
    ASSIGNED_CONTACT_ID: 1,
    ASSIGNED_SENDER_ID: 2,
}
DEFAULT_SIGNER_FIELDS = (
    {
        "party": "sender", "type": "date", "placeholder": "Company date",
        "recipient": ASSIGNED_SENDER_ID, "entityName": "users",
        "top": 650, "left": 48,
    },
    {
        "party": "sender", "type": "signature", "label": "Company signature",
        "recipient": ASSIGNED_SENDER_ID, "entityName": "users",
        "top": 692, "left": 48,
    },
    {
        "party": "contractor", "type": "name", "placeholder": "Full name",
        "recipient": ASSIGNED_CONTACT_ID, "entityName": "contacts",
        "top": 790, "left": 48,
    },
    {
        "party": "contractor", "type": "date", "placeholder": "Select date",
        "recipient": ASSIGNED_CONTACT_ID, "entityName": "contacts",
        "top": 832, "left": 48,
    },
    {
        "party": "contractor", "type": "signature", "label": "Signature",
        "recipient": ASSIGNED_CONTACT_ID, "entityName": "contacts",
        "top": 874, "left": 48,
    },
)


def _default_timezone() -> dict[str, str]:
    """Return the builder-required timezone, with an explicit env override."""
    explicit_zone = os.environ.get("GHL_CONTRACT_TIMEZONE", "").strip()
    zone = explicit_zone
    if not zone:
        local_path = os.path.realpath("/etc/localtime")
        marker = "/zoneinfo/"
        if marker in local_path:
            zone = local_path.split(marker, 1)[1]
    if not zone:
        local_tz = datetime.now().astimezone().tzinfo
        zone = getattr(local_tz, "key", "") or "UTC"
    try:
        abbreviation = datetime.now(ZoneInfo(zone)).tzname() or zone
    except Exception:
        if explicit_zone:
            raise ContractTemplateError(
                f"GHL_CONTRACT_TIMEZONE {explicit_zone!r} is not a valid IANA timezone."
            )
        zone = "UTC"
        abbreviation = "UTC"
    return {"zone": zone, "abbreviation": abbreviation}


def _product_lists(pages: Any) -> list[dict[str, Any]]:
    """Return native product tables whose pricing metadata must stay in sync."""
    if not isinstance(pages, list):
        return []
    return [
        deepcopy(element)
        for element in walk_elements(pages)
        if element.get("type") == "ProductList"
    ]


def make_letter_page() -> dict[str, Any]:
    """Return the same blank Letter page shape used by the GHL builder."""
    return {
        "type": "Page",
        "version": 2,
        "id": str(uuid4()),
        "children": [],
        "component": {
            "name": "Page",
            "options": {
                "src": "",
                "pageDimensions": {
                    "dimensions": {"width": 816, "height": 1056},
                    "margins": {"top": 48, "right": 48, "bottom": 48, "left": 48},
                    "rotation": "portrait",
                },
            },
        },
        "responsiveStyles": {
            "large": {
                "backgroundColor": "#ffffff",
                "backgroundPosition": "top left",
                "backgroundSize": "cover",
                "backgroundRepeat": "repeat",
                "opacity": 100,
            }
        },
    }


def walk_elements(pages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Yield every element in every page, including nested row/column children."""
    def walk(children: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        for child in children:
            yield child
            nested = child.get("children")
            if isinstance(nested, list):
                yield from walk(nested)

    for page in pages:
        children = page.get("children")
        if isinstance(children, list):
            yield from walk(children)


def _next_field_id(pages: list[dict[str, Any]], prefix: str) -> str:
    used = {
        element.get("component", {}).get("options", {}).get("fieldId")
        for element in walk_elements(pages)
    }
    index = 1
    candidate = f"{prefix}{index}" if prefix == "signature" else f"{prefix}_{index}"
    while candidate in used:
        index += 1
        candidate = f"{prefix}{index}" if prefix == "signature" else f"{prefix}_{index}"
    return candidate


def _primary_recipient(document: dict[str, Any]) -> tuple[Any, Any]:
    recipients = document.get("recipients")
    if not isinstance(recipients, list):
        return ASSIGNED_CONTACT_ID, "contacts"
    recipient = next((item for item in recipients if item.get("isPrimary")), None)
    recipient = recipient or (recipients[0] if recipients else None)
    if not recipient:
        return ASSIGNED_CONTACT_ID, "contacts"
    return recipient.get("id"), recipient.get("entityName")


def build_field(
    kind: str,
    *,
    pages: list[dict[str, Any]],
    document: dict[str, Any],
    label: str | None = None,
    placeholder: str | None = None,
    field_id: str | None = None,
    recipient: str | None = None,
    entity_name: str | None = None,
    required: bool = True,
    top: int = 0,
    left: int = 0,
    width: int | None = None,
    height: int | None = None,
) -> dict[str, Any]:
    """Build one native floating field element."""
    normalized = kind.strip().lower()
    if normalized not in FIELD_TYPES:
        raise ContractTemplateError(
            f"Unsupported field type {kind!r}. Choose: {', '.join(FIELD_TYPES)}."
        )
    native_type = FIELD_TYPES[normalized]
    default_width, default_height = DEFAULT_DIMENSIONS[native_type]
    width = default_width if width is None else width
    height = default_height if height is None else height
    if min(top, left, width, height) < 0 or width == 0 or height == 0:
        raise ContractTemplateError("Field coordinates must be non-negative and dimensions positive.")

    default_recipient, default_entity = _primary_recipient(document)
    recipient = recipient if recipient is not None else default_recipient
    entity_name = entity_name if entity_name is not None else default_entity
    used_field_ids = {
        element.get("component", {}).get("options", {}).get("fieldId")
        for element in walk_elements(pages)
    }
    if field_id and field_id in used_field_ids:
        raise ContractTemplateError(f"Field id {field_id!r} already exists in this template.")
    field_id = field_id or _next_field_id(pages, FIELD_PREFIXES[native_type])
    if native_type == "Signature":
        display_text = label or "Signature"
    elif native_type == "InitialsField":
        display_text = label or "Initials"
    else:
        display_text = ""
    options: dict[str, Any] = {
        "isGhost": True,
        "text": display_text,
        "required": required,
        "fieldId": field_id,
        "src": "",
        "recipient": recipient,
        "signedDate": None,
        "entityName": entity_name,
    }
    if native_type == "TextField":
        options["placeholder"] = placeholder or label or ("Full name" if normalized == "name" else "Enter value")
    elif native_type == "DateField":
        options.update({
            "placeholder": placeholder or label or "Select date",
            "availableDates": "any",
            "dateFormat": "yyyy-MM-dd",
        })
    elif native_type == "Signature":
        options["showName"] = True
    elif native_type == "Checkbox":
        options.update({"preChecked": False, "isConditionalLogic": False})

    large_styles = {
        "paddingTop": "0px",
        "paddingBottom": "0px",
        "paddingLeft": "0px",
        "paddingRight": "0px",
        "marginTop": None,
        "marginBottom": None,
        "marginLeft": None,
        "marginRight": None,
        "position": {
            "top": top,
            "left": left,
            "bottom": max(0, 1056 - top - height),
            "right": max(0, 816 - left - width),
            "preferBottom": False,
            "preferRight": False,
        },
        "scale": {"scaleX": 1, "scaleY": 1},
        "dimensions": {"width": width, "height": height},
    }
    if native_type == "Signature":
        large_styles["align"] = "signature-left"

    return {
        "type": native_type,
        "version": 2 if native_type == "Signature" else 1,
        "id": str(uuid4()),
        "children": [],
        "component": {
            "isDraggable": True,
            "name": COMPONENT_NAMES[native_type],
            "options": options,
        },
        "responsiveStyles": {
            "large": large_styles
        },
    }


def add_field(document: dict[str, Any], field: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a document with one compact field specification added."""
    result = deepcopy(document)
    pages = result.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ContractTemplateError("Template has no pages. Add a native page or use a compact create spec first.")
    page_number = field.get("page", 1)
    if not isinstance(page_number, int) or page_number < 1 or page_number > len(pages):
        raise ContractTemplateError(f"Page must be between 1 and {len(pages)}.")
    page = pages[page_number - 1]
    if not isinstance(page.get("children"), list):
        raise ContractTemplateError(f"Page {page_number} has no valid children array.")
    native = build_field(
        field.get("type", ""), pages=pages, document=result,
        label=field.get("label"), placeholder=field.get("placeholder"),
        field_id=field.get("fieldId") or field.get("field_id"),
        recipient=field.get("recipient"), entity_name=field.get("entityName") or field.get("entity_name"),
        required=field.get("required", True), top=field.get("top", 0), left=field.get("left", 0),
        width=field.get("width"), height=field.get("height"),
    )
    page["children"].append(native)
    result["fillableFields"] = compute_fillable_fields(pages)
    return result


def ensure_default_signer_fields(document: dict[str, Any]) -> dict[str, Any]:
    """Ensure both parties' required signing fields exist on the final page.

    The contractor/contact gets Full name, Date, and Signature fields assigned
    to ``assignedContact``. The company/sender gets Date and Signature fields
    assigned to ``assignedSender``. Existing correctly assigned matches retain
    their ids, placement, and styling. Unassigned semantic matches are repaired
    to the contractor so they cannot accidentally satisfy the sender defaults.
    """
    result = deepcopy(document)
    pages = result.get("pages")
    if pages is None or pages == []:
        pages = [make_letter_page()]
        result["pages"] = pages
    if not isinstance(pages, list) or not all(isinstance(page, dict) for page in pages):
        raise ContractTemplateError("Template pages must be an array of page objects.")
    final_page = pages[-1]
    children = final_page.get("children")
    if not isinstance(children, list):
        raise ContractTemplateError("The final template page has no valid children array.")

    def is_semantic_field(element: dict[str, Any], kind: str) -> bool:
        native_type = FIELD_TYPES[kind]
        if element.get("type") != native_type:
            return False
        options = element.get("component", {}).get("options", {})
        if not isinstance(options, dict):
            return False
        if kind == "name":
            placeholder = str(options.get("placeholder") or "").strip().casefold()
            if placeholder not in {"full name", "name"}:
                return False
        return True

    def has_expected_assignment(element: dict[str, Any], default: dict[str, Any]) -> bool:
        options = element["component"]["options"]
        return (
            options.get("recipient") == default["recipient"]
            and options.get("entityName") == default["entityName"]
        )

    def is_unassigned(element: dict[str, Any]) -> bool:
        options = element["component"]["options"]
        return not options.get("recipient") or not options.get("entityName")

    # An unassigned native field is a contractor field by default. Repair it
    # before matching party-specific defaults so it can never stand in for the
    # company/sender field merely because sender defaults are processed first.
    for kind in ("name", "date", "signature"):
        for element in walk_elements([final_page]):
            if is_semantic_field(element, kind) and is_unassigned(element):
                options = element["component"]["options"]
                options["recipient"] = ASSIGNED_CONTACT_ID
                options["entityName"] = "contacts"
                options["required"] = True

    for default in DEFAULT_SIGNER_FIELDS:
        kind = default["type"]
        semantic_fields = [
            element for element in walk_elements([final_page])
            if is_semantic_field(element, kind)
        ]
        matching = next(
            (element for element in semantic_fields if has_expected_assignment(element, default)),
            None,
        )
        if matching is not None:
            matching["component"]["options"]["required"] = True
        else:
            field_spec = {key: value for key, value in default.items() if key != "party"}
            result = add_field(result, {**field_spec, "page": len(pages)})
            pages = result["pages"]
            final_page = pages[-1]
    result["fillableFields"] = compute_fillable_fields(result["pages"])
    return result


def compute_fillable_fields(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rebuild the metadata array exactly as the current GHL builder does."""
    fields = []
    for element in walk_elements(pages):
        if element.get("type") not in FILLABLE_TYPES:
            continue
        options = element.get("component", {}).get("options", {})
        value = options.get("text") or ""
        fields.append({
            "value": value,
            "fieldId": options.get("fieldId"),
            "isRequired": bool(options.get("required")),
            "recipient": options.get("recipient"),
            "hasCompleted": bool(value),
            "entityType": options.get("entityName"),
            "id": element.get("id"),
            "type": element.get("type"),
        })
    return fields


def apply_template_input(
    existing: dict[str, Any], payload: dict[str, Any], location_id: str
) -> dict[str, Any]:
    """Losslessly apply a compact spec or native top-level patch to a template."""
    if not isinstance(payload, dict):
        raise ContractTemplateError("Template JSON must be an object.")
    result = deepcopy(existing)
    original_product_lists = _product_lists(existing.get("pages"))
    fields = payload.get("fields")
    for key, value in payload.items():
        if key != "fields":
            result[key] = deepcopy(value)
    if fields is not None:
        if not isinstance(fields, list):
            raise ContractTemplateError("fields must be an array.")
        if not result.get("pages"):
            result["pages"] = [make_letter_page()]
        for field in fields:
            if not isinstance(field, dict):
                raise ContractTemplateError("Every field must be an object.")
            result = add_field(result, field)
    pages = result.get("pages")
    if _product_lists(pages) != original_product_lists:
        raise ContractTemplateError(
            "ProductList page edits are not supported because GoHighLevel "
            "recomputes pricing and payment metadata in the browser builder."
        )
    if isinstance(pages, list) and (fields is not None or "pages" in payload):
        result["fillableFields"] = compute_fillable_fields(pages)
    result["locationId"] = location_id
    return sanitize_update_payload(result)


def completed_redirect_settings(document: dict[str, Any]) -> dict[str, Any]:
    """Return the builder-native completed-document redirect settings."""
    settings = document.get("redirectSettings")
    settings = deepcopy(settings) if isinstance(settings, dict) else {}
    settings.setdefault("enableDocumentRedirectUrl", False)
    settings.setdefault("documentRedirectUrl", "")
    settings.setdefault("documentRedirectType", "newTab")
    return settings


def set_completed_redirect(
    document: dict[str, Any], url: str, redirect_type: str = "existingTab"
) -> dict[str, Any]:
    """Enable a completed-document redirect using the current builder schema."""
    normalized_url = url.strip()
    if "://" in normalized_url and not normalized_url.startswith(("http://", "https://")):
        raise ContractTemplateError("Completed-document redirect must be a valid HTTP(S) URL.")
    if normalized_url and not normalized_url.startswith(("http://", "https://")):
        normalized_url = f"https://{normalized_url}"
    parsed = urlparse(normalized_url)
    try:
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        hostname = None
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or any(character.isspace() for character in normalized_url)
    ):
        raise ContractTemplateError("Completed-document redirect must be a valid HTTP(S) URL.")
    if redirect_type not in REDIRECT_TYPES:
        raise ContractTemplateError(
            "Completed-document redirect type must be 'existingTab' or 'newTab'."
        )
    result = deepcopy(document)
    settings = completed_redirect_settings(result)
    settings.update({
        "enableDocumentRedirectUrl": True,
        "documentRedirectUrl": normalized_url,
        "documentRedirectType": redirect_type,
    })
    result["redirectSettings"] = settings
    return sanitize_update_payload(result)


def prepare_template_export(document: dict[str, Any]) -> dict[str, Any]:
    """Make redirect settings explicit so export/import cannot silently omit them."""
    result = deepcopy(document)
    result["redirectSettings"] = completed_redirect_settings(result)
    return result


def sanitize_update_payload(document: dict[str, Any]) -> dict[str, Any]:
    """Match the current builder's PUT whitelist and preserve nested values."""
    result = {
        key: deepcopy(value)
        for key, value in document.items()
        if key in UPDATE_ROOT_KEYS
        and not (
            key == "thumbnail"
            and (document.get("type") != "contentLibrary" or not value)
        )
    }
    if isinstance(result.get("name"), str):
        result["name"] = result["name"].strip()

    timezone = result.get("timezone")
    explicit_timezone = os.environ.get("GHL_CONTRACT_TIMEZONE", "").strip()
    if (
        not explicit_timezone
        and isinstance(timezone, dict)
        and timezone.get("zone")
        and timezone.get("abbreviation")
    ):
        result["timezone"] = {
            key: deepcopy(timezone[key])
            for key in ("zone", "abbreviation")
            if timezone.get(key) is not None
        }
    else:
        result["timezone"] = _default_timezone()

    payment_info = result.get("paymentInfo")
    if isinstance(payment_info, dict):
        result["paymentInfo"] = {
            key: deepcopy(value)
            for key, value in payment_info.items()
            if key in PAYMENT_INFO_KEYS
        }
    elif "paymentInfo" in result:
        result["paymentInfo"] = {}

    grand_total = result.get("grandTotal")
    if isinstance(grand_total, dict):
        result["grandTotal"] = {
            key: deepcopy(value)
            for key, value in grand_total.items()
            if key in GRAND_TOTAL_KEYS
        }

    notification_settings = result.get("notificationSettings")
    if isinstance(notification_settings, dict):
        notification_settings.pop("value", None)
    else:
        result["notificationSettings"] = {}
    if not isinstance(result.get("customValueLinkage"), dict):
        result["customValueLinkage"] = {}
    if not isinstance(result.get("redirectSettings"), dict):
        result["redirectSettings"] = {}
    if not isinstance(result.get("emailAttachments"), list):
        result["emailAttachments"] = []
    if result.get("paymentLiveMode") is None:
        result["paymentLiveMode"] = True
    if not isinstance(result.get("roles"), list):
        result["roles"] = []

    recipients = result.get("recipients")
    if isinstance(recipients, list):
        result["recipients"] = [
            recipient for recipient in recipients
            if isinstance(recipient, dict)
            and recipient.get("id") not in {"assignedContact", "assignedSender"}
            and recipient.get("entityName") != "role"
        ]
    redirect_settings = result.get("redirectSettings", {})
    redirect_url = redirect_settings.get("documentRedirectUrl")
    if (
        isinstance(redirect_url, str) and redirect_url
        and not redirect_url.startswith(("http://", "https://"))
    ):
        redirect_settings["documentRedirectUrl"] = f"https://{redirect_url}"
    redirect_type = redirect_settings.get("documentRedirectType")
    if redirect_type is not None and redirect_type not in REDIRECT_TYPES:
        raise ContractTemplateError(
            "redirectSettings.documentRedirectType must be 'existingTab' or 'newTab'."
        )
    return result
