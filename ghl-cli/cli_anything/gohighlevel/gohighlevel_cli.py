"""GoHighLevel CLI — Agent-usable command-line interface to the GHL API."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import click

from cli_anything.gohighlevel import __version__
import requests

from cli_anything.gohighlevel.utils import ghl_client as api
from cli_anything.gohighlevel.utils import saas_audit as saas_audit_utils
from cli_anything.gohighlevel.utils import saas_lifecycle as saas_lifecycle_utils

# Ghost ink is an optional module. Distributed builds ship without it, so the
# flags below are hidden rather than advertised as options that cannot work.
# Resolved at import time because Click needs it when building the decorators.
GHOST_INK_AVAILABLE = (
    importlib.util.find_spec("cli_anything.gohighlevel.utils.ghost_ink") is not None
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app_domain() -> str:
    """Host for the links handed back to the operator.

    GoHighLevel agencies white-label the app onto their own domain, so a
    hardcoded host sends everyone else to somebody else's login page. Read at
    call time, not import time, because the wrapper sources the credential
    profile into the environment.
    """
    return os.environ.get("GHL_APP_DOMAIN", "").strip() or "app.gohighlevel.com"


def _output(ctx: click.Context, data, label: str = ""):
    """Print data respecting --json flag."""
    as_json = ctx.obj.get("json", False)
    # Internal-API calls report failure in-band. Never render one as data —
    # an empty-looking success is worse than a loud error.
    if isinstance(data, dict) and data.get("_error"):
        code = data.get("code", "")
        prefix = f"API Error ({code})" if code else "API Error"
        click.echo(f"{prefix}: {data.get('message', 'unknown error')}", err=True)
        # SystemExit, not ctx.exit(): click's Exit subclasses RuntimeError and
        # would be swallowed by each command's `except Exception` handler,
        # turning a hard failure back into a zero exit code.
        raise SystemExit(1)
    if data is None:
        click.echo("No response from the API (no data returned).", err=True)
        raise SystemExit(1)
    if as_json:
        click.echo(json.dumps(data, indent=2, default=str))
    else:
        if label:
            click.echo(f"\n{label}")
            click.echo("-" * len(label))
        click.echo(api.format_output(data))


def _handle_error(e: Exception):
    """Handle API errors with clear messages."""
    if isinstance(e, requests.exceptions.HTTPError):
        resp = e.response
        try:
            body = resp.json()
            msg = body.get("message") or body.get("msg") or json.dumps(body)
        except Exception:
            msg = resp.text
        click.echo(f"API Error ({resp.status_code}): {msg}", err=True)
    else:
        click.echo(f"Error: {e}", err=True)
    sys.exit(1)


def _loc(ctx: click.Context) -> str:
    """Get location ID from context or env."""
    return ctx.obj.get("location_id") or api._get_location_id()


def _merge_fields(body: dict, fields: tuple[str, ...]) -> dict:
    """Merge repeatable --field key=value overrides into body.

    Each value is parsed as JSON when possible (so `isActive=true` -> bool,
    `slotDuration=30` -> int, `teamMembers=[{...}]` -> list) and falls back to
    a plain string otherwise.
    """
    for item in fields:
        if "=" not in item:
            raise click.BadParameter(f"--field must be key=value, got: {item!r}")
        key, _, raw = item.partition("=")
        key = key.strip()
        try:
            value = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            value = raw
        body[key] = value
    return body


# ---------------------------------------------------------------------------
# Main CLI Group
# ---------------------------------------------------------------------------

@click.group(invoke_without_command=True)
@click.option("--json", "use_json", is_flag=True, help="Output as JSON")
@click.option("--location-id", envvar="GHL_LOCATION_ID", default=None, help="GHL Location/Sub-account ID")
@click.option("--experimental", is_flag=True, help="Enable experimental commands (UNOFFICIAL internal GHL API — own-account-only, uses your full Firebase session token)")
@click.version_option(__version__, prog_name="cli-anything-gohighlevel")
@click.pass_context
def cli(ctx, use_json, location_id, experimental):
    """GoHighLevel CLI — manage contacts, workflows, calendars, and more."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = use_json
    ctx.obj["location_id"] = location_id
    ctx.obj["experimental"] = experimental
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


# ---------------------------------------------------------------------------
# REPL Command
# ---------------------------------------------------------------------------

@cli.command(hidden=True)
@click.pass_context
def repl(ctx):
    """Interactive REPL mode."""
    try:
        from cli_anything.gohighlevel.utils.repl_skin import ReplSkin
        skin = ReplSkin("gohighlevel", version=__version__)
        skin.print_banner()
        pt_session = skin.create_prompt_session()

        commands = {
            "contacts": "Manage contacts (list, get, create, update, delete, search, tags)",
            "opportunities": "Manage pipeline opportunities (list, get, create, update, delete)",
            "calendars": "Manage calendars and appointments (list, slots, book)",
            "workflows": "List and manage workflows",
            "conversations": "Manage conversations and messages",
            "emails": "Email campaigns (list, get, send)",
            "payments": "Transactions, subscriptions, invoices, orders",
            "forms": "Forms and submissions",
            "documents": "Documents, contracts, and templates",
            "social": "Social media posts and analytics",
            "locations": "Location/sub-account management",
            "saas": "Read agency SaaS sub-account subscriptions and plans",
            "help": "Show this help",
            "exit": "Exit REPL",
        }

        while True:
            try:
                line = skin.get_input(pt_session, project_name="ghl")
                if not line or not line.strip():
                    continue
                parts = line.strip().split()
                cmd = parts[0].lower()

                if cmd in ("exit", "quit", "q"):
                    skin.print_goodbye()
                    break
                elif cmd == "help":
                    skin.help(commands)
                else:
                    # Pass through to Click CLI
                    try:
                        cli.main(parts, standalone_mode=False, obj=ctx.obj)
                    except SystemExit:
                        pass
                    except click.exceptions.UsageError as e:
                        skin.error(str(e))
            except (EOFError, KeyboardInterrupt):
                skin.print_goodbye()
                break
    except ImportError:
        click.echo("REPL requires prompt-toolkit. Install with: pip install prompt-toolkit")
        click.echo("Use subcommands directly instead: ghl contacts list")


# ===========================================================================
# CONTACTS
# ===========================================================================

@cli.group()
@click.pass_context
def contacts(ctx):
    """Manage contacts — list, get, create, update, delete, search, tags."""
    pass


@contacts.command("list")
@click.option("--limit", default=20, help="Number of contacts to return")
@click.option("--offset", "skip", default=0, help="Number to skip (for pagination)")
@click.option("--query", default=None, help="Search query string")
@click.pass_context
def contacts_list(ctx, limit, skip, query):
    """List contacts in the location."""
    try:
        params = {"locationId": _loc(ctx), "limit": limit, "startAfterId": skip if skip else None}
        if query:
            params["query"] = query
        data = api.get("/contacts/", params=params)
        contacts_data = data.get("contacts", data)
        _output(ctx, contacts_data if ctx.obj["json"] else data, "Contacts")
    except Exception as e:
        _handle_error(e)


@contacts.command("get")
@click.argument("contact_id")
@click.pass_context
def contacts_get(ctx, contact_id):
    """Get a single contact by ID."""
    try:
        data = api.get(f"/contacts/{contact_id}")
        _output(ctx, data, "Contact Details")
    except Exception as e:
        _handle_error(e)


@contacts.command("create")
@click.option("--email", default=None, help="Contact email")
@click.option("--phone", default=None, help="Contact phone")
@click.option("--first-name", default=None, help="First name")
@click.option("--last-name", default=None, help="Last name")
@click.option("--name", default=None, help="Full name")
@click.option("--company", "company_name", default=None, help="Company name")
@click.option("--tag", "tags", multiple=True, help="Tags to add (repeatable)")
@click.option("--source", default=None, help="Contact source")
@click.pass_context
def contacts_create(ctx, email, phone, first_name, last_name, name, company_name, tags, source):
    """Create a new contact."""
    try:
        body = {"locationId": _loc(ctx)}
        if email:
            body["email"] = email
        if phone:
            body["phone"] = phone
        if first_name:
            body["firstName"] = first_name
        if last_name:
            body["lastName"] = last_name
        if name:
            body["name"] = name
        if company_name:
            body["companyName"] = company_name
        if tags:
            body["tags"] = list(tags)
        if source:
            body["source"] = source
        data = api.post("/contacts/", data=body)
        _output(ctx, data, "Contact Created")
    except Exception as e:
        _handle_error(e)


@contacts.command("update")
@click.argument("contact_id")
@click.option("--email", default=None)
@click.option("--phone", default=None)
@click.option("--first-name", default=None)
@click.option("--last-name", default=None)
@click.option("--company", "company_name", default=None)
@click.option("--tag", "tags", multiple=True, help="Replace all tags")
@click.pass_context
def contacts_update(ctx, contact_id, email, phone, first_name, last_name, company_name, tags):
    """Update a contact by ID."""
    try:
        body = {}
        if email:
            body["email"] = email
        if phone:
            body["phone"] = phone
        if first_name:
            body["firstName"] = first_name
        if last_name:
            body["lastName"] = last_name
        if company_name:
            body["companyName"] = company_name
        if tags:
            body["tags"] = list(tags)
        data = api.put(f"/contacts/{contact_id}", data=body)
        _output(ctx, data, "Contact Updated")
    except Exception as e:
        _handle_error(e)


@contacts.command("delete")
@click.argument("contact_id")
@click.pass_context
def contacts_delete(ctx, contact_id):
    """Delete a contact by ID."""
    try:
        data = api.delete(f"/contacts/{contact_id}")
        _output(ctx, data, "Contact Deleted")
    except Exception as e:
        _handle_error(e)


@contacts.command("search")
@click.argument("query")
@click.option("--limit", default=20)
@click.pass_context
def contacts_search(ctx, query, limit):
    """Search contacts with advanced filters."""
    try:
        # pageLimit, not pageSize (422 otherwise). Free-text `query` searches
        # name, email and phone; the old firstNameLowerCase filter meant an
        # email or domain search silently matched nothing.
        body = {
            "locationId": _loc(ctx),
            "pageLimit": limit,
            "query": query,
        }
        data = api.post("/contacts/search", data=body)
        _output(ctx, data, f"Search: '{query}'")
    except Exception as e:
        _handle_error(e)


@contacts.command("add-tag")
@click.argument("contact_id")
@click.argument("tags", nargs=-1, required=True)
@click.pass_context
def contacts_add_tag(ctx, contact_id, tags):
    """Add tags to a contact."""
    try:
        data = api.post(f"/contacts/{contact_id}/tags", data={"tags": list(tags)})
        _output(ctx, data, "Tags Added")
    except Exception as e:
        _handle_error(e)


@contacts.command("remove-tag")
@click.argument("contact_id")
@click.argument("tags", nargs=-1, required=True)
@click.pass_context
def contacts_remove_tag(ctx, contact_id, tags):
    """Remove tags from a contact."""
    try:
        data = api.delete(f"/contacts/{contact_id}/tags", data={"tags": list(tags)})
        _output(ctx, data, "Tags Removed")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# OPPORTUNITIES
# ===========================================================================

@cli.group()
@click.pass_context
def opportunities(ctx):
    """Manage pipeline opportunities — list, get, create, update, delete."""
    pass


@opportunities.command("list")
@click.option("--pipeline-id", default=None, help="Filter by pipeline ID")
@click.option("--limit", default=20)
@click.option("--status", default=None, type=click.Choice(["open", "won", "lost", "abandoned"]))
@click.pass_context
def opportunities_list(ctx, pipeline_id, limit, status):
    """List opportunities."""
    try:
        # /opportunities/search is the odd one out: it wants snake_case
        # location_id and rejects the camelCase locationId every other
        # endpoint uses.
        params = {"location_id": _loc(ctx), "limit": limit}
        if pipeline_id:
            params["pipelineId"] = pipeline_id
        if status:
            params["status"] = status
        data = api.get("/opportunities/search", params=params)
        _output(ctx, data, "Opportunities")
    except Exception as e:
        _handle_error(e)


@opportunities.command("get")
@click.argument("opportunity_id")
@click.pass_context
def opportunities_get(ctx, opportunity_id):
    """Get opportunity details."""
    try:
        data = api.get(f"/opportunities/{opportunity_id}")
        _output(ctx, data, "Opportunity Details")
    except Exception as e:
        _handle_error(e)


@opportunities.command("create")
@click.option("--pipeline-id", required=True, help="Pipeline ID")
@click.option("--stage-id", required=True, help="Stage ID")
@click.option("--name", required=True, help="Opportunity name")
@click.option("--contact-id", required=True, help="Contact ID")
@click.option("--value", "monetary_value", default=None, type=float, help="Monetary value")
@click.option("--status", default="open", type=click.Choice(["open", "won", "lost", "abandoned"]))
@click.pass_context
def opportunities_create(ctx, pipeline_id, stage_id, name, contact_id, monetary_value, status):
    """Create a new opportunity."""
    try:
        body = {
            "locationId": _loc(ctx),
            "pipelineId": pipeline_id,
            "pipelineStageId": stage_id,
            "name": name,
            "contactId": contact_id,
            "status": status,
        }
        if monetary_value is not None:
            body["monetaryValue"] = monetary_value
        data = api.post("/opportunities/", data=body)
        _output(ctx, data, "Opportunity Created")
    except Exception as e:
        _handle_error(e)


@opportunities.command("update")
@click.argument("opportunity_id")
@click.option("--name", default=None)
@click.option("--stage-id", default=None, help="Move to stage")
@click.option("--status", default=None, type=click.Choice(["open", "won", "lost", "abandoned"]))
@click.option("--value", "monetary_value", default=None, type=float)
@click.pass_context
def opportunities_update(ctx, opportunity_id, name, stage_id, status, monetary_value):
    """Update an opportunity."""
    try:
        body = {}
        if name:
            body["name"] = name
        if stage_id:
            body["pipelineStageId"] = stage_id
        if status:
            body["status"] = status
        if monetary_value is not None:
            body["monetaryValue"] = monetary_value
        data = api.put(f"/opportunities/{opportunity_id}", data=body)
        _output(ctx, data, "Opportunity Updated")
    except Exception as e:
        _handle_error(e)


@opportunities.command("delete")
@click.argument("opportunity_id")
@click.pass_context
def opportunities_delete(ctx, opportunity_id):
    """Delete an opportunity."""
    try:
        data = api.delete(f"/opportunities/{opportunity_id}")
        _output(ctx, data, "Opportunity Deleted")
    except Exception as e:
        _handle_error(e)


@opportunities.command("pipelines")
@click.pass_context
def opportunities_pipelines(ctx):
    """List all pipelines."""
    try:
        data = api.get("/opportunities/pipelines", params={"locationId": _loc(ctx)})
        _output(ctx, data, "Pipelines")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# CALENDARS
# ===========================================================================

@cli.group()
@click.pass_context
def calendars(ctx):
    """Manage calendars, appointments, and availability slots."""
    pass


@calendars.command("list")
@click.pass_context
def calendars_list(ctx):
    """List all calendars."""
    try:
        data = api.get("/calendars/", params={"locationId": _loc(ctx)})
        _output(ctx, data, "Calendars")
    except Exception as e:
        _handle_error(e)


@calendars.command("get")
@click.argument("calendar_id")
@click.pass_context
def calendars_get(ctx, calendar_id):
    """Get calendar details."""
    try:
        data = api.get(f"/calendars/{calendar_id}")
        _output(ctx, data, "Calendar Details")
    except Exception as e:
        _handle_error(e)



def _to_epoch_ms(value, end_of_day: bool = False, tz: str | None = None) -> int:
    """Accept YYYY-MM-DD, ISO 8601, or epoch ms; return epoch ms.

    Bare dates are read in `tz` (IANA name) when given, else local time.
    """
    import datetime as _dt
    v = str(value).strip()
    if v.isdigit():
        return int(v)
    if len(v) == 10:
        d = _dt.datetime.strptime(v, "%Y-%m-%d")
        if tz:
            from zoneinfo import ZoneInfo
            d = d.replace(tzinfo=ZoneInfo(tz))
        if end_of_day:
            d = d.replace(hour=23, minute=59, second=59)
    else:
        d = _dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    return int(d.timestamp() * 1000)


@calendars.command("slots")
@click.argument("calendar_id")
@click.option("--start", required=True, help="Start date (YYYY-MM-DD or epoch ms)")
@click.option("--end", required=True, help="End date (YYYY-MM-DD or epoch ms)")
@click.option("--timezone", default="America/New_York")
@click.pass_context
def calendars_slots(ctx, calendar_id, start, end, timezone):
    """Get available appointment slots."""
    try:
        params = {
            "startDate": _to_epoch_ms(start, tz=timezone),
            "endDate": _to_epoch_ms(end, end_of_day=True, tz=timezone),
            "timezone": timezone,
        }
        data = api.get(f"/calendars/{calendar_id}/free-slots", params=params)
        _output(ctx, data, "Available Slots")
    except Exception as e:
        _handle_error(e)


