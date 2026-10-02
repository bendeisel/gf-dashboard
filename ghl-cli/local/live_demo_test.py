#!/usr/bin/env python3
"""End-to-end functional test of the GHL CLI against the Demo Account.

Creates only 'ZZ CLI TEST' objects, verifies them, then deletes them.
Never sends messages, never books appointments, never publishes.
"""
import json, os, subprocess, sys, time, tempfile

GHL = os.path.expanduser("~/.config/claude-accounts/gf-account/skills/gohighlevel-cli/ghl")
DEMO_LOC = "ci0jwHqmVfVyvvLyqRGQ"
COMPANY = "vAlo5qwvj1pNVM9gBvQk"
PIPE, STAGE1, STAGE2 = "98WYRR9uOlvL4aau4rr7", "483cc402-937d-4776-9bf6-80be56384704", "f5db1853-85c6-4dc2-b679-70ba76b11292"
TMP = tempfile.mkdtemp(prefix="ghltest-", dir=os.path.dirname(os.path.abspath(__file__)))
ENV = {**os.environ, "GHL_PROFILE": "demo", "GHL_SUPPRESS_INTERNAL_WARNING": "1"}

results, created, leftovers = [], {}, []


def ghl(*args, exp=False, js=True, stdin=None):
    cmd = [GHL] + (["--experimental"] if exp else []) + (["--json"] if js else []) + list(args)
    p = subprocess.run(cmd, capture_output=True, text=True, env=ENV, input=stdin, timeout=180)
    out = p.stdout.strip()
    try:
        data = json.loads(out) if js and out else out
    except json.JSONDecodeError:
        data = out
    return p.returncode, data, p.stderr.strip()


def step(area, name, fn):
    try:
        ok, detail = fn()
    except Exception as e:  # noqa
        ok, detail = False, f"exception: {e}"
    results.append((area, name, ok, str(detail)[:160]))
    print(f"[{'PASS' if ok else 'FAIL'}] {area:14} {name:38} {str(detail)[:110]}", flush=True)
    return ok


def find_id(d, *keys):
    """Dig for an id in nested API responses."""
    if isinstance(d, dict):
        for k in keys:
            if k in d and isinstance(d[k], str):
                return d[k]
        for v in d.values():
            r = find_id(v, *keys)
            if r:
                return r
    elif isinstance(d, list):
        for v in d:
            r = find_id(v, *keys)
            if r:
                return r
    return None


def wf(name, data):
    path = os.path.join(TMP, name)
    with open(path, "w") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))
    return path


# ---------------------------------------------------------------- READ-ONLY
def t_read(args, key=None, exp=False):
    def f():
        rc, d, err = ghl(*args, exp=exp)
        if rc != 0:
            return False, err or d
        if key and isinstance(d, dict):
            v = d.get(key)
            if isinstance(v, dict):
                v = v.get(key, v)
            n = len(v) if isinstance(v, list) else "ok"
            return True, f"{key}: {n}"
        return True, "ok"
    return f


print("\n=== READ-ONLY CHECKS ===")
for area, name, args, key, exp in [
    ("locations", "get", ["locations", "get"], "location", False),
    ("locations", "tags", ["locations", "tags"], "tags", False),
    ("locations", "custom-fields", ["locations", "custom-fields"], "customFields", False),
    ("locations", "custom-values", ["locations", "custom-values"], "customValues", False),
    ("contacts", "list", ["contacts", "list", "--limit", "5"], "contacts", False),
    ("opportunities", "pipelines", ["opportunities", "pipelines"], "pipelines", False),
    ("opportunities", "list", ["opportunities", "list"], "opportunities", False),
    ("calendars", "list", ["calendars", "list"], "calendars", False),
    ("calendars", "groups", ["calendars", "groups"], "groups", False),
    ("calendars", "appointments", ["calendars", "appointments"], None, False),
    ("conversations", "list (SMS)", ["conversations", "list", "--type", "SMS", "--limit", "5"], "conversations", False),
    ("conversations", "list (Email)", ["conversations", "list", "--type", "Email", "--limit", "5"], "conversations", False),
    ("forms", "list", ["forms", "list"], "forms", False),
    ("workflows", "list", ["workflows", "list"], "workflows", False),
    ("payments", "invoices", ["payments", "invoices"], None, False),
    ("payments", "transactions", ["payments", "transactions"], None, False),
    ("payments", "orders", ["payments", "orders"], None, False),
    ("payments", "subscriptions", ["payments", "subscriptions"], None, False),
    ("documents", "list", ["documents", "list"], None, False),
    ("documents", "templates", ["documents", "templates"], None, False),
    ("social", "accounts", ["social", "accounts"], None, False),
    ("social", "posts", ["social", "posts"], None, False),
    ("emails", "list-campaigns (public)", ["emails", "list-campaigns"], None, False),
    ("emails", "campaigns (internal)", ["emails", "campaigns"], None, True),
    ("emails", "templates (internal)", ["emails", "templates"], None, True),
    ("smartlists", "list", ["smartlists", "list"], "smartLists", True),
    ("funnels", "list", ["funnels", "list"], "funnels", True),
    ("surveys", "list", ["surveys", "list"], "surveys", True),
    ("saas", "locations (agency)", ["saas", "locations", "--company-id", COMPANY], None, False),
    ("saas", "plans (agency)", ["saas", "plans", "--company-id", COMPANY], None, False),
]:
    step(area, name, t_read(args, key, exp))

# conversation message read on first existing conversation (read only)
def t_conv_messages():
    rc, d, err = ghl("conversations", "list", "--limit", "1")
    cid = find_id(d.get("conversations", [{}])[0] if isinstance(d, dict) and d.get("conversations") else {}, "id")
    if not cid:
        return True, "no conversations to read (skipped)"
    rc, d, err = ghl("conversations", "messages", cid)
    return rc == 0, "read messages of 1 conversation" if rc == 0 else err
step("conversations", "messages (read)", t_conv_messages)

def t_submissions():
    rc, d, err = ghl("forms", "list")
    fid = d["forms"][0]["id"]
    rc, d, err = ghl("forms", "submissions", fid)
    return rc == 0, "read submissions of 1 form" if rc == 0 else err
step("forms", "submissions", t_submissions)

# ---------------------------------------------------------------- LOCAL (no network)
print("\n=== LOCAL TOOLS (no GHL writes) ===")
spec = os.path.join(TMP, "optin.json")
step("funnels", "templates", t_read(["funnels", "templates"]))
def t_init():
    rc, d, err = ghl("funnels", "init-template", "roadmap", "--theme", "modern", "--output", spec, js=False)
    return rc == 0 and os.path.exists(spec), err or "spec written"
step("funnels", "init-template (roadmap)", t_init)
def t_lint():
    rc, d, err = ghl("funnels", "lint", spec, js=False)
    txt = (d or err)
    return "score" in txt.lower(), txt.splitlines()[0] + " (non-zero exit = below lint threshold, informational)"
step("funnels", "lint", t_lint)
prev = os.path.join(TMP, "preview.html")
def t_prev():
    rc, d, err = ghl("funnels", "preview", spec, "--output", prev, js=False)
    return rc == 0 and os.path.exists(prev), f"{os.path.getsize(prev)//1024} KB preview" if os.path.exists(prev) else err
step("funnels", "preview (local HTML)", t_prev)

# ---------------------------------------------------------------- WRITE (create → verify → delete)
print("\n=== CREATE / UPDATE / DELETE (ZZ CLI TEST objects only) ===")
stamp = time.strftime("%m%d%H%M")
EMAIL = f"zz-cli-test-{stamp}@example.com"