@calendars.command("appointments")
@click.option("--calendar-id", default=None, help="Filter by calendar ID")
@click.option("--contact-id", default=None, help="Filter by contact ID")
@click.option("--start", default=None, help="Start date filter")
@click.option("--end", default=None, help="End date filter")
@click.pass_context
def calendars_appointments(ctx, calendar_id, contact_id, start, end):
    """List appointments."""
    try:
        import time as _time
        now_ms = int(_time.time() * 1000)
        params = {
            "locationId": _loc(ctx),
            "startTime": _to_epoch_ms(start) if start else now_ms - 30 * 86400000,
            "endTime": _to_epoch_ms(end, end_of_day=True) if end else now_ms + 30 * 86400000,
        }
        # GET /calendars/events requires one of calendarId/userId/groupId;
        # with none given, sweep every calendar in the location.
        cal_ids = [calendar_id] if calendar_id else [
            c["id"] for c in api.get("/calendars/", params={"locationId": _loc(ctx)}).get("calendars", [])
        ]
        events = []
        for cid in cal_ids:
            events += api.get("/calendars/events", params={**params, "calendarId": cid}).get("events", [])
        if contact_id:
            events = [e for e in events if e.get("contactId") == contact_id]
        data = {"events": events, "total": len(events)}
        _output(ctx, data, "Appointments")
    except Exception as e:
        _handle_error(e)


@calendars.command("book")
@click.option("--calendar-id", required=True, help="Calendar ID")
@click.option("--contact-id", required=True, help="Contact ID")
@click.option("--slot-id", required=True, help="Slot ID from 'slots' command")
@click.option("--start", required=True, help="Start time (ISO 8601)")
@click.option("--end", required=True, help="End time (ISO 8601)")
@click.option("--title", default=None, help="Appointment title")
@click.pass_context
def calendars_book(ctx, calendar_id, contact_id, slot_id, start, end, title):
    """Book an appointment."""
    try:
        body = {
            "calendarId": calendar_id,
            "locationId": _loc(ctx),
            "contactId": contact_id,
            "selectedSlot": slot_id,
            "startTime": start,
            "endTime": end,
        }
        if title:
            body["title"] = title
        data = api.post("/calendars/events/appointments", data=body)
        _output(ctx, data, "Appointment Booked")
    except Exception as e:
        _handle_error(e)


@calendars.command("groups")
@click.pass_context
def calendars_groups(ctx):
    """List calendar groups."""
    try:
        data = api.get("/calendars/groups", params={"locationId": _loc(ctx)})
        _output(ctx, data, "Calendar Groups")
    except Exception as e:
        _handle_error(e)


@calendars.command("create")
@click.option("--name", default=None, help="Calendar name")
@click.option("--calendar-type", default=None,
              type=click.Choice([
                  "round_robin", "event", "class_booking",
                  "collective", "service_booking", "personal",
              ]),
              help="Calendar type (GHL defaults to round_robin if omitted)")
@click.option("--description", default=None, help="Calendar description")
@click.option("--group-id", default=None, help="Calendar group ID")
@click.option("--slug", default=None, help="Booking widget slug")
@click.option("--team-member", "team_members", multiple=True,
              help="Team member user ID (repeatable)")
@click.option("--slot-duration", default=None, type=int, help="Slot duration value")
@click.option("--slot-duration-unit", default=None,
              type=click.Choice(["mins", "hours"]), help="Slot duration unit")
@click.option("--active/--inactive", "is_active", default=None,
              help="Set the calendar active or inactive")
@click.option("--from-json", "json_file", default=None, type=click.Path(exists=True),
              help="Load the request body from a JSON file (base; options override it)")
@click.option("--field", "fields", multiple=True,
              help="Any other body field as key=value (JSON value if parseable, repeatable)")
@click.pass_context
def calendars_create(ctx, name, calendar_type, description, group_id, slug,
                     team_members, slot_duration, slot_duration_unit,
                     is_active, json_file, fields):
    """Create a calendar.

    Common fields are exposed as options; use --from-json for a full payload
    and --field key=value for anything not covered (e.g. openHours,
    availabilities, notifications).
    """
    try:
        body: dict = {}
        if json_file:
            with open(json_file) as f:
                body = json.load(f)
        if name is not None:
            body["name"] = name
        if calendar_type is not None:
            body["calendarType"] = calendar_type
        if description is not None:
            body["description"] = description
        if group_id is not None:
            body["groupId"] = group_id
        if slug is not None:
            body["slug"] = slug
        if team_members:
            body["teamMembers"] = [{"userId": uid, "priority": 1.0} for uid in team_members]
        if slot_duration is not None:
            body["slotDuration"] = slot_duration
        if slot_duration_unit is not None:
            body["slotDurationUnit"] = slot_duration_unit
        if is_active is not None:
            body["isActive"] = is_active
        _merge_fields(body, fields)
        body.setdefault("locationId", _loc(ctx))
        if not body.get("name"):
            raise click.UsageError("Calendar name is required (--name or via --from-json).")
        data = api.post("/calendars/", data=body)
        _output(ctx, data, "Calendar Created")
    except Exception as e:
        _handle_error(e)


@calendars.command("update")
@click.argument("calendar_id")
@click.option("--name", default=None, help="Calendar name")
@click.option("--description", default=None, help="Calendar description")
@click.option("--group-id", default=None, help="Calendar group ID")
@click.option("--slug", default=None, help="Booking widget slug")
@click.option("--team-member", "team_members", multiple=True,
              help="Team member user ID (replaces the team list, repeatable)")
@click.option("--slot-duration", default=None, type=int, help="Slot duration value")
@click.option("--slot-duration-unit", default=None,
              type=click.Choice(["mins", "hours"]), help="Slot duration unit")
@click.option("--active/--inactive", "is_active", default=None,
              help="Set the calendar active or inactive")
@click.option("--from-json", "json_file", default=None, type=click.Path(exists=True),
              help="Load the request body from a JSON file (base; options override it)")
@click.option("--field", "fields", multiple=True,
              help="Any other body field as key=value (JSON value if parseable, repeatable)")
@click.pass_context
def calendars_update(ctx, calendar_id, name, description, group_id, slug,
                     team_members, slot_duration, slot_duration_unit,
                     is_active, json_file, fields):
    """Update a calendar by ID (only the fields you pass are changed)."""
    try:
        body: dict = {}
        if json_file:
            with open(json_file) as f:
                body = json.load(f)
        if name is not None:
            body["name"] = name
        if description is not None:
            body["description"] = description
        if group_id is not None:
            body["groupId"] = group_id
        if slug is not None:
            body["slug"] = slug
        if team_members:
            body["teamMembers"] = [{"userId": uid, "priority": 1.0} for uid in team_members]
        if slot_duration is not None:
            body["slotDuration"] = slot_duration
        if slot_duration_unit is not None:
            body["slotDurationUnit"] = slot_duration_unit
        if is_active is not None:
            body["isActive"] = is_active
        _merge_fields(body, fields)
        if not body:
            raise click.UsageError("Nothing to update — pass at least one field.")
        data = api.put(f"/calendars/{calendar_id}", data=body)
        _output(ctx, data, "Calendar Updated")
    except Exception as e:
        _handle_error(e)


@calendars.command("delete")
@click.argument("calendar_id")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def calendars_delete(ctx, calendar_id, yes):
    """Delete a calendar by ID.

    WARNING: GHL does NOT audit-log calendar-object deletions, so a deleted
    calendar cannot be recovered from the audit trail — recovery requires
    escalating to GHL Support. Use with care.
    """
    try:
        if not yes:
            click.confirm(
                f"Delete calendar {calendar_id}? GHL does not audit-log calendar "
                "deletions — this is unrecoverable except via GHL Support. Continue?",
                abort=True,
            )
        data = api.delete(f"/calendars/{calendar_id}")
        _output(ctx, data, "Calendar Deleted")
    except click.Abort:
        click.echo("Aborted.", err=True)
        sys.exit(1)
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# WORKFLOWS
# ===========================================================================

def _require_experimental(ctx: click.Context):
    """Guard: exit if --experimental flag not set."""
    if not ctx.obj.get("experimental"):
        click.echo(
            "Error: This command requires --experimental flag (uses internal GHL API).\n"
            "Usage: ghl --experimental <group> <command> ...",
            err=True,
        )
        sys.exit(1)


def _get_internal_client(ctx: click.Context):
    """Get an InternalGHLClient (lazy import to avoid dep when not needed)."""
    from cli_anything.gohighlevel.utils.ghl_internal_client import TokenManager, InternalGHLClient
    token_mgr = TokenManager()
    return InternalGHLClient(token_mgr, _loc(ctx))


@cli.group()
@click.pass_context
def workflows(ctx):
    """List and manage workflows. Create commands require --experimental."""
    pass


@workflows.command("list")
@click.pass_context
def workflows_list(ctx):
    """List all workflows."""
    try:
        data = api.get("/workflows/", params={"locationId": _loc(ctx)})
        _output(ctx, data, "Workflows")
    except Exception as e:
        _handle_error(e)


@workflows.command("enroll")
@click.option("--contact-id", required=True, help="Contact ID to enroll")
@click.option("--workflow-id", required=True, help="Workflow ID")
@click.pass_context
def workflows_enroll(ctx, contact_id, workflow_id):
    """Enroll a contact in a workflow (public API)."""
    try:
        data = api.post(f"/contacts/{contact_id}/workflow/{workflow_id}")
        _output(ctx, data, "Contact Enrolled")
    except Exception as e:
        _handle_error(e)


@workflows.command("remove")
@click.option("--contact-id", required=True, help="Contact ID to remove")
@click.option("--workflow-id", required=True, help="Workflow ID")
@click.pass_context
def workflows_remove(ctx, contact_id, workflow_id):
    """Remove a contact from a workflow (public API)."""
    try:
        data = api.delete(f"/contacts/{contact_id}/workflow/{workflow_id}")
        _output(ctx, data, "Contact Removed from Workflow")
    except Exception as e:
        _handle_error(e)


@workflows.command("create")
@click.option("--name", required=True, help="Workflow name")
@click.option("--folder", default=None, help="Folder name (created if needed)")
@click.option("--from-json", "json_file", required=True, type=click.Path(exists=True),
              help="Campaign JSON file path")
@click.pass_context
def workflows_create(ctx, name, folder, json_file):
    """Create workflows from a campaign JSON file (experimental, internal API).

    The JSON file should contain a campaign dict where each key is a workflow
    with 'name', 'templates' (linked steps), and optional 'tag' (trigger).
    """
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils.workflow_builder import CampaignBuilder

        with open(json_file) as f:
            campaign = json.load(f)

        client = _get_internal_client(ctx)
        builder = CampaignBuilder(client)
        stats = builder.build(campaign, folder or name)

        if ctx.obj["json"]:
            click.echo(json.dumps(stats, indent=2, default=str))
        else:
            click.echo(builder.format_summary())
    except Exception as e:
        _handle_error(e)


@workflows.command("create-step")
@click.option("--type", "step_type", required=True,
              type=click.Choice(["email", "sms", "wait", "tag", "webhook", "ai"]))
@click.option("--name", required=True, help="Step name")
@click.option("--output-file", "out_file", required=True, type=click.Path(),
              help="JSON file to append step to")
@click.option("--subject", default=None, help="Email subject (email type)")
@click.option("--body", default=None, help="Message body (email/sms type)")
@click.option("--from-name", default="", help="Sender name (email type)")
@click.option("--value", default=None, type=int, help="Wait value (wait type)")
@click.option("--unit", default="days", type=click.Choice(["minutes", "hours", "days"]),
              help="Wait unit (wait type)")
@click.option("--tags", default=None, help="Comma-separated tags (tag type)")
@click.option("--remove-tags", is_flag=True, help="Remove tags instead of add (tag type)")
@click.option("--url", default=None, help="Webhook URL (webhook type)")
@click.option("--method", default="POST", help="HTTP method (webhook type)")
@click.option("--prompt", default=None, help="AI prompt (ai type)")
@click.option("--model", default="gpt-4o", help="AI model (ai type)")
@click.pass_context
def workflows_create_step(ctx, step_type, name, out_file, subject, body, from_name,
                          value, unit, tags, remove_tags, url, method, prompt, model):
    """Build a workflow step and append to a JSON file (experimental).

    Use repeatedly to build up a workflow step-by-step, then pass the
    file to 'workflows create --from-json'.
    """
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils import workflow_builder as wb

        if step_type == "email":
            if not subject or not body:
                click.echo("Error: --subject and --body required for email step", err=True)
                sys.exit(1)
            step = wb.email_step(name, subject, body, from_name)
        elif step_type == "sms":
            if not body:
                click.echo("Error: --body required for sms step", err=True)
                sys.exit(1)
            step = wb.sms_step(name, body)
        elif step_type == "wait":
            if value is None:
                click.echo("Error: --value required for wait step", err=True)
                sys.exit(1)
            step = wb.wait_step(name, value, unit)
        elif step_type == "tag":
            if not tags:
                click.echo("Error: --tags required for tag step", err=True)
                sys.exit(1)
            step = wb.tag_step(name, [t.strip() for t in tags.split(",")], remove=remove_tags)
        elif step_type == "webhook":
            if not url:
                click.echo("Error: --url required for webhook step", err=True)
                sys.exit(1)
            step = wb.webhook_step(name, url, method)
        elif step_type == "ai":
            if not prompt:
                click.echo("Error: --prompt required for ai step", err=True)
                sys.exit(1)
            step = wb.ai_step(name, prompt, model)
        else:
            click.echo(f"Error: Unknown step type: {step_type}", err=True)
            sys.exit(1)

        # Load existing or start fresh
        import os
        if os.path.exists(out_file):
            with open(out_file) as f:
                steps = json.load(f)
        else:
            steps = []

        steps.append(step)

        # Auto-link all steps
        linked = wb.link_steps(steps)
        with open(out_file, "w") as f:
            json.dump(linked, f, indent=2)

        if ctx.obj["json"]:
            click.echo(json.dumps(step, indent=2))
        else:
            click.echo(f"Step added: {step['name']} ({step['type']})")
            click.echo(f"Total steps in {out_file}: {len(linked)}")
    except Exception as e:
        _handle_error(e)


@workflows.command("create-n8n")
@click.option("--name", required=True, help="Workflow name")
@click.option("--webhook-url", required=True, help="n8n webhook URL")
@click.option("--tag", default=None, help="Trigger tag (creates tag trigger)")
@click.option("--folder", default=None, help="Folder name")
@click.pass_context
def workflows_create_n8n(ctx, name, webhook_url, tag, folder):
    """Create a minimal GHL workflow that triggers an n8n webhook (experimental).

    Creates: [tag trigger] → [webhook POST to n8n URL]
    """
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils import workflow_builder as wb

        steps = [wb.webhook_step(f"n8n: {name}", webhook_url, "POST")]
        if tag:
            steps.insert(0, wb.tag_step(f"Tag: {tag}", [tag]))

        linked = wb.link_steps(steps)
        campaign = {
            "n8n_bridge": {
                "name": name,
                "templates": linked,
                "tag": tag,
            }
        }

        from cli_anything.gohighlevel.utils.workflow_builder import CampaignBuilder
        client = _get_internal_client(ctx)
        builder = CampaignBuilder(client)
        stats = builder.build(campaign, folder or f"n8n-{name}")

        if ctx.obj["json"]:
            click.echo(json.dumps(stats, indent=2, default=str))
        else:
            click.echo(builder.format_summary())
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# DOCUMENTS / CONTRACTS
# ===========================================================================

@cli.group()
@click.pass_context
def documents(ctx):
    """Documents, contracts, and proposals — list, send, templates."""
    pass


@documents.command("list")
@click.option("--status", default=None, type=click.Choice(["draft", "sent", "viewed", "completed", "accepted"]))
@click.option("--payment-status", default=None, type=click.Choice(["waiting_for_payment", "paid", "no_payment"]))
@click.option("--limit", default=20)
@click.option("--offset", "skip", default=0)
@click.option("--query", default=None, help="Search by name")
@click.pass_context
def documents_list(ctx, status, payment_status, limit, skip, query):
    """List documents/contracts."""
    try:
        params = {"locationId": _loc(ctx), "limit": limit, "skip": skip}
        if status:
            params["status"] = status
        if payment_status:
            params["paymentStatus"] = payment_status
        if query:
            params["query"] = query
        data = api.get("/proposals/document", params=params)
        _output(ctx, data, "Documents")
    except Exception as e:
        _handle_error(e)


@documents.command("templates")
@click.option("--type", "template_type", default=None, type=click.Choice(["proposal", "estimate", "contentLibrary"]))
@click.option("--name", default=None, help="Filter by template name")
@click.option("--limit", default=20)
@click.pass_context
def documents_templates(ctx, template_type, name, limit):
    """List document/contract templates."""
    try:
        params = {"locationId": _loc(ctx), "limit": limit}
        if template_type:
            params["type"] = template_type
        if name:
            params["name"] = name
        data = api.get("/proposals/templates", params=params)
        _output(ctx, data, "Document Templates")
    except Exception as e:
        _handle_error(e)


@documents.command("send")
@click.option("--document-id", required=True, help="Document ID to send")
@click.option("--sent-by", required=True, help="User ID of sender")
@click.option("--medium", default="email", type=click.Choice(["email", "link"]), help="Delivery method")
@click.option("--name", "document_name", default=None, help="Document name override")
@click.pass_context
def documents_send(ctx, document_id, sent_by, medium, document_name):
    """Send an existing document to its recipients."""
    try:
        body = {
            "locationId": _loc(ctx),
            "documentId": document_id,
            "sentBy": sent_by,
            "medium": medium,
        }
        if document_name:
            body["documentName"] = document_name
        data = api.post("/proposals/document/send", data=body)
        _output(ctx, data, "Document Sent")
    except Exception as e:
        _handle_error(e)


@documents.command("send-template")
@click.option("--template-id", required=True, help="Template ID")
@click.option("--contact-id", required=True, help="Contact ID to send to")
@click.option("--user-id", required=True, help="User ID (sender)")
@click.option("--opportunity-id", default=None, help="Link to opportunity")
@click.option("--send/--no-send", "send_document", default=True, help="Send immediately or just create")
@click.pass_context
def documents_send_template(ctx, template_id, contact_id, user_id, opportunity_id, send_document):
    """Create and send a contract from a template."""
    try:
        body = {
            "templateId": template_id,
            "contactId": contact_id,
            "userId": user_id,
            "locationId": _loc(ctx),
            "sendDocument": send_document,
        }
        if opportunity_id:
            body["opportunityId"] = opportunity_id
        data = api.post("/proposals/templates/send", data=body)
        _output(ctx, data, "Template Sent")
    except Exception as e:
        _handle_error(e)