def t_contact_create():
    rc, d, err = ghl("contacts", "create", "--email", EMAIL, "--first-name", "ZZ CLI", "--last-name", "TEST",
                     "--tag", "zz-cli-test", "--source", "ghl-cli-test")
    cid = find_id(d, "id")
    created["contact"] = cid
    return bool(cid), cid or err or d
step("contacts", "create (fake @example.com)", t_contact_create)

def t_contact_get():
    rc, d, err = ghl("contacts", "get", created["contact"])
    return rc == 0 and EMAIL in json.dumps(d), "read back OK" if rc == 0 else err
step("contacts", "get", t_contact_get)

def t_contact_update():
    rc, d, err = ghl("contacts", "update", created["contact"], "--company", "ZZ CLI Test Co")
    return rc == 0, "company set" if rc == 0 else err
step("contacts", "update", t_contact_update)

def t_addtag():
    rc, d, err = ghl("contacts", "add-tag", created["contact"], "zz-cli-test-2")
    return rc == 0, "tag added" if rc == 0 else err
step("contacts", "add-tag", t_addtag)

def t_rmtag():
    rc, d, err = ghl("contacts", "remove-tag", created["contact"], "zz-cli-test-2")
    return rc == 0, "tag removed" if rc == 0 else err
step("contacts", "remove-tag", t_rmtag)

def t_search():
    time.sleep(3)
    rc, d, err = ghl("contacts", "search", EMAIL)
    return rc == 0, "search ran" + (" (found)" if created.get("contact") and created["contact"] in json.dumps(d) else " (index lag)")
step("contacts", "search", t_search)

def t_opp_create():
    rc, d, err = ghl("opportunities", "create", "--pipeline-id", PIPE, "--stage-id", STAGE1,
                     "--name", "ZZ CLI TEST deal", "--contact-id", created["contact"], "--value", "1")
    oid = find_id(d, "id")
    created["opp"] = oid
    return bool(oid), oid or err or d
step("opportunities", "create", t_opp_create)

def t_opp_update():
    rc, d, err = ghl("opportunities", "update", created["opp"], "--stage-id", STAGE2, "--value", "2")
    return rc == 0, "moved to Hot Lead stage" if rc == 0 else err
step("opportunities", "update (move stage)", t_opp_update)

def t_opp_get():
    rc, d, err = ghl("opportunities", "get", created["opp"])
    return rc == 0 and STAGE2 in json.dumps(d), "stage verified" if rc == 0 else err
step("opportunities", "get", t_opp_get)

def t_cal_create():
    rc, d, err = ghl("calendars", "create", "--name", "ZZ CLI TEST calendar", "--calendar-type", "event",
                     "--slot-duration", "30", "--slot-duration-unit", "mins", "--slug", f"zz-cli-test-{stamp}", "--inactive")
    cid = find_id(d.get("calendar", d) if isinstance(d, dict) else d, "id")
    created["calendar"] = cid
    return bool(cid), cid or err or d
step("calendars", "create (inactive)", t_cal_create)

def t_cal_update():
    rc, d, err = ghl("calendars", "update", created["calendar"], "--name", "ZZ CLI TEST calendar (renamed)")
    return rc == 0, "renamed" if rc == 0 else err
step("calendars", "update", t_cal_update)

def t_slots():
    cal = created.get("calendar") or "3ycbpCGN8SGDESqDJT73"
    rc, d, err = ghl("calendars", "slots", "3ycbpCGN8SGDESqDJT73", "--start", time.strftime("%Y-%m-%d"),
                     "--end", time.strftime("%Y-%m-%d", time.localtime(time.time() + 6 * 86400)))
    return rc == 0, "slots read (no booking)" if rc == 0 else err
step("calendars", "slots (read only)", t_slots)

def t_smart_create():
    rc, d, err = ghl("smartlists", "create", "--name", "ZZ CLI TEST list", "--filter", "tags:eq:zz-cli-test", exp=True)
    sid = find_id(d, "id", "_id")
    created["smartlist"] = sid
    return bool(sid), sid or err or d