def _contract_json(path):
    """Load one contract template input file."""
    with open(path, encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise click.UsageError("Contract template JSON must be an object.")
    return value


def _contract_result(value, operation):
    """Reject structured internal-client failures instead of printing success."""
    if not isinstance(value, dict):
        raise RuntimeError(f"{operation} returned no template object.")
    if value.get("_error"):
        raise RuntimeError(f"{operation} failed: {value.get('message', 'unknown error')}")
    return value.get("data") if isinstance(value.get("data"), dict) else value


def _created_template_id(value):
    record = _contract_result(value, "Create template")
    template_id = record.get("id") or record.get("_id")
    if not template_id:
        raise RuntimeError("Create template response did not include an id.")
    return template_id


def _verify_contract_persisted(expected, actual, operation):
    """Fail loudly when GHL accepts a write but stores different content."""
    actual = _contract_result(actual, operation)
    for key in ("name", "pages", "groups", "fillableFields"):
        if key in expected and actual.get(key) != expected.get(key):
            raise RuntimeError(
                f"{operation} did not persist {key!r}. The template was "
                "re-read and differs from the submitted payload. Export it "
                "before retrying."
            )
    expected_redirect = expected.get("redirectSettings")
    if isinstance(expected_redirect, dict) and any(
        key in expected_redirect
        for key in (
            "enableDocumentRedirectUrl",
            "documentRedirectUrl",
            "documentRedirectType",
        )
    ):
        actual_redirect = actual.get("redirectSettings")
        if not isinstance(actual_redirect, dict):
            actual_redirect = {}
        for key in (
            "enableDocumentRedirectUrl",
            "documentRedirectUrl",
            "documentRedirectType",
        ):
            if key in expected_redirect and actual_redirect.get(key) != expected_redirect.get(key):
                raise RuntimeError(
                    f"{operation} did not persist redirect setting {key!r}. "
                    "The template was re-read and differs from the submitted "
                    "payload. Export it before retrying."
                )
    return actual


@documents.command("get-template")
@click.argument("template_id")
@click.pass_context
def documents_get_template(ctx, template_id):
    """Get a full native contract template (experimental internal API)."""
    _require_experimental(ctx)
    try:
        data = _contract_result(
            _get_internal_client(ctx).get_contract_template(template_id),
            "Get template",
        )
        _output(ctx, data, "Contract Template")
    except Exception as e:
        _handle_error(e)


@documents.command("export-template")
@click.argument("template_id")
@click.option("--output", required=True, type=click.Path(dir_okay=False))
@click.pass_context
def documents_export_template(ctx, template_id, output):
    """Export a lossless native contract template JSON file."""
    _require_experimental(ctx)
    try:
        data = _contract_result(
            _get_internal_client(ctx).get_contract_template(template_id),
            "Export template",
        )
        from cli_anything.gohighlevel.utils.contract_template_builder import (
            prepare_template_export,
        )
        data = prepare_template_export(data)
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        if ctx.obj["json"]:
            click.echo(json.dumps({"templateId": template_id, "output": output}, indent=2))
        else:
            click.echo(f"Contract template exported to {output}")
    except Exception as e:
        _handle_error(e)


@documents.command("get-redirect")
@click.argument("template_id")
@click.pass_context
def documents_get_redirect(ctx, template_id):
    """Read a template's completed-document redirect (experimental)."""
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils.contract_template_builder import (
            completed_redirect_settings,
        )

        data = _contract_result(
            _get_internal_client(ctx).get_contract_template(template_id),
            "Get template redirect",
        )
        _output(ctx, completed_redirect_settings(data), "Completed-Document Redirect")
    except Exception as e:
        _handle_error(e)


@documents.command("set-redirect")
@click.argument("template_id")
@click.option("--url", required=True, help="HTTP(S) URL opened after completion")
@click.option(
    "--target",
    type=click.Choice(["existing-tab", "new-tab"]),
    default="existing-tab",
    show_default=True,
)
@click.pass_context
def documents_set_redirect(ctx, template_id, url, target):
    """Set and verify a template's completed-document redirect (experimental)."""
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils.contract_template_builder import (
            set_completed_redirect,
        )

        client = _get_internal_client(ctx)
        current = _contract_result(
            client.get_contract_template(template_id), "Read template"
        )
        payload = set_completed_redirect(
            current,
            url,
            "existingTab" if target == "existing-tab" else "newTab",
        )
        _contract_result(
            client.update_contract_template(template_id, payload),
            "Set template redirect",
        )
        persisted = _verify_contract_persisted(
            payload,
            client.get_contract_template(template_id),
            "Verify template redirect",
        )
        _output(ctx, persisted, "Contract Template Redirect Updated")
    except Exception as e:
        _handle_error(e)


@documents.command("create-template")
@click.option("--name", required=True, help="Contract template name")
@click.option("--from-json", "json_file", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--public/--no-public",
    "is_public",
    default=False,
    help=(
        "Publish a shareable doc-form link anyone can open and sign. "
        "Create-time only: GoHighLevel ignores isPublicDocument on update, so a "
        "template created without this cannot be made public later."
    ),
)
@click.pass_context
def documents_create_template(ctx, name, json_file, is_public):
    """Create a draft with contractor-first and company signing fields."""
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils.contract_template_builder import (
            apply_template_input,
            ensure_default_signer_fields,
            sanitize_update_payload,
        )

        template_input = None
        if json_file:
            template_input = _contract_json(json_file)
            # The explicit CLI option is authoritative. This also keeps the
            # shell name and the full-content PUT name identical.
            template_input["name"] = name
            # Compact create fields without an explicit party belong to the
            # contractor placeholder. Do this before applying against the
            # freshly created shell, whose recipient list may contain a real
            # preview contact and would otherwise change the assignment.
            if isinstance(template_input.get("fields"), list):
                for field in template_input["fields"]:
                    if isinstance(field, dict) and not field.get("recipient"):
                        field["recipient"] = "assignedContact"
                        field["entityName"] = "contacts"
            # Validate the local schema before creating a remote shell. This
            # avoids leaving an orphan draft when the input is malformed.
            validated = apply_template_input({"pages": []}, template_input, _loc(ctx))
            ensure_default_signer_fields(validated)
        client = _get_internal_client(ctx)
        template_id = _created_template_id(
            client.create_contract_template(name, is_public_document=is_public)
        )
        persisted = _contract_result(client.get_contract_template(template_id), "Read created template")
        payload = apply_template_input(persisted, template_input or {}, _loc(ctx))
        payload = ensure_default_signer_fields(payload)
        payload["locationId"] = _loc(ctx)
        payload = sanitize_update_payload(payload)
        _contract_result(client.update_contract_template(template_id, payload), "Add default signer fields")
        persisted = _verify_contract_persisted(
            payload,
            client.get_contract_template(template_id),
            "Verify created template",
        )
        _output(ctx, persisted, "Contract Template Created")
    except Exception as e:
        _handle_error(e)


@documents.command("update-template")
@click.argument("template_id")
@click.option("--from-json", "json_file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.pass_context
def documents_update_template(ctx, template_id, json_file):
    """Safely update a contract template from compact/native JSON."""
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils.contract_template_builder import apply_template_input

        client = _get_internal_client(ctx)
        current = _contract_result(client.get_contract_template(template_id), "Read template")
        payload = apply_template_input(current, _contract_json(json_file), _loc(ctx))
        _contract_result(client.update_contract_template(template_id, payload), "Update template")
        persisted = _verify_contract_persisted(
            payload,
            client.get_contract_template(template_id),
            "Verify template",
        )
        _output(ctx, persisted, "Contract Template Updated")
    except Exception as e:
        _handle_error(e)


@documents.command("add-field")
@click.argument("template_id")
@click.option("--type", "field_type", required=True,
              type=click.Choice(["name", "text", "signature", "date", "initials", "checkbox"]))
@click.option("--page", default=1, type=click.IntRange(min=1), show_default=True)
@click.option("--label", default=None)
@click.option("--placeholder", default=None)
@click.option("--field-id", default=None)
@click.option("--recipient", default=None, help="Recipient/contact/user/role id")
@click.option("--entity-name", type=click.Choice(["contacts", "users", "role"]), default=None)
@click.option("--required/--optional", default=True, show_default=True)
@click.option("--top", default=0, type=click.IntRange(min=0), show_default=True)
@click.option("--left", default=0, type=click.IntRange(min=0), show_default=True)
@click.option("--width", default=None, type=click.IntRange(min=1))
@click.option("--height", default=None, type=click.IntRange(min=1))
@click.pass_context
def documents_add_field(ctx, template_id, field_type, page, label, placeholder,
                        field_id, recipient, entity_name, required, top, left,
                        width, height):
    """Add a signer field to an existing contract template."""
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils.contract_template_builder import (
            add_field, sanitize_update_payload,
        )

        client = _get_internal_client(ctx)
        current = _contract_result(client.get_contract_template(template_id), "Read template")
        updated = add_field(current, {
            "type": field_type, "page": page, "label": label,
            "placeholder": placeholder, "fieldId": field_id,
            "recipient": recipient, "entityName": entity_name,
            "required": required, "top": top, "left": left,
            "width": width, "height": height,
        })
        updated["locationId"] = _loc(ctx)
        payload = sanitize_update_payload(updated)
        _contract_result(client.update_contract_template(template_id, payload), "Add field")
        persisted = _verify_contract_persisted(
            payload,
            client.get_contract_template(template_id),
            "Verify field",
        )
        _output(ctx, persisted, "Contract Field Added")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# CONVERSATIONS
# ===========================================================================

@cli.group()
@click.pass_context
def conversations(ctx):
    """Manage conversations and messages."""
    pass


@conversations.command("list")
@click.option("--limit", default=20)
@click.option("--status", default=None, type=click.Choice(["all", "read", "unread", "starred"]))
@click.option("--type", "msg_type", default=None,
              type=click.Choice(["Email", "SMS", "WhatsApp", "GMB", "IG", "FB", "Live_Chat", "Custom"]),
              help="Filter by last message type")
@click.pass_context
def conversations_list(ctx, limit, status, msg_type):
    """List conversations. Use --type Email to see email conversations."""
    try:
        # API uses TYPE_EMAIL format for lastMessageType filter
        TYPE_MAP = {
            "Email": "TYPE_EMAIL", "SMS": "TYPE_SMS", "WhatsApp": "TYPE_WHATSAPP",
            "GMB": "TYPE_GMB", "IG": "TYPE_INSTAGRAM", "FB": "TYPE_FACEBOOK",
            "Live_Chat": "TYPE_LIVE_CHAT", "Custom": "TYPE_CUSTOM",
        }
        params = {"locationId": _loc(ctx), "limit": limit}
        if status:
            params["status"] = status
        if msg_type:
            params["lastMessageType"] = TYPE_MAP.get(msg_type, f"TYPE_{msg_type.upper()}")
        data = api.get("/conversations/search", params=params)
        _output(ctx, data, "Conversations")
    except Exception as e:
        _handle_error(e)


@conversations.command("get")
@click.argument("conversation_id")
@click.pass_context
def conversations_get(ctx, conversation_id):
    """Get conversation details."""
    try:
        data = api.get(f"/conversations/{conversation_id}")
        _output(ctx, data, "Conversation Details")
    except Exception as e:
        _handle_error(e)


@conversations.command("messages")
@click.argument("conversation_id")
@click.option("--limit", default=20)
@click.option("--type", "msg_type", default=None,
              type=click.Choice(["Email", "SMS", "WhatsApp", "GMB", "IG", "FB", "Live_Chat", "Custom"]),
              help="Filter messages by type")
@click.pass_context
def conversations_messages(ctx, conversation_id, limit, msg_type):
    """Get messages in a conversation. Use --type Email for email messages only."""
    try:
        TYPE_MAP = {
            "Email": "TYPE_EMAIL", "SMS": "TYPE_SMS", "WhatsApp": "TYPE_WHATSAPP",
            "GMB": "TYPE_GMB", "IG": "TYPE_INSTAGRAM", "FB": "TYPE_FACEBOOK",
            "Live_Chat": "TYPE_LIVE_CHAT", "Custom": "TYPE_CUSTOM",
        }
        params = {"limit": limit}
        if msg_type:
            params["type"] = TYPE_MAP.get(msg_type, f"TYPE_{msg_type.upper()}")
        data = api.get(f"/conversations/{conversation_id}/messages", params=params)
        _output(ctx, data, "Messages")
    except Exception as e:
        _handle_error(e)


@conversations.command("get-email")
@click.argument("email_message_id")
@click.pass_context
def conversations_get_email(ctx, email_message_id):
    """Get full email details (subject, body, headers, attachments).

    Two-step workflow: list conversations --type Email → get message IDs → get-email <id>
    """
    try:
        data = api.get(f"/conversations/messages/email/{email_message_id}")
        _output(ctx, data, "Email Details")
    except Exception as e:
        _handle_error(e)


@conversations.command("send")
@click.argument("conversation_id")
@click.option("--type", "msg_type", default="SMS", type=click.Choice(["SMS", "Email", "WhatsApp", "GMB", "IG", "FB", "Live_Chat"]))
@click.option("--message", required=True, help="Message text")
@click.pass_context
def conversations_send(ctx, conversation_id, msg_type, message):
    """Send a message in a conversation."""
    try:
        body = {
            "type": msg_type,
            "message": message,
            "conversationId": conversation_id,
        }
        data = api.post(f"/conversations/messages", data=body)
        _output(ctx, data, "Message Sent")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# EMAILS
# ===========================================================================

@cli.group()
@click.pass_context
def emails(ctx):
    """Email campaigns and templates."""
    pass


EMAIL_INTERNAL_VERSION = {"Version": "2021-07-28"}


@emails.command("campaigns")
@click.option("--limit", default=20, help="Max campaigns to return")
@click.option("--status", default=None,
              type=click.Choice(["draft", "complete", "scheduled", "paused"]),
              help="Filter by status (client-side)")
@click.pass_context
def emails_campaigns(ctx, limit, status):
    """List broadcast campaigns — the Marketing > Emails > Campaigns screen.

    Distinct from `list-campaigns`, which hits the public /campaigns/ endpoint
    and reports workflow campaigns (usually empty). Requires --experimental.
    """
    _require_experimental(ctx)
    try:
        client = _get_internal_client(ctx)
        data = client.request(
            "GET", f"/emails/schedule?locationId={_loc(ctx)}&limit={limit}",
            extra_headers=EMAIL_INTERNAL_VERSION)
        if isinstance(data, dict) and status and not data.get("_error"):
            data = {**data,
                    "schedules": [s for s in data.get("schedules", [])
                                  if s.get("status") == status]}
        _output(ctx, data, "Broadcast Campaigns")
    except Exception as e:
        _handle_error(e)


@emails.command("templates")
@click.option("--limit", default=20, help="Max templates to return")
@click.pass_context
def emails_templates(ctx, limit):
    """List reusable email templates (Marketing > Emails > Templates)."""
    _require_experimental(ctx)
    try:
        client = _get_internal_client(ctx)
        data = client.request(
            "GET", f"/emails/builder?locationId={_loc(ctx)}&limit={limit}",
            extra_headers=EMAIL_INTERNAL_VERSION)
        _output(ctx, data, "Email Templates")
    except Exception as e:
        _handle_error(e)


@cli.group()
@click.pass_context
def smartlists(ctx):
    """Contact smart lists (saved contact filters)."""
    pass


DEFAULT_SMARTLIST_COLUMNS = [
    "name", "phone", "email", "companyName", "dateAdded", "lastActivity", "tags",
]


VALUELESS_OPERATORS = {"exists", "not_exists", "is_empty", "is_not_empty"}


def _parse_filter(expr: str) -> dict:
    """Parse `field:operator[:value]` into one GHL filter leaf.

    Examples:
        email:exists
        tags:not_eq:blacklist,unsubbed        -> list value + minimumMatch
        valid_email:eq:true                   -> real boolean
        dnd_settings.Email.status:not_eq:true -> dotted field paths are fine
    """
    parts = expr.split(":")
    if len(parts) < 2:
        raise click.BadParameter(
            f"filter '{expr}' must be field:operator[:value] (e.g. email:exists)")
    field, operator = parts[0], parts[1]
    leaf: dict = {"operator": operator, "field": field}
    if operator in VALUELESS_OPERATORS:
        if len(parts) > 2:
            raise click.BadParameter(f"operator '{operator}' takes no value")
        return leaf
    if len(parts) < 3:
        raise click.BadParameter(f"operator '{operator}' needs a value: {expr}")
    raw = ":".join(parts[2:])          # values may legitimately contain ':'
    if "," in raw:
        leaf["value"] = [v.strip() for v in raw.split(",") if v.strip()]
        leaf["options"] = {"minimumMatch": 1}
    elif raw.lower() in ("true", "false"):
        leaf["value"] = raw.lower() == "true"
    else:
        leaf["value"] = raw
    return leaf


@smartlists.command("create")
@click.option("--name", required=True, help="Smart list name")
@click.option("--filter", "filter_exprs", multiple=True,
              help="field:operator[:value], repeatable, ANDed together. "
                   "e.g. --filter email:exists --filter tags:not_eq:blacklist,unsubbed")
@click.option("--from-json", type=click.Path(exists=True), default=None,
              help="JSON file with full filterSpecs (see `smartlists get` output). "
                   "Takes precedence over --filter.")
@click.pass_context
def smartlists_create(ctx, name, filter_exprs, from_json):
    """Create a smart list.

    With neither --filter nor --from-json the list matches every contact, which
    is what the GHL UI does for a brand-new list — useful as a container, but it
    is not really a *smart* list. Pass filters to make it one.
    """
    _require_experimental(ctx)
    try:
        filter_specs = {"filters": [{"group": "OR", "filters": []}], "page": 1, "limit": 20}
        sort_specs = []
        if from_json:
            with open(from_json) as fh:
                spec = json.load(fh)
            filter_specs = spec.get("filterSpecs", filter_specs)
            sort_specs = spec.get("sortSpecs", [])
        elif filter_exprs:
            # GHL nests conditions as OR-group -> AND-group -> leaves.
            leaves = [_parse_filter(e) for e in filter_exprs]
            filter_specs = {
                "filters": [{"group": "OR",
                             "filters": [{"group": "AND", "filters": leaves}]}],
                "page": 1,
                "limit": 20,
            }
        body = {
            "columns": [{"key": c, "value": c, "order": i}
                        for i, c in enumerate(DEFAULT_SMARTLIST_COLUMNS)],
            "filterSpecs": filter_specs,
            "listName": name,
            "sortSpecs": sort_specs,
            "locationId": _loc(ctx),
        }
        client = _get_internal_client(ctx)
        data = client.request("POST", "/contacts/smartlist", body,
                              extra_headers=EMAIL_INTERNAL_VERSION)
        _output(ctx, data, f"Created smart list '{name}'")
    except Exception as e:
        _handle_error(e)


@smartlists.command("delete")
@click.argument("smart_list_id")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def smartlists_delete(ctx, smart_list_id, yes):
    """Delete a smart list by ID. Deletes the LIST only, never its contacts."""
    _require_experimental(ctx)
    if not yes:
        click.confirm(
            f"Delete smart list {smart_list_id} from location {_loc(ctx)}?", abort=True)
    try:
        # Deletion is POST /smartlist/delete on api.leadconnectorhq.com with a
        # snake_case body — NOT DELETE /contacts/smartlist/{id} on the usual
        # backend host, which 404s.
        client = _get_internal_client(ctx)
        data = client.request("POST", "https://api.leadconnectorhq.com/smartlist/delete",
                              {"smartlist_id": smart_list_id},
                              extra_headers=EMAIL_INTERNAL_VERSION)
        _output(ctx, data if data else {"status": "deleted", "id": smart_list_id},
                "Deleted smart list")
    except Exception as e:
        _handle_error(e)


@smartlists.command("get")
@click.argument("smart_list_id")
@click.pass_context
def smartlists_get(ctx, smart_list_id):
    """Get a smart list by ID, including its filterSpecs.

    The ID is the last path segment of the GHL smart-list URL:
    .../contacts/smart_list/<SMART_LIST_ID>
    """
    _require_experimental(ctx)
    try:
        client = _get_internal_client(ctx)
        data = client.request(
            "GET", f"/contacts/smartlist/{smart_list_id}?transform=true",
            extra_headers=EMAIL_INTERNAL_VERSION)
        _output(ctx, data, f"Smart List {smart_list_id}")
    except Exception as e:
        _handle_error(e)


@smartlists.command("list")
@click.pass_context
def smartlists_list(ctx):
    """List every smart list in the location.

    Uses /contacts/smartlist/search — the collection endpoint the UI calls on
    page load. Returns id + listName so `smartlists get` and
    `emails create-campaign --smart-list` have something to reference.
    """
    _require_experimental(ctx)
    try:
        client = _get_internal_client(ctx)
        user_id = client.token_mgr.get_user_id() or ""
        data = client.request(
            "GET",
            f"/contacts/smartlist/search?locationId={_loc(ctx)}&userId={user_id}"
            "&globals=true&transform=true",
            extra_headers=EMAIL_INTERNAL_VERSION)
        _output(ctx, data, "Smart Lists")
    except Exception as e:
        _handle_error(e)


# --- Campaign authoring -------------------------------------------------
#
# A GHL broadcast campaign is TWO records, not one:
#   1. a *template* (/emails/builder) that owns the HTML body, and
#   2. a *campaign* (/emails/schedule) that points at the template.
# The HTML itself lands in Firebase Storage; POST /emails/builder/data returns
# the resulting previewUrl.
#
# SENDING IS A SEPARATE ENDPOINT: POST /emails/schedule/start. Nothing in this
# CLI calls it. Everything below leaves the campaign in `draft`, so a mistake
# here cannot dispatch mail.

def _split_from(from_email: str) -> None:
    if "@" not in from_email:
        raise click.BadParameter(f"--from-email must be an address, got {from_email!r}")


def _recipient_block(ctx, client, smart_list_id, tags, assigned_to):
    """Build the `filters` object that binds recipients to a campaign.

    Grammar taken from the UI's own payload builder: a smart list carries BOTH
    its resolved filter leaves and its id; tags are expressed as a single leaf;
    an empty leaf array means "all contacts".
    """
    if smart_list_id:
        sl = client.request("GET", f"/contacts/smartlist/{smart_list_id}?transform=true",
                            extra_headers=EMAIL_INTERNAL_VERSION)
        if isinstance(sl, dict) and sl.get("_error"):
            raise click.ClickException(
                f"Could not read smart list {smart_list_id}: {sl.get('message')}")
        spec = ((sl or {}).get("smartList") or {}).get("filterSpecs") or {}
        leaves = spec.get("filters", [])
        if not leaves:
            click.echo(
                f"warning: smart list {smart_list_id} has no filters, so this "
                "campaign would target every contact.", err=True)
        return {"filters": leaves, "id": smart_list_id, "assigned_to": assigned_to}
    if tags:
        return {"filters": [{"field": "tags", "operator": "eq", "value": list(tags)}],
                "assigned_to": assigned_to}
    return {"filters": [], "assigned_to": assigned_to}


@emails.command("create-campaign")
@click.option("--name", required=True, help="Campaign name (internal)")
@click.option("--subject", required=True, help="Subject line")
@click.option("--from-name", required=True, help="Sender display name")
@click.option("--from-email", required=True, help="Sender address")
@click.option("--html-file", type=click.Path(exists=True), required=True,
              help="File containing the email body HTML")
@click.option("--preview-text", default="", help="Inbox preview text")
@click.option("--reply-to", default="", help="Reply-To address (defaults to from)")
@click.option("--smart-list", "smart_list_id", default=None,
              help="Bind recipients to this smart list ID (see `smartlists list`)")
@click.option("--tag", "tags", multiple=True,
              help="Bind recipients by tag; repeatable. Ignored if --smart-list is set.")
@click.option("--ab-subject", "ab_subjects", multiple=True,
              help="Additional subject line to test against --subject; repeatable. "
                   "A/B is the default mode — at least one is required unless "
                   "--no-ab-test is passed.")
@click.option("--ab-test/--no-ab-test", "ab_test", default=True,
              help="Run as a subject-line A/B test. ON by default; --no-ab-test "
                   "sends one subject to everyone.")
@click.option("--ab-test-size", default=50, type=click.IntRange(1, 100),
              help="Percent of the list used for the test phase (default 50)")
@click.option("--ab-test-hours", default=4, type=click.FloatRange(0.25, 168),
              help="Hours to run the test before picking a winner (default 4)")
@click.option("--ab-winning-criteria", default="openRate",
              type=click.Choice(["openRate", "clickRate"]),
              help="How the winner is chosen (default openRate)")
@click.option("--utm/--no-utm", "utm_tracking", default=True,
              help="Append the location's default UTM parameters. ON by default.")
@click.option("--click-tracking/--no-click-tracking", default=False,
              help="Rewrite links for click tracking. OFF by default, matching "
                   "how these campaigns are normally sent.")
@click.option("--first-name-fallback", default="there",
              help="Fallback for a blank/missing first name (default 'there')")
@click.option("--allow-no-personalization", is_flag=True,
              help="Permit copy with no first-name merge field at all")
@click.option("--ghost-ink/--no-ghost-ink", default=None,
              hidden=not GHOST_INK_AVAILABLE,
              help="Inject hidden 'ham' text into the body. Auto-detected based on module availability.")
@click.option("--ghost-ink-topic", default=None,
              hidden=not GHOST_INK_AVAILABLE,
              help="Bias ghost-ink passage selection to a topic")
@click.option("--ghost-ink-seed", default=None,
              hidden=not GHOST_INK_AVAILABLE,
              help="Deterministic passage choice for a given topic")
@click.option("--timezone", "time_zone", default="America/New_York",
              help="Campaign timezone")
@click.pass_context
def emails_create_campaign(ctx, name, subject, from_name, from_email, html_file,
                           preview_text, reply_to, smart_list_id, tags, ab_subjects,
                           ab_test, ab_test_size, ab_test_hours, ab_winning_criteria,
                           utm_tracking, click_tracking, first_name_fallback,
                           allow_no_personalization, ghost_ink, ghost_ink_topic,
                           ghost_ink_seed, time_zone):
    """Create a broadcast campaign as a DRAFT. Never sends.

    Builds the template, uploads the HTML, creates the campaign, and saves the
    subject/sender/recipient settings. The result sits in Marketing > Emails as
    a draft for a human to review and send.

    Defaults reflect house style: subject-line A/B on, UTM tracking on, and every
    first-name merge field given a fallback.
    """
    _require_experimental(ctx)
    _split_from(from_email)
    try:
        from cli_anything.gohighlevel.utils import merge_fields as mf

        # Determine if ghost_ink should be used. Default to True if available, False otherwise.
        ghost_ink_available = False
        apply_ghost_ink_with_passage = None
        assert_ghost_ink = None

        try:
            from cli_anything.gohighlevel.utils.ghost_ink import (
                apply_ghost_ink_with_passage,
                assert_ghost_ink as assert_ghost_ink_fn,
            )
            ghost_ink_available = True
            assert_ghost_ink = assert_ghost_ink_fn
        except ImportError:
            ghost_ink_available = False

        # Resolve the actual ghost_ink value
        effective_ghost_ink = ghost_ink if ghost_ink is not None else ghost_ink_available

        # If user explicitly requested ghost_ink but it's not available, error out
        if ghost_ink is True and not ghost_ink_available:
            raise click.UsageError(
                "ghost ink module is not installed in this build. "
                "Pass --no-ghost-ink to proceed without it, or --ghost-ink to fail if unavailable.")

        loc = _loc(ctx)
        client = _get_internal_client(ctx)
        user_id = client.token_mgr.get_user_id() or ""

        with open(html_file, encoding="utf-8") as fh:
            html = fh.read()

        # --- A/B is the default; a "test" with one variation is not a test ---
        if ab_test and not ab_subjects:
            raise click.UsageError(
                "A/B testing is on by default, so at least one --ab-subject is "
                "required to have something to test against --subject.\n"
                "Add:  --ab-subject \"<alternate subject line>\"\n"
                "Or send a single subject to everyone with --no-ab-test.")
        if ab_subjects and not ab_test:
            raise click.UsageError(
                "--ab-subject was given but --no-ab-test disables the test. "
                "Drop one of the two.")

        # --- personalization: a bare first-name token renders "Hi ," ---
        all_subjects = [subject, *ab_subjects]
        personalized = any(mf.has_first_name(t)
                           for t in (*all_subjects, preview_text, html))
        if not personalized and not allow_no_personalization:
            raise click.UsageError(
                "No first-name merge field found in the subject, preview text or "
                "body. Add {{contact.first_name}} where you want it (the fallback "
                "is added automatically), or pass --allow-no-personalization.")

        bare = sum(mf.count_bare_first_name(t)
                   for t in (*all_subjects, preview_text, html))
        subject = mf.ensure_fallbacks(subject, first_name_fallback)
        ab_subjects = tuple(mf.ensure_fallbacks(s, first_name_fallback)
                            for s in ab_subjects)
        preview_text = mf.ensure_fallbacks(preview_text, first_name_fallback)
        html = mf.ensure_fallbacks(html, first_name_fallback)

        passage = None
        if effective_ghost_ink:
            html, passage = apply_ghost_ink_with_passage(
                html, ghost_ink_topic, ghost_ink_seed)
            # Lint before the HTML leaves the process. The shared contract
            # requires sentinel, frozen-CSS, pool-membership, visible-body and
            # anchor checks on every send path, not just the builder ones.
            assert_ghost_ink(html)

        # 1. template shell
        tpl = client.request("POST", "/emails/builder", {
            "locationId": loc, "type": "html", "updatedBy": user_id,
            "title": name, "isPlainText": False, "language": "en",
        }, extra_headers=EMAIL_INTERNAL_VERSION)
        if not isinstance(tpl, dict) or tpl.get("_error"):
            _output(ctx, tpl, "Template create failed")
            return
        template_id = tpl.get("redirect") or tpl.get("id") or tpl.get("_id")

        # 2. body HTML -> Firebase Storage
        saved = client.request("POST", "/emails/builder/data", {
            "locationId": loc, "templateId": template_id, "html": html,
            "editorType": "html", "previewText": preview_text, "updatedBy": user_id,
        }, extra_headers=EMAIL_INTERNAL_VERSION)
        if not isinstance(saved, dict) or saved.get("_error"):
            _output(ctx, saved, "HTML upload failed")
            return

        # 3. campaign record pointing at the template
        camp = client.request("POST", "/emails/schedule", {
            "locationId": loc, "parentId": "", "byUserName": from_name,
            "byUserId": user_id, "timeZone": time_zone,
            "templateId": str(template_id), "templateType": "html",
            "isPlainText": False, "name": name, "language": "en",
        }, extra_headers=EMAIL_INTERNAL_VERSION)
        if not isinstance(camp, dict) or camp.get("_error"):
            _output(ctx, camp, "Campaign create failed")
            return
        campaign_id = camp.get("id") or camp.get("_id")

        # The create response carries only {id}; documentId — which identifies
        # the campaign's rendered body — appears on the next read. A/B subject
        # variations share that one body, so fetch it rather than reading it off
        # the create response, where it is always absent (that wrote null).
        document_id = camp.get("documentId")
        if ab_test and not document_id:
            fetched = client.request("GET", f"/emails/schedule/{loc}/{campaign_id}",
                                     extra_headers=EMAIL_INTERNAL_VERSION)
            if isinstance(fetched, dict) and not fetched.get("_error"):
                document_id = fetched.get("documentId")
            if not document_id:
                raise click.ClickException(
                    "Campaign was created but has no documentId, so the A/B "
                    "variations would have no body. Campaign left in place for "
                    f"inspection: {campaign_id}")

        # 4. subject / sender / recipients. isSave=True keeps it a draft; the
        #    same payload with isSave=False is what the Send button posts to
        #    /emails/schedule/start, which this CLI never calls.
        params = {
            "locationId": loc, "byUserName": from_name, "byUserId": user_id,
            "timeZone": time_zone, "type": "abtest" if ab_test else "normal",
            "previewText": preview_text, "isSave": True,
            "hasUtmTracking": utm_tracking,
            "hasTrackingLinks": click_tracking,
            "filters": _recipient_block(ctx, client, smart_list_id, tags, user_id),
            "bulkReqInfo": {
                "freezeList": False,
                "description": subject,
                "opSource": "email-builder",
                "opSpecs": {
                    "opType": "bulk-email",
                    "subject": subject,
                    "from": f"{from_name} <{from_email}>",
                    "assignedTo": user_id,
                    "replyToAddress": reply_to or from_email,
                },
            },
        }
        if ab_test:
            variations = [{"subject": s, "documentId": document_id}
                          for s in (subject, *ab_subjects)]
            # Field names and value spellings taken from a real UI-created A/B
            # campaign, not inferred: testType is "emailSubject" (camelCase),
            # testDuration is SECONDS, testSize is a percent.
            params["abTestInfo"] = {
                "variations": variations,
                "variationCount": len(variations),
                "testType": "emailSubject",
                "testSize": ab_test_size,
                "testDuration": int(ab_test_hours * 3600),
                "winningCriteria": ab_winning_criteria,
                "winningVariationIndex": -1,
            }

        meta = client.request("PATCH", f"/emails/schedule/{loc}/{campaign_id}", params,
                              extra_headers=EMAIL_INTERNAL_VERSION)
        if isinstance(meta, dict) and meta.get("_error"):
            _output(ctx, meta, "Campaign settings failed")
            return

        result = {
            "campaignId": campaign_id,
            "templateId": template_id,
            "status": "draft",
            "name": name,
            "subject": subject,
            "abTest": {
                "variations": 1 + len(ab_subjects),
                "abSubjects": list(ab_subjects),
                "testSize": f"{ab_test_size}%",
                "testDuration": f"{ab_test_hours}h",
                "winningCriteria": ab_winning_criteria,
            } if ab_test else False,
            "utmTracking": utm_tracking,
            "clickTracking": click_tracking,
            "firstNameFallbacksAdded": bare,
            "recipients": ("smartList:" + smart_list_id) if smart_list_id
                          else ("tags:" + ",".join(tags) if tags else "all"),
            # Omitted entirely in builds without the module, so a receipt never
            # reports on a feature the build does not have. Unchanged where it
            # is installed.
            **({"ghostInk": passage["id"] if passage else False}
               if GHOST_INK_AVAILABLE else {}),
            "previewUrl": saved.get("previewUrl"),
            # Corrected 2026-09-15 against a link Jay opened himself. The old form,
            # /v2/location/{loc}/marketing/emails/schedule/{id}, was invented here and
            # matched no GHL route: there is no /v2 segment, campaigns live under
            # /emails/campaigns/create/{id}, and the draft opens on its /schedule step.
            "editUrl": (f"https://{_app_domain()}/location/{loc}"
                        f"/emails/campaigns/create/{campaign_id}/schedule"),
        }
        _output(ctx, result, f"Created DRAFT campaign '{name}' (not sent)")
    except click.ClickException:
        raise
    except Exception as e:
        _handle_error(e)


@emails.command("get-campaign")
@click.argument("campaign_id")
@click.pass_context
def emails_get_campaign(ctx, campaign_id):
    """Fetch one campaign, including its recipient filters and sender settings."""
    _require_experimental(ctx)
    try:
        client = _get_internal_client(ctx)
        data = client.request("GET", f"/emails/schedule/{_loc(ctx)}/{campaign_id}",
                              extra_headers=EMAIL_INTERNAL_VERSION)
        _output(ctx, data, f"Campaign {campaign_id}")
    except Exception as e:
        _handle_error(e)


@emails.command("delete-campaign")
@click.argument("campaign_id")
@click.option("--template-id", default=None,
              help="Also delete the campaign's template (from create-campaign output)")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def emails_delete_campaign(ctx, campaign_id, template_id, yes):
    """Delete a campaign. Sent campaigns keep their delivery history in GHL."""
    _require_experimental(ctx)
    if not yes:
        click.confirm(f"Delete campaign {campaign_id} from location {_loc(ctx)}?",
                      abort=True)
    try:
        loc = _loc(ctx)
        client = _get_internal_client(ctx)
        data = client.request("DELETE", f"/emails/schedule/{loc}/{campaign_id}",
                              extra_headers=EMAIL_INTERNAL_VERSION)
        out = {"campaign": data if data else {"status": "deleted", "id": campaign_id}}
        if template_id:
            out["template"] = client.request(
                "DELETE", f"/emails/builder/{loc}/{template_id}",
                extra_headers=EMAIL_INTERNAL_VERSION)
        _output(ctx, out, "Deleted campaign")
    except Exception as e:
        _handle_error(e)


@emails.command("list-campaigns")
@click.option("--status", default=None, help="Filter by status")
@click.pass_context
def emails_list_campaigns(ctx, status):
    """List email campaigns. Note: Uses the campaigns API."""
    try:
        params = {"locationId": _loc(ctx)}
        if status:
            params["status"] = status
        data = api.get("/campaigns/", params=params)
        _output(ctx, data, "Email Campaigns")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# PAYMENTS
# ===========================================================================

@cli.group()
@click.pass_context
def payments(ctx):
    """Payments, subscriptions, invoices, transactions, and orders."""
    pass


@payments.command("transactions")
@click.option("--limit", default=20)
@click.option("--offset", default=0)
@click.option("--contact-id", default=None)
@click.pass_context
def payments_transactions(ctx, limit, offset, contact_id):
    """List transactions."""
    try:
        params = {"altId": _loc(ctx), "altType": "location", "limit": limit, "offset": offset}
        if contact_id:
            params["contactId"] = contact_id
        data = api.get("/payments/transactions", params=params)
        _output(ctx, data, "Transactions")
    except Exception as e:
        _handle_error(e)


@payments.command("subscriptions")
@click.option("--limit", default=20)
@click.option("--offset", default=0)
@click.option("--contact-id", default=None, help="Filter by contact ID")
@click.option(
    "--status",
    default=None,
    help="Pass a status filter to GHL (not listed in the current public parameter table)",
)
@click.pass_context
def payments_subscriptions(ctx, limit, offset, contact_id, status):
    """List recurring payment subscriptions for the current location."""
    try:
        params = {
            "altId": _loc(ctx),
            "altType": "location",
            "limit": limit,
            "offset": offset,
        }
        if contact_id:
            params["contactId"] = contact_id
        if status:
            params["status"] = status
        data = api.get("/payments/subscriptions", params=params)
        _output(ctx, data, "Subscriptions")
    except Exception as e:
        _handle_error(e)


@payments.command("subscription")
@click.argument("subscription_id")
@click.pass_context
def payments_subscription(ctx, subscription_id):
    """Get one recurring payment subscription by ID."""
    try:
        params = {"altId": _loc(ctx), "altType": "location"}
        data = api.get(f"/payments/subscriptions/{subscription_id}", params=params)
        _output(ctx, data, "Subscription")
    except Exception as e:
        _handle_error(e)


@payments.command("subscription-discount")
@click.argument("subscription_id")
@click.option("--expect-contact-id", default=None, help="Require this exact contact ID")
@click.option("--expect-coupon-code", default=None, help="Require this exact applied coupon code")
@click.pass_context
def payments_subscription_discount(ctx, subscription_id, expect_contact_id, expect_coupon_code):
    """Inspect one subscription's discount evidence (GET only, no edits).

    Missing schedule or coupon fields are unknown, not proof of a zero charge
    or of an expired discount. Use the real GHL UI to verify billing dates.
    """
    if not subscription_id or any(
        not (char.isascii() and (char.isalnum() or char in "_-"))
        for char in subscription_id
    ):
        raise click.UsageError("Provide one literal subscription ID.")
    try:
        location_id = _loc(ctx)
        data = api.get(
            f"/payments/subscriptions/{subscription_id}",
            params={"altId": location_id, "altType": "location"},
        )
        if not isinstance(data, dict) or data.get("_id") != subscription_id:
            raise ValueError("Subscription response identity is missing or mismatched.")
        if data.get("altId") != location_id or data.get("altType") != "location":
            raise ValueError("Subscription response location is missing or mismatched.")
        if expect_contact_id is not None and data.get("contactId") != expect_contact_id:
            raise ValueError("Subscription contact ID is missing or mismatched.")
        coupon = data.get("coupon")
        coupon_code = coupon.get("code") if isinstance(coupon, dict) else None
        if expect_coupon_code is not None and coupon_code != expect_coupon_code:
            raise ValueError("Applied coupon code is missing or mismatched.")
        _output(ctx, {
            "readOnly": True,
            "mutationSupported": False,
            "subscription": data,
            "billingInterpretation": "No next charge date or amount is inferred. Verify in the GHL UI.",
            "browserReview": [
                "Verify the target, product, price, applied discount and billing schedule in real Chrome.",
                "Save before and after subscription screenshots, including discount duration and next charge.",
                "Only change duration or replace the applied coupon when explicitly authorized.",
                "Stop on immediate charge, proration, invoice, or remove-only controls.",
                "Do not edit the shared coupon, price, product, subscription status, or SaaS location.",
            ],
        }, "Subscription discount evidence")
    except Exception as e:
        _handle_error(e)


@payments.command("orders")
@click.option("--limit", default=20)
@click.option("--offset", default=0)
@click.pass_context
def payments_orders(ctx, limit, offset):
    """List orders."""
    try:
        params = {"altId": _loc(ctx), "altType": "location", "limit": limit, "offset": offset}
        data = api.get("/payments/orders", params=params)
        _output(ctx, data, "Orders")
    except Exception as e:
        _handle_error(e)


@payments.command("invoices")
@click.option("--limit", default=20)
@click.option("--offset", default=0)
@click.option("--status", default=None, type=click.Choice(["draft", "sent", "paid", "void"]))
@click.option("--contact-id", default=None)
@click.pass_context
def payments_invoices(ctx, limit, offset, status, contact_id):
    """List invoices."""
    try:
        params = {"altId": _loc(ctx), "altType": "location", "limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if contact_id:
            params["contactId"] = contact_id
        data = api.get("/invoices/", params=params)
        _output(ctx, data, "Invoices")
    except Exception as e:
        _handle_error(e)


@payments.command("create-invoice")
@click.option("--contact-id", required=True, help="Contact ID")
@click.option("--name", required=True, help="Invoice name/title")
@click.option("--amount", required=True, type=float, help="Total amount in cents")
@click.option("--due-date", required=True, help="Due date (YYYY-MM-DD)")
@click.pass_context
def payments_create_invoice(ctx, contact_id, name, amount, due_date):
    """Create a new invoice."""
    try:
        body = {
            "altId": _loc(ctx),
            "altType": "location",
            "contactId": contact_id,
            "name": name,
            "total": amount,
            "dueDate": due_date,
        }
        data = api.post("/invoices/", data=body)
        _output(ctx, data, "Invoice Created")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# FORMS
# ===========================================================================

@cli.group()
@click.pass_context
def forms(ctx):
    """Forms and form submissions."""
    pass


@forms.command("list")
@click.option("--limit", default=20)
@click.option("--offset", "skip", default=0)
@click.option("--type", "form_type", default=None, help="Form type filter")
@click.pass_context
def forms_list(ctx, limit, skip, form_type):
    """List forms."""
    try:
        params = {"locationId": _loc(ctx), "limit": limit, "skip": skip}
        if form_type:
            params["type"] = form_type
        data = api.get("/forms/", params=params)
        _output(ctx, data, "Forms")
    except Exception as e:
        _handle_error(e)


@forms.command("submissions")
@click.argument("form_id")
@click.option("--limit", default=20)
@click.option("--page", default=1)
@click.pass_context
def forms_submissions(ctx, form_id, limit, page):
    """Get form submissions."""
    try:
        params = {"locationId": _loc(ctx), "limit": limit, "page": page}
        data = api.get(f"/forms/submissions", params={"formId": form_id, **params})
        _output(ctx, data, f"Submissions for form {form_id}")
    except Exception as e:
        _handle_error(e)


@forms.command("get")
@click.argument("form_id")
@click.pass_context
def forms_get(ctx, form_id):
    """Get a full stored form, including formData (experimental internal API)."""
    _require_experimental(ctx)
    try:
        form = _get_internal_client(ctx).get_form(form_id)
        if not isinstance(form, dict):
            raise RuntimeError("Get form returned no form object.")
        if form.get("_error"):
            raise RuntimeError(f"Get form failed: {form.get('message', 'unknown error')}")
        _output(ctx, form, "Form")
    except Exception as e:
        _handle_error(e)


@forms.command("create")
@click.option("--from-json", "json_file", required=True, type=click.Path(exists=True),
              help="Form spec JSON (see utils/form_survey_builder.py for the shape)")
@click.pass_context
def forms_create(ctx, json_file):
    """Create a form with full content — sections, columns, fields (experimental).

    The spec JSON needs a "name" and a "fields" list. Each field is a compact
    dict: {"type": "text", "tag": "first_name", "label": "First Name", "width": 50}.
    Use {"kind": "header", "text": "..."} for section dividers and
    {"kind": "html", "html": "..."} for content blocks. "width" (25/33/50/100)
    controls columns. Built and verified end-to-end via the internal API.
    """
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils import form_survey_builder as fsb

        with open(json_file) as f:
            spec = json.load(f)
        payload = fsb.build_form_payload(spec)
        client = _get_internal_client(ctx)
        form = client.create_form(payload["name"], payload["formData"])
        if not form or (isinstance(form, dict) and form.get("_error")):
            click.echo(f"Error creating form: {form}", err=True)
            sys.exit(1)
        summary = fsb.count_summary(payload, is_survey=False)
        if ctx.obj["json"]:
            click.echo(json.dumps(form, indent=2, default=str))
        else:
            click.echo(f"Created form '{payload['name']}' ({form.get('_id')}) — {summary}")
    except Exception as e:
        _handle_error(e)


@forms.command("delete")
@click.argument("form_id")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def forms_delete(ctx, form_id, yes):
    """Delete a form (experimental, internal API)."""
    _require_experimental(ctx)
    try:
        if not yes:
            click.confirm(
                f"Delete form {form_id}? This permanently removes the native GHL form. Continue?",
                abort=True,
            )
        client = _get_internal_client(ctx)
        ok = client.delete_form(form_id)
        click.echo("Deleted." if ok else "Delete failed.", err=not ok)
        if not ok:
            sys.exit(1)
    except click.Abort:
        click.echo("Aborted.", err=True)
        sys.exit(1)
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# SURVEYS (experimental — internal API)
# ===========================================================================

@cli.group()
@click.pass_context
def surveys(ctx):
    """Surveys — list, create, delete. Create/delete require --experimental."""
    pass


@surveys.command("list")
@click.option("--limit", default=20)
@click.pass_context
def surveys_list(ctx, limit):
    """List surveys (experimental, internal API)."""
    _require_experimental(ctx)
    try:
        client = _get_internal_client(ctx)
        data = client.request("GET", f"/surveys/?locationId={_loc(ctx)}&limit={limit}",
                              extra_headers={"Version": "2021-07-28"})
        _output(ctx, data, "Surveys")
    except Exception as e:
        _handle_error(e)


@surveys.command("create")
@click.option("--from-json", "json_file", required=True, type=click.Path(exists=True),
              help="Survey spec JSON (see utils/form_survey_builder.py for the shape)")
@click.pass_context
def surveys_create(ctx, json_file):
    """Create a multi-slide survey with fields and styled buttons (experimental).

    The spec JSON needs a "name" and a "slides" list; each slide has a "name",
    optional "button" (label string), and a "fields" list using the same compact
    field shape as forms. Two-step under the hood (create shell, then push the
    FULL formData envelope) because the survey service silently drops incomplete
    payloads.
    """
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils import form_survey_builder as fsb

        with open(json_file) as f:
            spec = json.load(f)
        payload = fsb.build_survey_payload(spec)
        client = _get_internal_client(ctx)

        shell = client.create_survey(payload["name"])
        if not shell or (isinstance(shell, dict) and shell.get("_error")):
            click.echo(f"Error creating survey shell: {shell}", err=True)
            sys.exit(1)
        survey_id = shell.get("_id")
        client.update_survey(survey_id, payload["name"], payload["formData"])
        time.sleep(0.5)  # let the write settle before verifying

        # Verify content actually persisted (survey service can silently no-op)
        check = client.get_survey(survey_id)
        slides = (check or {}).get("formData", {}).get("slides", []) if isinstance(check, dict) else []
        if not slides:
            click.echo(
                f"Warning: survey {survey_id} was created but its content did not persist. "
                "The payload likely miss a required field key.", err=True)
            sys.exit(1)
        summary = fsb.count_summary(payload, is_survey=True)
        if ctx.obj["json"]:
            click.echo(json.dumps(check, indent=2, default=str))
        else:
            click.echo(f"Created survey '{payload['name']}' ({survey_id}) — {summary}")
    except Exception as e:
        _handle_error(e)


@surveys.command("delete")
@click.argument("survey_id")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def surveys_delete(ctx, survey_id, yes):
    """Delete a survey (experimental, internal API)."""
    _require_experimental(ctx)
    try:
        if not yes:
            click.confirm(
                f"Delete survey {survey_id}? This permanently removes the native GHL survey. Continue?",
                abort=True,
            )
        client = _get_internal_client(ctx)
        ok = client.delete_survey(survey_id)
        click.echo("Deleted." if ok else "Delete failed.", err=not ok)
        if not ok:
            sys.exit(1)
    except click.Abort:
        click.echo("Aborted.", err=True)
        sys.exit(1)
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# FUNNELS (experimental — internal builder API)
# ===========================================================================

@cli.group()
@click.pass_context
def funnels(ctx):
    """Funnels and builder-v2 landing pages (experimental internal API)."""
    pass


@funnels.command("checkout-assets")
@click.option("--form-id", required=True)
@click.option("--annual-row-id", required=True)
@click.option("--monthly-row-id", required=True)
@click.option("--checkout-url", required=True)
@click.option("--output-dir", required=True, type=click.Path(file_okay=False))
@click.option("--coupon-code", default=None)
@click.option("--email", default=None)
@click.pass_context
def funnels_checkout_assets(ctx, **kwargs):
    """Generate local CSS, footer JS and iframe HTML. No provider writes."""
    from cli_anything.gohighlevel.utils.checkout_probe import checkout_assets
    try:
        paths = checkout_assets(**kwargs)
    except (ValueError, OSError):
        raise click.ClickException("Invalid inputs or output directory already exists/is unwritable. No remote change made.") from None
    click.echo(json.dumps(paths, indent=2))


@funnels.command("serve-probe")
@click.argument("html_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--port", default=8765, type=click.IntRange(1, 65535), show_default=True)
def funnels_serve_probe(html_file, port):
    """Serve only HTML_FILE at /embed.html on loopback. Stop with Ctrl+C."""
    from cli_anything.gohighlevel.utils.checkout_probe import probe_server
    try:
        with probe_server(html_file, port) as server:
            click.echo(f"Probe: http://localhost:{port}/embed.html — Ctrl+C to stop", err=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                click.echo("Probe server stopped.", err=True)
    except (ValueError, OSError):
        raise click.ClickException("Unable to read HTML or bind loopback port; no server started.") from None


@funnels.command("templates")
@click.pass_context
def funnels_templates(ctx):
    """List the built-in, design-system landing-page templates."""
    from cli_anything.gohighlevel.utils import landing_page_design as design
    rows = [{"template": key, "description": value}
            for key, value in design.TEMPLATE_INFO.items()]
    if ctx.obj["json"]:
        click.echo(json.dumps({"templates": rows, "themes": design.THEMES}, indent=2))
    else:
        _output(ctx, rows, "Landing-page templates")
        click.echo("\nThemes: " + ", ".join(design.THEMES))


@funnels.command("init-template")
@click.argument("template", type=click.Choice([
    "vsl", "vsl-application", "sales-letter", "roadmap", "application",
    "membership", "pricing", "optin", "calendar", "intake",
]))
@click.option("--theme", default="otter",
              type=click.Choice(["otter", "editorial", "modern", "warm"]), show_default=True)
@click.option("--output", required=True, type=click.Path(dir_okay=False))
def funnels_init_template(template, theme, output):
    """Create an editable compact JSON spec from a polished template."""
    from pathlib import Path
    from cli_anything.gohighlevel.utils import landing_page_design as design
    path = Path(output)
    if path.exists():
        raise click.ClickException(f"refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(design.template_spec(template, theme), indent=2) + "\n",
                    encoding="utf-8")
    click.echo(f"Created {template} template ({theme}) at {path}")


@funnels.command("lint")
@click.argument("json_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--strict", is_flag=True, help="Fail on warnings and informational findings too")
@click.pass_context
def funnels_lint(ctx, json_file, strict):
    """Score a compact page spec and flag design/conversion problems."""
    from cli_anything.gohighlevel.utils import landing_page_design as design
    with open(json_file) as f:
        report = design.lint_spec(json.load(f), strict=strict)
    if ctx.obj["json"]:
        click.echo(json.dumps(report, indent=2))
    else:
        click.echo(f"Design score: {report['score']}/100")
        click.echo(" · ".join(f"{k}: {v}" for k, v in report["summary"].items()))
        for issue in report["issues"]:
            click.echo(f"[{issue['severity'].upper()}] {issue['code']} {issue['path']}: {issue['message']}")
    if not report["passed"]:
        raise click.exceptions.Exit(1)


@funnels.command("preview")
@click.argument("json_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--output", required=True, type=click.Path(dir_okay=False))
def funnels_preview(json_file, output):
    """Render a local responsive HTML preview before touching GHL."""
    from cli_anything.gohighlevel.utils import landing_page_design as design
    with open(json_file) as f:
        path = design.render_preview(json.load(f), output)
    click.echo(f"Rendered preview to {path}")


@funnels.command("list")
@click.option("--limit", default=50)
@click.option("--type", "funnel_type", default="funnel",
              type=click.Choice(["funnel", "website"]))
@click.pass_context
def funnels_list(ctx, limit, funnel_type):
    """List funnels or websites (experimental, internal API)."""
    _require_experimental(ctx)
    try:
        client = _get_internal_client(ctx)
        path = (f"/funnels/funnel/list?locationId={_loc(ctx)}"
                f"&limit={limit}&offset=0&type={funnel_type}")
        data = client.request("GET", path, extra_headers={"Version": "2021-07-28"})
        _output(ctx, data, f"Funnels ({funnel_type})")
    except Exception as e:
        _handle_error(e)


@funnels.command("create")
@click.option("--name", required=True, help="Funnel name")
@click.option("--type", "funnel_type", default="funnel",
              type=click.Choice(["funnel", "website"]))
@click.pass_context
def funnels_create(ctx, name, funnel_type):
    """Create an empty funnel shell (experimental)."""
    _require_experimental(ctx)
    try:
        client = _get_internal_client(ctx)
        r = client.create_funnel(name, funnel_type)
        if not r or (isinstance(r, dict) and r.get("_error")):
            click.echo(f"Error creating funnel: {r}", err=True)
            sys.exit(1)
        if ctx.obj["json"]:
            click.echo(json.dumps(r, indent=2, default=str))
        else:
            click.echo(f"Created funnel shell '{name}' ({r.get('id')}).")
    except Exception as e:
        _handle_error(e)


@funnels.command("pages")
@click.argument("funnel_id")
@click.option("--limit", default=20, type=click.IntRange(1, 20), show_default=True)
@click.pass_context
def funnels_pages(ctx, funnel_id, limit):
    """List a funnel's page records."""
    _require_experimental(ctx)
    try:
        _output(ctx, _get_internal_client(ctx).list_funnel_pages(funnel_id, limit), "Pages")
    except Exception as e:
        _handle_error(e)


def _page_data_from_spec(spec, page_id, funnel_id, location_id):
    """Accept raw pageData or expand the compact page-builder spec."""
    import copy
    candidate = spec.get("pageData", spec)
    sections = candidate.get("sections") if isinstance(candidate, dict) else None
    is_raw = bool(sections and isinstance(sections[0], dict)
                  and "metaData" in sections[0] and "elements" in sections[0])
    if is_raw:
        data = copy.deepcopy(candidate)
        for section in data["sections"]:
            section["pageId"] = page_id
            section["funnelId"] = funnel_id
            section["locationId"] = location_id
        return data
    if "sections" not in spec:
        raise ValueError("page spec needs 'sections' or 'pageData'")
    from cli_anything.gohighlevel.utils import funnel_page_builder as fpb
    return fpb.build_page_data(spec, page_id=page_id, funnel_id=funnel_id,
                               location_id=location_id)


def _download_page_data(client, page_id, page_type="draft"):
    page = client.get_funnel_page(page_id)
    versions = [v for v in (page or {}).get("versionHistory", [])
                if v.get("pageType") == page_type]
    if not versions:
        raise ValueError(f"page has no {page_type!r} version")
    response = requests.get(versions[0]["pageDownloadUrl"], timeout=30)
    response.raise_for_status()
    return response.json()


def _write_page_backup(page_id, page_data, output=None):
    """Persist a recoverable draft snapshot before replacing builder content."""
    if output:
        path = Path(output)
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = Path.cwd() / ".ghl-backups" / f"{page_id}-{stamp}-draft.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(page_data, indent=2) + "\n", encoding="utf-8")
    return path


@funnels.command("export-page")
@click.argument("page_id")
@click.option("--output", required=True, type=click.Path(dir_okay=False))
@click.option("--version", "page_type", default="draft",
              type=click.Choice(["draft", "live"]))
@click.pass_context
def funnels_export_page(ctx, page_id, output, page_type):
    """Download a page's complete builder-v2 JSON for backup or reuse."""
    _require_experimental(ctx)
    try:
        data = _download_page_data(_get_internal_client(ctx), page_id, page_type)
        with open(output, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        click.echo(f"Exported {page_type} page data to {output}")
    except Exception as e:
        _handle_error(e)


@funnels.command("elements")
@click.argument("page_id")
@click.option("--version", "page_type", default="draft",
              type=click.Choice(["draft", "live"]))
@click.pass_context
def funnels_elements(ctx, page_id, page_type):
    """List every native element id and type stored on a page."""
    _require_experimental(ctx)
    try:
        data = _download_page_data(_get_internal_client(ctx), page_id, page_type)
        result = []
        for section in data.get("sections", []):
            for node in section.get("elements", []):
                if node.get("type") == "element":
                    result.append({"id": node.get("id"), "type": node.get("meta"),
                                   "title": node.get("title"), "container": section.get("id")})
        for node in data.get("popups", []):
            if node.get("type") == "element":
                result.append({"id": node.get("id"), "type": node.get("meta"),
                               "title": node.get("title"), "container": "popup"})
        if ctx.obj["json"]:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            _output(ctx, result, "Elements")
    except Exception as e:
        _handle_error(e)


@funnels.command("export-element")
@click.argument("page_id")
@click.argument("element_id")
@click.option("--output", required=True, type=click.Path(dir_okay=False))
@click.option("--version", "page_type", default="draft",
              type=click.Choice(["draft", "live"]))
@click.pass_context
def funnels_export_element(ctx, page_id, element_id, output, page_type):
    """Export one native node for reuse as a compact-spec native element."""
    _require_experimental(ctx)
    try:
        data = _download_page_data(_get_internal_client(ctx), page_id, page_type)
        nodes = [node for section in data.get("sections", []) for node in section.get("elements", [])]
        nodes.extend(data.get("popups", []))
        node = next((n for n in nodes if n.get("id") == element_id), None)
        if not node:
            raise ValueError(f"element not found: {element_id}")
        with open(output, "w") as f:
            json.dump({"type": "native", "node": node}, f, indent=2)
            f.write("\n")
        click.echo(f"Exported {node.get('meta')} element to {output}")
    except Exception as e:
        _handle_error(e)


@funnels.command("export-global-sections")
@click.argument("funnel_id")
@click.option("--output", required=True, type=click.Path(dir_okay=False))
@click.pass_context
def funnels_export_global_sections(ctx, funnel_id, output):
    """Download a funnel's shared header/footer section artifact."""
    _require_experimental(ctx)
    try:
        funnel = _get_internal_client(ctx).get_funnel(funnel_id)
        url = (funnel or {}).get("globalSectionsDownloadUrl") or (funnel or {}).get("globalSectionsUrl")
        if not url:
            raise ValueError("funnel has no global-sections artifact")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(output, "w") as f:
            json.dump(response.json(), f, indent=2)
            f.write("\n")
        click.echo(f"Exported global sections to {output}")
    except Exception as e:
        _handle_error(e)


@funnels.command("set-global-sections")
@click.argument("funnel_id")
@click.option("--from-json", "json_file", required=True, type=click.Path(exists=True))
@click.option("--yes", is_flag=True, help="Confirm replacing shared sections for every page in this funnel")
@click.pass_context
def funnels_set_global_sections(ctx, funnel_id, json_file, yes):
    """Replace a funnel's shared sections from an exported JSON artifact."""
    _require_experimental(ctx)
    if not yes:
        raise click.ClickException("set-global-sections affects every page; rerun with --yes")
    try:
        with open(json_file) as f:
            sections = json.load(f)
        if not isinstance(sections, list):
            raise ValueError("global-sections JSON must be a list")
        client = _get_internal_client(ctx)
        funnel = client.get_funnel(funnel_id) or {}
        version = int(funnel.get("globalSectionVersion") or 0) + 1
        result = client.save_global_sections(funnel_id, sections, version)
        if not result or (isinstance(result, dict) and result.get("_error")):
            raise RuntimeError(f"global-section save failed: {result}")
        _output(ctx, result, "Global sections")
    except Exception as e:
        _handle_error(e)


@funnels.command("create-page")
@click.argument("funnel_id")
@click.option("--from-json", "json_file", required=True, type=click.Path(exists=True))
@click.option("--publish", is_flag=True, help="Create a live version as well as a draft")
@click.pass_context
def funnels_create_page(ctx, funnel_id, json_file, publish):
    """Create a step/page and populate it from compact or raw builder JSON."""
    _require_experimental(ctx)
    try:
        import uuid
        from cli_anything.gohighlevel.utils import funnel_page_builder as fpb
        with open(json_file) as f:
            spec = json.load(f)
        name = spec.get("name", "Landing Page")
        path = spec.get("path", "/landing-page")
        if not path.startswith("/"):
            path = "/" + path
        step = {"id": str(uuid.uuid4()), "name": name, "url": path, "pages": [],
                "type": spec.get("pageType", "optin_funnel_page"), "split": False,
                "control_traffic": 100, "sequence": int(spec.get("sequence", 1))}
        client = _get_internal_client(ctx)
        created = client.create_funnel_step_page(funnel_id, step)
        page = (created or {}).get("page") or ((created or {}).get("data") or {}).get("page")
        page_id = (page or {}).get("_id")
        if not page_id:
            raise RuntimeError(f"page creation did not return an id: {created}")
        # GHL returns the new page id before its page record is consistently
        # readable.  Saving immediately can otherwise fail with a misleading
        # "Page does not exist or is deleted" response.
        for _ in range(10):
            page_record = client.get_funnel_page(page_id)
            if page_record and not page_record.get("_error"):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError(f"new page did not become available: {page_id}")
        page_data = _page_data_from_spec(spec, page_id, funnel_id, _loc(ctx))
        saved = client.save_funnel_page(page_id, funnel_id, page_data, page_version=2,
                                        publish=False, meta=spec.get("seo"))
        if not saved or saved.get("_error"):
            raise RuntimeError(f"draft page save failed: {saved}")
        if publish:
            live_saved = client.save_funnel_page(
                page_id, funnel_id, page_data, page_version=2,
                publish=True, meta=spec.get("seo"),
            )
            if not live_saved or live_saved.get("_error"):
                raise RuntimeError(f"live page save failed: {live_saved}")
        result = {"funnelId": funnel_id, "stepId": step["id"], "pageId": page_id,
                  "name": name, "published": publish, "save": saved}
        if ctx.obj["json"]:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            click.echo(f"Created {'live' if publish else 'draft'} page '{name}' ({page_id}) — "
                       f"{fpb.count_summary(page_data)}")
    except Exception as e:
        _handle_error(e)


@funnels.command("set-content")
@click.argument("page_id")
@click.option("--from-json", "json_file", required=True, type=click.Path(exists=True))
@click.option("--backup-output", type=click.Path(dir_okay=False),
              help="Draft backup path (default: .ghl-backups/<page>-<UTC>-draft.json)")
@click.option("--publish", is_flag=True, help="Save as the live version")
@click.pass_context
def funnels_set_content(ctx, page_id, json_file, backup_output, publish):
    """Back up the draft, then replace full builder content."""
    _require_experimental(ctx)
    try:
        from cli_anything.gohighlevel.utils import funnel_page_builder as fpb
        with open(json_file) as f:
            spec = json.load(f)
        client = _get_internal_client(ctx)
        page = client.get_funnel_page(page_id)
        if not page or page.get("_error"):
            raise ValueError(f"page not found: {page_id}")
        funnel_id = page["funnelId"]
        backup_path = _write_page_backup(
            page_id, _download_page_data(client, page_id, "draft"), backup_output,
        )
        click.echo(f"Backed up current draft to {backup_path}", err=bool(ctx.obj["json"]))
        page_data = _page_data_from_spec(spec, page_id, funnel_id, _loc(ctx))
        result = client.save_funnel_page(
            page_id, funnel_id, page_data,
            page_version=int(page.get("pageVersion") or 1) + 1,
            publish=publish, meta=spec.get("seo"),
        )
        if not result or result.get("_error"):
            raise RuntimeError(f"page save failed: {result}")
        if ctx.obj["json"]:
            click.echo(json.dumps(result, indent=2, default=str))
        else:
            click.echo(f"Saved {'live' if publish else 'draft'} page {page_id} — "
                       f"{fpb.count_summary(page_data)}. Visual verification on the real GHL preview is still required.")
    except Exception as e:
        _handle_error(e)


@funnels.command("delete")
@click.argument("funnel_id")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt")
@click.pass_context
def funnels_delete(ctx, funnel_id, yes):
    """Delete a funnel (experimental, internal API)."""
    _require_experimental(ctx)
    try:
        if not yes:
            click.confirm(
                f"Delete funnel {funnel_id}? This permanently removes the funnel and its pages. Continue?",
                abort=True,
            )
        client = _get_internal_client(ctx)
        ok = client.delete_funnel(funnel_id)
        click.echo("Deleted." if ok else "Delete failed.", err=not ok)
        if not ok:
            sys.exit(1)
    except click.Abort:
        click.echo("Aborted.", err=True)
        sys.exit(1)
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# SOCIAL MEDIA
# ===========================================================================

@cli.group()
@click.pass_context
def social(ctx):
    """Social media posts and analytics."""
    pass


@social.command("accounts")
@click.pass_context
def social_accounts(ctx):
    """List connected social media accounts."""
    try:
        data = api.get(f"/social-media-posting/{_loc(ctx)}/accounts")
        _output(ctx, data, "Social Accounts")
    except Exception as e:
        _handle_error(e)


@social.command("posts")
@click.option("--limit", default=20)
@click.option("--offset", "skip", default=0)
@click.option("--type", "post_type", default=None, help="Filter by post type")
@click.pass_context
def social_posts(ctx, limit, skip, post_type):
    """List social media posts."""
    try:
        import datetime as _dt
        now = _dt.datetime.now(_dt.timezone.utc)
        params = {
            "skip": str(skip),
            "limit": str(limit),
            "fromDate": (now - _dt.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "toDate": (now + _dt.timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "includeUsers": "false",
        }
        if post_type:
            params["type"] = post_type
        data = api.post(f"/social-media-posting/{_loc(ctx)}/posts/list", data=params)
        _output(ctx, data, "Social Posts")
    except Exception as e:
        _handle_error(e)


@social.command("create-post")
@click.option("--account-id", required=True, multiple=True, help="Social account IDs (repeatable)")
@click.option("--text", required=True, help="Post text content")
@click.option("--media-url", default=None, multiple=True, help="Media URLs (repeatable)")
@click.option("--schedule", default=None, help="Schedule time (ISO 8601)")
@click.pass_context
def social_create_post(ctx, account_id, text, media_url, schedule):
    """Create a social media post."""
    try:
        body = {
            "locationId": _loc(ctx),
            "accountIds": list(account_id),
            "summary": text,
        }
        if media_url:
            body["media"] = [{"url": u, "type": "image"} for u in media_url]
        if schedule:
            body["scheduledAt"] = schedule
        data = api.post(f"/social-media-posting/{_loc(ctx)}/posts", data=body)
        _output(ctx, data, "Post Created")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# LOCATIONS
# ===========================================================================

@cli.group()
@click.pass_context
def locations(ctx):
    """Location/sub-account management."""
    pass


@locations.command("get")
@click.pass_context
def locations_get(ctx):
    """Get current location details."""
    try:
        data = api.get(f"/locations/{_loc(ctx)}")
        _output(ctx, data, "Location Details")
    except Exception as e:
        _handle_error(e)


@locations.command("search")
@click.option("--company-id", required=True, help="Company/Agency ID")
@click.option("--limit", default=20)
@click.option("--offset", "skip", default=0)
@click.option("--query", default=None, help="Search query")
@click.pass_context
def locations_search(ctx, company_id, limit, skip, query):
    """Search locations (requires company-level access)."""
    try:
        params = {"companyId": company_id, "limit": limit, "skip": skip}
        if query:
            params["query"] = query
        data = api.get("/locations/search", params=params)
        _output(ctx, data, "Locations")
    except Exception as e:
        _handle_error(e)


@locations.command("tags")
@click.pass_context
def locations_tags(ctx):
    """List tags for current location."""
    try:
        data = api.get(f"/locations/{_loc(ctx)}/tags")
        _output(ctx, data, "Location Tags")
    except Exception as e:
        _handle_error(e)


@locations.command("custom-fields")
@click.pass_context
def locations_custom_fields(ctx):
    """List custom fields for current location."""
    try:
        data = api.get(f"/locations/{_loc(ctx)}/customFields")
        _output(ctx, data, "Custom Fields")
    except Exception as e:
        _handle_error(e)


@locations.command("custom-values")
@click.pass_context
def locations_custom_values(ctx):
    """List custom values for current location."""
    try:
        data = api.get(f"/locations/{_loc(ctx)}/customValues")
        _output(ctx, data, "Custom Values")
    except Exception as e:
        _handle_error(e)


@locations.command("set-custom-value")
@click.option("--name", required=True, help="Custom value name (created if it doesn't exist)")
@click.option("--value", required=True, help="Value to set")
@click.pass_context
def locations_set_custom_value(ctx, name, value):
    """Create or update a location custom value by name.

    Looks up the custom value by (case-insensitive) name: PUTs the new value if
    it exists, else POSTs to create it. Returns the id + `fieldKey` merge tag
    (e.g. {{ custom_values.blast_message }}). Used by the /sms-blast skill to set
    the dynamic blast message before firing.
    """
    try:
        loc = _loc(ctx)
        data = api.get(f"/locations/{loc}/customValues")
        existing = next(
            (cv for cv in (data.get("customValues") or [])
             if (cv.get("name") or "").strip().lower() == name.strip().lower()),
            None,
        )
        if existing:
            res = api.put(f"/locations/{loc}/customValues/{existing['id']}",
                          {"name": name, "value": value})
            action = "updated"
        else:
            res = api.post(f"/locations/{loc}/customValues",
                           {"name": name, "value": value})
            action = "created"
        cv = (res.get("customValue") if isinstance(res, dict) else None) or res
        summary = {"action": action}
        if isinstance(cv, dict):
            summary.update({k: cv.get(k) for k in ("id", "name", "fieldKey", "value")})
        _output(ctx, summary, f"Custom Value {action}")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# SAAS SUB-ACCOUNTS
# ===========================================================================

@cli.group()
@click.pass_context
def saas(ctx):
    """Audit and manage agency SaaS sub-accounts."""
    pass


@saas.command("locations")
@click.option("--company-id", required=True, help="Company/Agency ID")
@click.option("--page", default=1, type=click.IntRange(min=1), show_default=True)
@click.pass_context
def saas_locations(ctx, company_id, page):
    """List SaaS-enabled sub-accounts for an agency."""
    try:
        data = api.get(f"/saas/saas-locations/{company_id}", params={"page": page})
        _output(ctx, data, "SaaS Locations")
    except Exception as e:
        _handle_error(e)


@saas.command("find-location")
@click.option("--company-id", required=True, help="Company/Agency ID")
@click.option("--customer-id", default=None, help="Stripe customer ID")
@click.option("--subscription-id", default=None, help="Stripe subscription ID")
@click.pass_context
def saas_find_location(ctx, company_id, customer_id, subscription_id):
    """Find a sub-account from a Stripe customer or subscription ID."""
    if not customer_id and not subscription_id:
        raise click.UsageError("Provide --customer-id or --subscription-id.")
    try:
        params = {"companyId": company_id}
        if customer_id:
            params["customerId"] = customer_id
        if subscription_id:
            params["subscriptionId"] = subscription_id
        data = api.get("/saas/locations", params=params)
        _output(ctx, data, "SaaS Location Match")
    except Exception as e:
        _handle_error(e)


@saas.command("subscription")
@click.argument("location_id")
@click.option("--company-id", required=True, help="Company/Agency ID")
@click.pass_context
def saas_subscription(ctx, location_id, company_id):
    """Get the agency SaaS subscription attached to a sub-account."""
    try:
        data = api.get(
            f"/saas/get-saas-subscription/{location_id}",
            params={"companyId": company_id},
        )
        _output(ctx, data, "SaaS Subscription")
    except Exception as e:
        _handle_error(e)


def _audit_error_label(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        return f"HTTP {status}"
    return f"{type(exc).__name__}: {str(exc)[:160]}"


def _audit_saas_locations(company_id: str) -> list[dict]:
    rows: list[dict] = []
    seen_ids: set[str] = set()
    page, expected_total = 1, None
    while True:
        payload = api.get(f"/saas/saas-locations/{company_id}", params={"page": page})
        batch, pagination = saas_audit_utils.extract_saas_page(payload)
        raw_page = pagination.get("page")
        raw_total_pages = pagination.get("totalPages")
        raw_total = pagination.get("total")
        has_next = pagination.get("hasNext")
        try:
            if any(isinstance(value, bool) for value in (raw_page, raw_total_pages, raw_total)):
                raise ValueError
            current_page = int(raw_page)
            total_pages = int(raw_total_pages)
            total = int(raw_total)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid SaaS pagination metadata on page {page}.") from None
        if (
            not isinstance(has_next, bool)
            or current_page != page
            or total < 0
            or total_pages < 0
            or (total > 0 and total_pages < 1)
            or has_next != (page < total_pages)
        ):
            raise ValueError(f"Invalid SaaS pagination metadata on page {page}.")
        expected_total = total if expected_total is None else expected_total
        if total != expected_total:
            raise ValueError("SaaS location total changed during pagination.")
        batch_ids = {str(item.get("locationId") or "") for item in batch}
        if (batch and "" in batch_ids) or seen_ids.intersection(batch_ids):
            raise ValueError(f"SaaS pagination did not advance safely on page {page}.")
        rows.extend(batch)
        seen_ids.update(batch_ids)
        if not has_next:
            break
        page += 1
        if page > 10_000:
            raise ValueError("SaaS pagination exceeded its safety limit.")
    if len(rows) != expected_total:
        raise ValueError(
            f"SaaS pagination returned {len(rows)} rows but declared {expected_total}."
        )
    return rows


def _audit_location_profiles(company_id: str) -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    limit, skip = 100, 0
    while True:
        payload = api.get(
            "/locations/search",
            params={"companyId": company_id, "limit": limit, "skip": skip},
            version="v3",
            agency=True,
        )
        batch = saas_audit_utils.extract_location_page(payload)
        new_ids = {
            str(item.get("id") or "")
            for item in batch
            if item.get("id") and str(item.get("id")) not in profiles
        }
        if batch and not new_ids:
            raise ValueError(f"Agency location pagination did not advance at skip {skip}.")
        for item in batch:
            if item.get("id"):
                profiles[str(item["id"])] = item
        if len(batch) < limit:
            break
        skip += len(batch)
    return profiles


def _audit_payment_subscriptions(location_id: str) -> list[dict]:
    rows: list[dict] = []
    limit, offset, expected = 1000, 0, None
    while True:
        payload = api.get(
            "/payments/subscriptions",
            params={
                "altId": location_id,
                "altType": "location",
                "limit": limit,
                "offset": offset,
            },
        )
        batch, total = saas_audit_utils.extract_payment_page(payload)
        expected = total if expected is None else expected
        if total != expected:
            raise ValueError("Payment subscription total changed during pagination.")
        rows.extend(batch)
        offset += len(batch)
        if offset >= total:
            break
        if not batch:
            raise ValueError("Payment subscription pagination stopped before totalCount.")
    return rows


def _audit_latest_transaction(location_id: str, subscription_id: str) -> dict | None:
    rows: list[dict] = []
    limit, offset, expected = 100, 0, None
    while True:
        payload = api.get(
            "/payments/transactions",
            params={
                "altId": location_id,
                "altType": "location",
                "subscriptionId": subscription_id,
                "limit": limit,
                "offset": offset,
            },
        )
        batch, total = saas_audit_utils.extract_transaction_page(payload)
        expected = total if expected is None else expected
        if total != expected:
            raise ValueError("Payment transaction total changed during pagination.")
        rows.extend(batch)
        offset += len(batch)
        if offset >= total:
            break
        if not batch:
            raise ValueError("Payment transaction pagination stopped before totalCount.")
    return saas_audit_utils.latest_successful_transaction(rows)


def _audit_order_product_ids(location_id: str, order_id: str) -> set[str]:
    payload = api.get(
        f"/payments/orders/{order_id}",
        params={"altId": location_id, "altType": "location"},
        version="v3",
    )
    if not isinstance(payload, dict):
        raise ValueError("Unexpected payment order response envelope.")
    return saas_audit_utils.order_product_ids(payload)


@saas.command("audit")
@click.option("--company-id", required=True, help="Company/Agency ID")
@click.option(
    "--billing-location-id",
    envvar="GHL_LOCATION_ID",
    required=True,
    help="Location containing the funnel payment subscriptions",
)
@click.option(
    "--product-id",
    envvar="GHL_SAAS_PRODUCT_ID",
    required=True,
    help="Payment product to reconcile",
)
@click.option(
    "--comped-emails-file",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Newline file or JSON string list from an authoritative comp ledger",
)
@click.option(
    "--internal-domain",
    multiple=True,
    default=saas_audit_utils.DEFAULT_INTERNAL_DOMAINS,
    show_default=True,
    help="Exact email domain classified as internal (repeatable)",
)
@click.pass_context
def saas_audit(ctx, company_id, billing_location_id, product_id, comped_emails_file, internal_domain):
    """Audit live SaaS sub-accounts against their separate payment records."""
    if not os.environ.get("GHL_AGENCY_API_KEY", "").strip():
        raise click.UsageError(
            "GHL_AGENCY_API_KEY is required for the read-only agency SaaS audit."
        )
    try:
        comped_emails = saas_audit_utils.load_comped_emails(comped_emails_file)
        internal_domains = {
            str(domain).strip().lower().lstrip("@") for domain in internal_domain if str(domain).strip()
        }
        warnings: list[str] = []
        if not comped_emails_file:
            warnings.append(
                "No authoritative deal_grant email file was loaded; only exact internal domains can be marked comped."
            )

        saas_locations = _audit_saas_locations(company_id)
        all_payments = _audit_payment_subscriptions(billing_location_id)
        resolved_products: list[tuple[dict, set[str]]] = []
        order_product_lookups = 0
        product_resolution_errors = 0
        for payment in all_payments:
            identifiers = saas_audit_utils.product_ids(payment)
            if not identifiers:
                order_product_lookups += 1
                order_id = str(payment.get("entityId") or "")
                if not order_id:
                    product_resolution_errors += 1
                else:
                    try:
                        identifiers = _audit_order_product_ids(billing_location_id, order_id)
                    except Exception:
                        product_resolution_errors += 1
            resolved_products.append((payment, identifiers))
        product_conflicts = [row for row, identifiers in resolved_products if len(identifiers) > 1]
        unidentified_products = [row for row, identifiers in resolved_products if not identifiers]
        payments = [row for row, identifiers in resolved_products if identifiers == {product_id}]
        contact_ids = {str(row.get("contactId")) for row in payments if row.get("contactId")}
        population = saas_audit_utils.population_check(len(payments), len(contact_ids))
        if product_conflicts or unidentified_products or product_resolution_errors:
            population["status"] = "failed"
            population["reason"] = "one or more payment product identities could not be proven"

        profiles_error = None
        try:
            location_profiles = _audit_location_profiles(company_id)
        except Exception as exc:
            location_profiles = {}
            profiles_error = _audit_error_label(exc)

        read_errors: dict[str, list[str]] = defaultdict(list)
        saas_details: dict[str, dict] = {}
        for source in saas_locations:
            location_id = str(source.get("locationId") or "")
            if profiles_error:
                read_errors[location_id].append(f"agency location read failed: {profiles_error}")
            elif location_id not in location_profiles:
                read_errors[location_id].append("agency location profile was not returned")
            try:
                payload = api.get(
                    f"/saas/get-saas-subscription/{location_id}",
                    params={"companyId": company_id},
                )
                detail = saas_audit_utils.extract_saas_detail(payload)
                if str(detail.get("locationId")) != location_id:
                    raise ValueError("SaaS detail returned a different locationId.")
                saas_details[location_id] = detail
                list_info = source.get("subscriptionInfo") or {}
                if (
                    detail.get("subscriptionId") != source.get("subscriptionId")
                    or detail.get("subscriptionStatus") != list_info.get("subscriptionStatus")
                ):
                    read_errors[location_id].append("SaaS list and detail reads disagreed")
            except Exception as exc:
                read_errors[location_id].append(f"SaaS subscription read failed: {_audit_error_label(exc)}")

        payments_by_email: dict[str, list[dict]] = defaultdict(list)
        for payment in payments:
            email = saas_audit_utils.normalized_email(payment.get("contactEmail"))
            if email:
                payments_by_email[email].append(payment)

        # The join that matters. GoHighLevel merges contacts on phone, so contactId sees
        # across a person's several email addresses where an email match cannot.
        payments_by_contact: dict[str, list[dict]] = defaultdict(list)
        for payment in payments:
            contact_id = str(payment.get("contactId") or "")
            if contact_id:
                payments_by_contact[contact_id].append(payment)

        saas_emails = {
            saas_audit_utils.normalized_email(item.get("email"))
            for item in saas_locations
            if item.get("email")
        }
        candidates_by_location, join_by_location, join_errors = saas_audit_utils.resolve_joins(
            saas_locations,
            saas_details,
            payments_by_contact,
            payments_by_email,
            location_profiles,
        )
        for location_id, messages in join_errors.items():
            read_errors[location_id].extend(messages)

        required_payment_ids: set[str] = set()
        payment_locations: dict[str, set[str]] = defaultdict(set)
        for source in saas_locations:
            location_id = str(source.get("locationId") or "")
            for payment in candidates_by_location.get(location_id, []):
                subscription_id = str(payment.get("subscriptionId") or "")
                if not subscription_id:
                    read_errors[location_id].append("payment subscription has no provider subscriptionId")
                    continue
                required_payment_ids.add(subscription_id)
                payment_locations[subscription_id].add(location_id)

        transaction_evidence: dict[str, dict | None] = {}
        for subscription_id in sorted(required_payment_ids):
            try:
                transaction_evidence[subscription_id] = _audit_latest_transaction(
                    billing_location_id, subscription_id
                )
            except Exception as exc:
                transaction_evidence[subscription_id] = None
                label = _audit_error_label(exc)
                for location_id in payment_locations[subscription_id]:
                    read_errors[location_id].append(f"payment transaction read failed: {label}")

        rows = saas_audit_utils.build_rows(
            saas_locations,
            saas_details,
            location_profiles,
            candidates_by_location,
            transaction_evidence,
            read_errors,
            comped_emails,
            internal_domains,
            join_by_location,
        )
        if population["status"] == "failed":
            for row in rows:
                row["errors"].append("population safety check failed; classification withheld")
                row["classification"] = "unknown"
        # An orphan is a payment subscription no SaaS location claims. Under the contact-id
        # join that means neither its contact nor its email reaches one, so a person paying
        # under a second address no longer counts as orphaned the way they used to.
        saas_contact_ids = {
            str(join.get("contactId") or "")
            for join in join_by_location.values()
            if join.get("contactId")
        }
        orphan_ids = sorted(
            str(payment.get("subscriptionId"))
            for payment in payments
            if payment.get("subscriptionId")
            and str(payment.get("contactId") or "") not in saas_contact_ids
            and saas_audit_utils.normalized_email(payment.get("contactEmail")) not in saas_emails
        )
        email_fallback = sum(row["join"].get("method") == "email" for row in rows)
        shared_contacts = sum(row["join"].get("locationsOnContact", 1) > 1 for row in rows)
        unresolved_shared = sum(
            row["join"].get("sharedContactResolved") is False for row in rows
        )
        if orphan_ids:
            warnings.append(
                f"{len(orphan_ids)} payment subscriptions matched no SaaS location by contact id or email."
            )
        if email_fallback:
            warnings.append(
                f"{email_fallback} SaaS locations carried no contact id and fell back to the email join."
            )
        if shared_contacts:
            warnings.append(
                f"{shared_contacts} SaaS locations share a contact id with another location "
                "(GoHighLevel merges contacts on phone); "
                f"{unresolved_shared} of them had too few active subscriptions to cover every "
                "location and are reported unknown."
            )
        if unidentified_products:
            warnings.append(
                f"{len(unidentified_products)} payment subscriptions still had no proven product ID after order-detail lookup."
            )
        if order_product_lookups:
            warnings.append(
                f"{order_product_lookups} payment subscriptions required a fresh order-detail read to prove product identity."
            )
        if product_conflicts:
            warnings.append(
                f"{len(product_conflicts)} payment subscriptions exposed conflicting product IDs."
            )
        warnings.append(
            "Deleted locations are not returned by the public SaaS location list and cannot be enumerated by this audit."
        )
        report = {
            "companyId": company_id,
            "billingLocationId": billing_location_id,
            "productId": product_id,
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "populationCheck": population,
            "summary": {
                "locations": len(rows),
                "classifications": None
                if population["status"] == "failed"
                else saas_audit_utils.classification_counts(rows),
            },
            "diagnostics": {
                "paymentOnlySubscriptions": len(orphan_ids),
                "paymentOnlySubscriptionIds": orphan_ids,
                "emailFallbackRows": email_fallback,
                "sharedContactRows": shared_contacts,
                "unresolvedSharedContactRows": unresolved_shared,
                "joinMethod": "ghl-contact-id, exact-normalized-email fallback",
                "unidentifiedProductSubscriptions": len(unidentified_products),
                "conflictingProductSubscriptions": len(product_conflicts),
                "orderProductLookups": order_product_lookups,
                "productResolutionErrors": product_resolution_errors,
            },
            "rows": rows,
            "warnings": warnings,
        }
        if ctx.obj.get("json", False):
            click.echo(json.dumps(report, indent=2, default=str))
        else:
            click.echo(saas_audit_utils.render_table(report))
        if population["status"] == "failed":
            raise SystemExit(2)
    except Exception as exc:
        _handle_error(exc)


def _lifecycle_read_target(
    company_id: str,
    location_id: str,
    billing_location_id: str,
    product_id: str,
) -> dict:
    """Build one lifecycle target using the audit's proven read and join model."""
    saas_locations = _audit_saas_locations(company_id)
    source = next(
        (item for item in saas_locations if str(item.get("locationId") or "") == location_id),
        None,
    )
    if source is None:
        raise ValueError(f"Location {location_id} is not in the agency SaaS location list.")
    profiles = _audit_location_profiles(company_id)
    if location_id not in profiles:
        raise ValueError("Agency location profile was not returned.")
    detail = saas_audit_utils.extract_saas_detail(
        api.get(
            f"/saas/get-saas-subscription/{location_id}",
            params={"companyId": company_id},
        )
    )
    if str(detail.get("locationId") or "") != location_id:
        raise ValueError("SaaS detail returned a different locationId.")

    resolved_payments: list[dict] = []
    product_errors = 0
    for payment in _audit_payment_subscriptions(billing_location_id):
        identifiers = saas_audit_utils.product_ids(payment)
        if not identifiers:
            order_id = str(payment.get("entityId") or "")
            if not order_id:
                product_errors += 1
                continue
            try:
                identifiers = _audit_order_product_ids(billing_location_id, order_id)
            except Exception:
                product_errors += 1
                continue
        if len(identifiers) > 1:
            product_errors += 1
        elif identifiers == {product_id}:
            resolved_payments.append(payment)

    payments_by_contact: dict[str, list[dict]] = defaultdict(list)
    payments_by_email: dict[str, list[dict]] = defaultdict(list)
    for payment in resolved_payments:
        contact_id = str(payment.get("contactId") or "")
        email = saas_audit_utils.normalized_email(payment.get("contactEmail"))
        if contact_id:
            payments_by_contact[contact_id].append(payment)
        if email:
            payments_by_email[email].append(payment)
    candidates, joins, join_errors = saas_audit_utils.resolve_joins(
        saas_locations,
        {location_id: detail},
        payments_by_contact,
        payments_by_email,
        profiles,
    )
    errors = list(join_errors.get(location_id, []))
    if product_errors:
        errors.append(
            f"{product_errors} payment records had unprovable or conflicting product identity"
        )
    evidence: dict[str, dict | None] = {}
    for payment in candidates.get(location_id, []):
        subscription_id = str(payment.get("subscriptionId") or "")
        if not subscription_id:
            errors.append("payment subscription has no provider subscriptionId")
            continue
        try:
            evidence[subscription_id] = _audit_latest_transaction(
                billing_location_id, subscription_id
            )
        except Exception as exc:
            errors.append(f"payment transaction read failed: {_audit_error_label(exc)}")
    row = saas_audit_utils.build_rows(
        [source],
        {location_id: detail},
        profiles,
        candidates,
        evidence,
        {location_id: errors},
        set(),
        set(),
        joins,
    )[0]
    return row


def _lifecycle_preflight(location_id: str) -> None:
    if not os.environ.get("GHL_AGENCY_API_KEY", "").strip():
        raise click.UsageError("GHL_AGENCY_API_KEY is required for lifecycle commands.")
    protected = saas_lifecycle_utils.protected_location_id()
    if protected and location_id == protected:
        raise click.UsageError("Your primary location is permanently protected.")


def _lifecycle_emit(ctx: click.Context, payload: dict, label: str) -> None:
    _output(ctx, payload, label)


def _lifecycle_target_summary(target: dict) -> dict:
    payments = (target.get("payment") or {}).get("subscriptions", [])
    invoice = (target.get("payment") or {}).get("lastInvoice") or {}
    return {
        "locationId": target.get("locationId"),
        "name": target.get("name"),
        "createdAt": target.get("createdAt"),
        "saasMode": target.get("saasMode"),
        "saasSubscription": (
            f"{(target.get('saas') or {}).get('status') or '-'} / "
            f"{(target.get('saas') or {}).get('subscriptionId') or '-'}"
        ),
        "paymentSubscriptions": ", ".join(
            f"{item.get('status') or '-'} / {item.get('id') or '-'}" for item in payments
        ) or "-",
        "lastPayment": (
            f"{invoice.get('date') or '-'} / {invoice.get('amount') or '-'} "
            f"{invoice.get('currency') or ''}"
        ).strip(),
        "errors": "; ".join(target.get("errors") or []) or "-",
    }


def _lifecycle_require_safe_apply(target: dict) -> None:
    if target.get("errors") or target.get("classification") == "unknown":
        raise click.UsageError("Apply refused because target reads or joins are not proven.")


def _lifecycle_options(function):
    options = [
        click.option("--company-id", required=True, help="Company/Agency ID"),
        click.option("--billing-location-id", envvar="GHL_LOCATION_ID", required=True),
        click.option("--product-id", envvar="GHL_SAAS_PRODUCT_ID", required=True),
        click.option("--apply", is_flag=True, help="Perform the single confirmed mutation"),
    ]
    for option in reversed(options):
        function = option(function)
    return function


@saas.command("disable")
@click.argument("location_id")
@click.option(
    "--export-dir",
    type=click.Path(file_okay=False),
    default="~/.config/ghl/exports",
    show_default=True,
    help="Private directory for the required pre-disable wallet export",
)
@_lifecycle_options
@click.pass_context
def saas_disable(ctx, location_id, export_dir, company_id, billing_location_id, product_id, apply):
    """Disable SaaS mode for one sub-account; dry-run unless --apply."""
    try:
        _lifecycle_preflight(location_id)
        target = _lifecycle_read_target(company_id, location_id, billing_location_id, product_id)
        if apply and ctx.obj.get("json", False):
            raise click.UsageError(
                "--json cannot be combined with --apply; rerun without --json for interactive approval."
            )
        report = {
            "action": "disable", "mode": "apply" if apply else "dry-run",
            "targetSummary": _lifecycle_target_summary(target), "target": target,
        }
        _lifecycle_emit(ctx, report, "SaaS Disable Target")
        if not apply:
            return
        _lifecycle_require_safe_apply(target)
        wallet = saas_lifecycle_utils.read_wallet_export(
            api.get, api.post, company_id, location_id
        )
        export_path = saas_lifecycle_utils.write_wallet_export(wallet, export_dir, location_id)
        click.echo(f"Wallet export: {export_path}")
        if not click.confirm("Approve disabling SaaS for this one target?", default=False):
            raise click.Abort()
        api.post(
            f"/saas/bulk-disable-saas/{company_id}",
            data={"locationIds": [location_id]},
            version="v3",
            agency=True,
        )
        fresh_profiles = _audit_location_profiles(company_id)
        if location_id not in fresh_profiles:
            raise RuntimeError(
                "Post-write verification could not prove the underlying location still exists."
            )
        fresh_saas_locations = _audit_saas_locations(company_id)
        if any(
            str(item.get("locationId") or "") == location_id
            for item in fresh_saas_locations
        ):
            raise RuntimeError("Post-write verification still found SaaS enabled.")
        _lifecycle_emit(
            ctx,
            {
                "verified": True,
                "walletExport": export_path,
                "state": {"saasEnabled": False, "location": fresh_profiles[location_id]},
            },
            "Disable Verified",
        )
    except Exception as exc:
        _handle_error(exc)


@saas.command("pause")
@click.argument("location_id")
@_lifecycle_options
@click.pass_context
def saas_pause(ctx, location_id, company_id, billing_location_id, product_id, apply):
    """Pause one sub-account; dry-run unless --apply."""
    try:
        _lifecycle_preflight(location_id)
        target = _lifecycle_read_target(company_id, location_id, billing_location_id, product_id)
        if apply and ctx.obj.get("json", False):
            raise click.UsageError(
                "--json cannot be combined with --apply; rerun without --json for interactive approval."
            )
        report = {
            "action": "pause", "mode": "apply" if apply else "dry-run",
            "targetSummary": _lifecycle_target_summary(target), "target": target,
            "consequences": list(saas_lifecycle_utils.PAUSE_CONSEQUENCES),
        }
        _lifecycle_emit(ctx, report, "SaaS Pause Target and Consequences")
        if not apply:
            return
        _lifecycle_require_safe_apply(target)
        if not click.confirm("Approve pausing this one sub-account?", default=False):
            raise click.Abort()
        api.post(
            f"/saas/pause/{location_id}",
            data={"paused": True, "companyId": company_id},
            version="v3",
            agency=True,
        )
        fresh = saas_audit_utils.extract_saas_detail(
            api.get(f"/saas/get-saas-subscription/{location_id}", params={"companyId": company_id})
        )
        fresh_target = {"saasMode": fresh.get("saasMode"), "saas": {"status": fresh.get("subscriptionStatus")}}
        if not saas_lifecycle_utils.is_paused(fresh_target):
            raise RuntimeError("Post-write verification did not show the sub-account paused.")
        _lifecycle_emit(ctx, {"verified": True, "state": fresh}, "Pause Verified")
    except Exception as exc:
        _handle_error(exc)


@saas.command("delete")
@click.argument("location_id")
@click.option("--reason", required=True, help="Audit reason (minimum 12 characters)")
@click.option("--delete-twilio-account", "twilio", flag_value=True, default=None)
@click.option("--keep-twilio-account", "twilio", flag_value=False)
@_lifecycle_options
@click.pass_context
def saas_delete(ctx, location_id, reason, twilio, company_id, billing_location_id, product_id, apply):
    """Delete one already-paused, non-paying sub-account; dry-run unless --apply."""
    try:
        _lifecycle_preflight(location_id)
        if twilio is None:
            raise click.UsageError("Choose --delete-twilio-account or --keep-twilio-account.")
        if len(reason.strip()) < saas_lifecycle_utils.MIN_REASON_LENGTH:
            raise click.UsageError("--reason must contain at least 12 characters.")
        target = _lifecycle_read_target(company_id, location_id, billing_location_id, product_id)
        if apply and ctx.obj.get("json", False):
            raise click.UsageError(
                "--json cannot be combined with --apply; rerun without --json for interactive approval."
            )
        report = {
            "action": "delete", "mode": "apply" if apply else "dry-run",
            "reason": reason.strip(), "deleteTwilioAccount": twilio,
            "targetSummary": _lifecycle_target_summary(target), "target": target,
        }
        _lifecycle_emit(ctx, report, "SaaS Delete Target")
        if not apply:
            return
        _lifecycle_require_safe_apply(target)
        if saas_lifecycle_utils.has_active_subscription(target):
            raise click.UsageError("Delete refused because an active subscription exists.")
        if not saas_lifecycle_utils.is_paused(target):
            raise click.UsageError("Delete refused because the sub-account is not paused.")
        typed_name = click.prompt("Type the exact location name to continue")
        if typed_name != str(target.get("name") or ""):
            raise click.UsageError("Typed location name did not match exactly.")
        if not click.confirm("Approve permanent deletion of this one sub-account?", default=False):
            raise click.Abort()
        api.delete(
            f"/locations/{location_id}",
            params={"deleteTwilioAccount": twilio},
            version="v3",
            agency=True,
        )
        try:
            api.get(f"/locations/{location_id}", version="v3", agency=True)
        except requests.exceptions.HTTPError as exc:
            if getattr(exc.response, "status_code", None) != 404:
                raise
        else:
            raise RuntimeError("Post-write verification still found the deleted location.")
        _lifecycle_emit(ctx, {"verified": True, "locationId": location_id, "reason": reason.strip()}, "Delete Verified")
    except Exception as exc:
        _handle_error(exc)


@saas.command("plans")
@click.option("--company-id", required=True, help="Company/Agency ID")
@click.pass_context
def saas_plans(ctx, company_id):
    """List an agency's SaaS plans."""
    try:
        data = api.get(f"/saas/agency-plans/{company_id}")
        _output(ctx, data, "SaaS Plans")
    except Exception as e:
        _handle_error(e)


@saas.command("plan")
@click.argument("plan_id")
@click.option("--company-id", required=True, help="Company/Agency ID")
@click.pass_context
def saas_plan(ctx, plan_id, company_id):
    """Get one agency SaaS plan by ID."""
    try:
        data = api.get(
            f"/saas/saas-plan/{plan_id}",
            params={"companyId": company_id},
        )
        _output(ctx, data, "SaaS Plan")
    except Exception as e:
        _handle_error(e)


# ===========================================================================
# Entry point
# ===========================================================================

def main():
    cli(obj={})


if __name__ == "__main__":
    main()