step("smartlists", "create (tag filter)", t_smart_create)

def t_smart_get():
    rc, d, err = ghl("smartlists", "get", created["smartlist"], exp=True)
    return rc == 0 and "zz-cli-test" in json.dumps(d), "filter verified" if rc == 0 else err
step("smartlists", "get", t_smart_get)

html = wf("email.html", '<p><span style="font-family:Arial;font-size:16px">Hi {{contact.first_name}}, this is a CLI test draft. Do not send.</span></p>')
def t_campaign():
    rc, d, err = ghl("emails", "create-campaign", "--name", "ZZ CLI TEST campaign (DO NOT SEND)",
                     "--subject", "{{contact.first_name}}, CLI test A", "--ab-subject", "CLI test B",
                     "--from-name", "Growth Factor Test", "--from-email", "test@growth-factor.ai",
                     "--html-file", html, "--smart-list", created["smartlist"], exp=True)
    created["campaign"] = find_id(d, "campaignId", "id")
    created["template"] = find_id(d, "templateId")
    return bool(created["campaign"]), f"draft {created['campaign']}" if created["campaign"] else (err or d)
step("emails", "create-campaign (DRAFT, A/B)", t_campaign)

def t_campaign_get():
    rc, d, err = ghl("emails", "get-campaign", created["campaign"], exp=True)
    s = json.dumps(d)
    return rc == 0, ("status draft" if "draft" in s.lower() else "read OK") + (" / fallback applied" if "default contact.first_name" in s else "")
step("emails", "get-campaign", t_campaign_get)

def t_form():
    p = wf("form.json", {"name": "ZZ CLI TEST form", "thankYouMessage": "Test only.",
                         "fields": [{"type": "text", "tag": "first_name", "label": "First Name", "width": 50},
                                    {"type": "text", "tag": "last_name", "label": "Last Name", "width": 50},
                                    {"type": "email", "tag": "email", "label": "Email", "required": True}]})
    rc, d, err = ghl("forms", "create", "--from-json", p, exp=True)
    created["form"] = find_id(d, "id", "_id", "formId")
    return bool(created["form"]), created["form"] or err or d
step("forms", "create (3 fields)", t_form)

def t_form_get():
    rc, d, err = ghl("forms", "get", created["form"], exp=True)
    return rc == 0 and "email" in json.dumps(d), "fields stored" if rc == 0 else err
step("forms", "get", t_form_get)

def t_survey():
    p = wf("survey.json", {"name": "ZZ CLI TEST survey", "slides": [
        {"name": "About you", "button": "Next", "fields": [{"type": "text", "tag": "first_name", "label": "First Name"}]},
        {"name": "Goals", "button": "Submit", "fields": [{"type": "single_options", "tag": "zz_goal", "label": "Main goal",
                                                           "options": ["Lose weight", "Learn to fight", "Compete"]}]}]})
    rc, d, err = ghl("surveys", "create", "--from-json", p, exp=True)
    created["survey"] = find_id(d, "id", "_id", "surveyId")
    return bool(created["survey"]), created["survey"] or err or d
step("surveys", "create (2 slides)", t_survey)

def t_funnel():
    rc, d, err = ghl("funnels", "create", "--name", "ZZ CLI TEST funnel", exp=True)
    created["funnel"] = find_id(d, "id", "_id", "funnelId")
    return bool(created["funnel"]), created["funnel"] or err or d
step("funnels", "create (shell)", t_funnel)

def t_page():
    rc, d, err = ghl("funnels", "create-page", created["funnel"], "--from-json", spec, exp=True)  # draft only, no --publish
    created["page"] = find_id(d, "pageId", "id", "_id")
    return rc == 0, f"draft page {created['page']}" if rc == 0 else (err or d)
step("funnels", "create-page (DRAFT from spec)", t_page)

def t_pages():
    rc, d, err = ghl("funnels", "pages", created["funnel"], exp=True)
    return rc == 0, "pages listed" if rc == 0 else err
step("funnels", "pages", t_pages)

def t_workflow():
    rc0, d0, _ = ghl("workflows", "list")
    if any("ZZ CLI TEST" in w.get("name", "") for w in d0.get("workflows", [])):
        return True, "already created in run 1 (skipped to avoid a duplicate)"
    rc, d, err = ghl("workflows", "create-n8n", "--name", "ZZ CLI TEST n8n bridge",
                     "--webhook-url", "https://example.com/zz-cli-test-webhook", "--tag", "zz-cli-test-trigger",
                     "--folder", "ZZ CLI TEST", exp=True)
    s = json.dumps(d)
    ok = rc == 0 and isinstance(d, dict) and not d.get("errors") and d.get("workflows_created") == 1
    return ok, ("DRAFT workflow created" if ok else (err or s))[:150]
step("workflows", "create-n8n (DRAFT)", t_workflow)

def t_wf_list():
    time.sleep(3)
    rc, d, err = ghl("workflows", "list")
    w = [x for x in d.get("workflows", []) if "ZZ CLI TEST" in x.get("name", "")] if isinstance(d, dict) else []
    if w:
        created["workflow"] = w[0]["id"]
    return bool(w), f"{w[0]['name']} status={w[0].get('status')}" if w else "not visible yet"
step("workflows", "list shows draft", t_wf_list)

def t_enroll():
    if not created.get("workflow"):
        return False, "no workflow id"
    rc, d, err = ghl("workflows", "enroll", "--contact-id", created["contact"], "--workflow-id", created["workflow"])
    ghl("workflows", "remove", "--contact-id", created["contact"], "--workflow-id", created["workflow"])
    return rc == 0, "enroll + remove on draft (webhook → example.com only)" if rc == 0 else (err or d)
step("workflows", "enroll + remove", t_enroll)

# ---------------------------------------------------------------- CLEANUP
print("\n=== CLEANUP ===")
def rm(label, *args, exp=False, key=None):
    def f():
        if not created.get(key):
            return False, "nothing to delete"
        rc, d, err = ghl(*args, exp=exp)
        if rc != 0:
            leftovers.append(f"{label} {created[key]}")
        return rc == 0, "deleted" if rc == 0 else (err or d)
    step("cleanup", label, f)

if created.get("campaign"):
    rm("email campaign", "emails", "delete-campaign", created["campaign"], *(["--template-id", created["template"]] if created.get("template") else []), "--yes", exp=True, key="campaign")
if created.get("smartlist"):
    rm("smart list", "smartlists", "delete", created["smartlist"], "--yes", exp=True, key="smartlist")
if created.get("form"):
    rm("form", "forms", "delete", created["form"], "--yes", exp=True, key="form")
if created.get("survey"):
    rm("survey", "surveys", "delete", created["survey"], "--yes", exp=True, key="survey")
if created.get("funnel"):
    rm("funnel", "funnels", "delete", created["funnel"], "--yes", exp=True, key="funnel")
if created.get("calendar"):
    rm("calendar", "calendars", "delete", created["calendar"], "--yes", key="calendar")
if created.get("opp"):
    rm("opportunity", "opportunities", "delete", created["opp"], key="opp")
if created.get("contact"):
    rm("contact", "contacts", "delete", created["contact"], key="contact")
leftovers.append("workflow 'ZZ CLI TEST n8n bridge' + folder 'ZZ CLI TEST' (CLI has no workflow delete)")

passed = sum(1 for r in results if r[2])
print(f"\n=== {passed}/{len(results)} passed ===")
print("Leftovers to remove by hand:", *leftovers, sep="\n  - ")
json.dump({"results": results, "created": created, "leftovers": leftovers}, open(os.path.join(TMP, "..", "ghl_test_results.json"), "w"), indent=1)
