"""Contract-template builder, client, and CLI safety tests."""
from __future__ import annotations

import json
import os
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

from click.testing import CliRunner

from cli_anything.gohighlevel.gohighlevel_cli import cli
from cli_anything.gohighlevel.utils.contract_template_builder import (
    ASSIGNED_CONTACT_ID,
    ASSIGNED_SENDER_ID,
    ContractTemplateError,
    DYNAMIC_SIGNING_ORDER,
    add_field,
    apply_template_input,
    build_field,
    ensure_default_signer_fields,
    make_letter_page,
    prepare_template_export,
    set_completed_redirect,
)
from cli_anything.gohighlevel.utils.ghl_internal_client import InternalGHLClient


def native_template():
    return {
        "id": "template-1",
        "_id": "mongo-1",
        "name": "Agreement",
        "locationId": "loc-1",
        "pages": [make_letter_page()],
        "groups": [],
        "recipients": [{"id": "contact-1", "entityName": "contacts", "isPrimary": True}],
        "futureGhlProperty": {"keep": [1, 2, 3]},
    }


class ContractBuilderTests(unittest.TestCase):
    @staticmethod
    def _party_fields(document, recipient):
        return [
            field for field in document["pages"][-1]["children"]
            if field.get("component", {}).get("options", {}).get("recipient") == recipient
        ]

    def test_native_field_shapes_match_current_builder(self):
        document = native_template()
        cases = {
            "name": ("TextField", 1, 165, 26),
            "signature": ("Signature", 2, 190, 68),
            "date": ("DateField", 1, 131, 26),
            "initials": ("InitialsField", 1, 130, 50),
            "checkbox": ("Checkbox", 1, 25, 25),
        }
        for kind, expected in cases.items():
            with self.subTest(kind=kind):
                field = build_field(kind, pages=document["pages"], document=document)
                dims = field["responsiveStyles"]["large"]["dimensions"]
                self.assertEqual((field["type"], field["version"], dims["width"], dims["height"]), expected)
                self.assertEqual(field["component"]["options"]["recipient"], "contact-1")
        name = build_field("name", pages=document["pages"], document=document)
        signature = build_field("signature", pages=document["pages"], document=document)
        date = build_field("date", pages=document["pages"], document=document)
        self.assertEqual(name["component"]["options"]["placeholder"], "Full name")
        self.assertTrue(signature["component"]["options"]["showName"])
        self.assertEqual(date["component"]["options"]["dateFormat"], "yyyy-MM-dd")

    def test_empty_template_defaults_fields_to_assigned_contact(self):
        document = {"pages": [make_letter_page()], "recipients": []}
        field = build_field("signature", pages=document["pages"], document=document)
        options = field["component"]["options"]
        self.assertEqual((options["recipient"], options["entityName"]), ("assignedContact", "contacts"))

    def test_compact_fields_get_unique_ids_and_fillable_metadata(self):
        document = add_field(native_template(), {"type": "name", "label": "Legal name"})
        document = add_field(document, {"type": "text"})
        document = add_field(document, {"type": "signature"})
        children = document["pages"][0]["children"]
        ids = [child["component"]["options"]["fieldId"] for child in children]
        self.assertEqual(ids, ["text_field_1", "text_field_2", "signature1"])
        self.assertEqual([field["type"] for field in document["fillableFields"]], ["TextField", "TextField"])
        self.assertEqual(children[0]["component"]["options"]["placeholder"], "Legal name")
        self.assertEqual(document["fillableFields"][0]["value"], "")
        self.assertFalse(document["fillableFields"][0]["hasCompleted"])

    def test_update_preserves_nested_data_and_uses_builder_root_whitelist(self):
        original = native_template()
        original.update({
            "deleted": False,
            "type": "proposal",
            "version": 2,
            "tags": [],
            "versionHistory": [],
        })
        original["pages"][0]["futureNestedProperty"] = {"keep": True}
        original["fillableFields"] = [{"type": "FutureField", "future": True}]
        result = apply_template_input(original, {"name": "Revised"}, "loc-2")
        self.assertNotIn("futureGhlProperty", result)
        self.assertEqual(result["pages"][0]["futureNestedProperty"], {"keep": True})
        self.assertEqual(result["fillableFields"], [{"type": "FutureField", "future": True}])
        self.assertNotIn("id", result)
        self.assertNotIn("_id", result)
        for key in ("deleted", "type", "version", "tags", "versionHistory"):
            self.assertNotIn(key, result)
        self.assertEqual(result["locationId"], "loc-2")
        self.assertEqual(original["name"], "Agreement")

    def test_compact_create_makes_a_letter_page(self):
        result = apply_template_input(
            {"name": "Blank", "pages": []},
            {"fields": [{"type": "signature", "top": 800, "left": 500}]},
            "loc-1",
        )
        page = result["pages"][0]
        self.assertEqual(page["component"]["options"]["pageDimensions"]["dimensions"], {"width": 816, "height": 1056})
        self.assertEqual(page["children"][0]["type"], "Signature")

    def test_default_signer_fields_are_added_to_final_page_idempotently(self):
        document = native_template()
        document["pages"].append(make_letter_page())
        first = ensure_default_signer_fields(document)
        second = ensure_default_signer_fields(first)

        self.assertEqual(first, second)
        self.assertEqual(first["pages"][0]["children"], [])
        fields = first["pages"][-1]["children"]
        self.assertEqual(
            [field["type"] for field in fields],
            ["DateField", "Signature", "TextField", "DateField", "Signature"],
        )
        self.assertEqual(
            [field["component"]["options"]["recipient"] for field in fields],
            [
                ASSIGNED_SENDER_ID, ASSIGNED_SENDER_ID,
                ASSIGNED_CONTACT_ID, ASSIGNED_CONTACT_ID, ASSIGNED_CONTACT_ID,
            ],
        )
        self.assertTrue(all(field["component"]["options"]["required"] for field in fields))
        self.assertEqual(
            [field["type"] for field in first["fillableFields"]],
            ["DateField", "TextField", "DateField"],
        )
        self.assertEqual(
            [field["recipient"] for field in first["fillableFields"]],
            [ASSIGNED_SENDER_ID, ASSIGNED_CONTACT_ID, ASSIGNED_CONTACT_ID],
        )
        self.assertEqual(
            [field["entityType"] for field in first["fillableFields"]],
            ["users", "contacts", "contacts"],
        )
        tops = [field["responsiveStyles"]["large"]["position"]["top"] for field in fields]
        self.assertEqual(tops, [650, 692, 790, 832, 874])
        dimensions = [field["responsiveStyles"]["large"]["dimensions"] for field in fields]
        for current, following, dimension in zip(tops, tops[1:], dimensions):
            self.assertLessEqual(current + dimension["height"], following)

    def test_dynamic_recipients_sign_contractor_first_then_sender(self):
        self.assertEqual(DYNAMIC_SIGNING_ORDER[ASSIGNED_CONTACT_ID], 1)
        self.assertEqual(DYNAMIC_SIGNING_ORDER[ASSIGNED_SENDER_ID], 2)

    def test_default_signer_fields_keep_existing_name_and_add_only_missing_fields(self):
        document = add_field(native_template(), {
            "type": "name", "fieldId": "legal_name", "top": 100,
            "recipient": ASSIGNED_CONTACT_ID, "entityName": "contacts",
            "required": False,
        })
        result = ensure_default_signer_fields(document)
        contractor_fields = self._party_fields(result, ASSIGNED_CONTACT_ID)
        self.assertEqual(
            [field["type"] for field in contractor_fields],
            ["TextField", "DateField", "Signature"],
        )
        self.assertEqual(contractor_fields[0]["component"]["options"]["fieldId"], "legal_name")
        self.assertTrue(contractor_fields[0]["component"]["options"]["required"])
        self.assertEqual(
            [field["type"] for field in self._party_fields(result, ASSIGNED_SENDER_ID)],
            ["DateField", "Signature"],
        )

    def test_user_assigned_fields_do_not_replace_signer_defaults(self):
        document = add_field(native_template(), {
            "type": "signature", "recipient": "user-1", "entityName": "users",
        })
        result = ensure_default_signer_fields(document)
        signatures = [
            field for field in result["pages"][-1]["children"]
            if field["type"] == "Signature"
        ]
        self.assertEqual(len(signatures), 3)
        assignments = {
            (field["component"]["options"]["recipient"], field["component"]["options"]["entityName"])
            for field in signatures
        }
        self.assertIn((ASSIGNED_CONTACT_ID, "contacts"), assignments)
        self.assertIn((ASSIGNED_SENDER_ID, "users"), assignments)

    def test_unassigned_native_defaults_are_repaired_without_duplicates(self):
        document = native_template()
        for kind in ("name", "date", "signature"):
            field = build_field(kind, pages=document["pages"], document=document)
            field["component"]["options"]["recipient"] = None
            field["component"]["options"]["entityName"] = None
            field["component"]["options"]["required"] = False
            document["pages"][-1]["children"].append(field)

        first = ensure_default_signer_fields(document)
        second = ensure_default_signer_fields(first)
        self.assertEqual(first, second)
        fields = first["pages"][-1]["children"]
        self.assertEqual(len(fields), 5)
        for field in self._party_fields(first, ASSIGNED_CONTACT_ID):
            options = field["component"]["options"]
            self.assertEqual(options["recipient"], ASSIGNED_CONTACT_ID)
            self.assertEqual(options["entityName"], "contacts")
            self.assertTrue(options["required"])
        self.assertEqual(len(self._party_fields(first, ASSIGNED_CONTACT_ID)), 3)
        self.assertEqual(len(self._party_fields(first, ASSIGNED_SENDER_ID)), 2)

    def test_contact_and_sender_fields_do_not_satisfy_each_other(self):
        document = native_template()
        document = add_field(document, {
            "type": "date", "recipient": ASSIGNED_CONTACT_ID,
            "entityName": "contacts", "fieldId": "contact_date",
            "required": False, "top": 111,
        })
        document = add_field(document, {
            "type": "signature", "recipient": ASSIGNED_SENDER_ID,
            "entityName": "users", "fieldId": "sender_signature",
            "required": False, "top": 222,
        })
        result = ensure_default_signer_fields(document)
        contractor = self._party_fields(result, ASSIGNED_CONTACT_ID)
        sender = self._party_fields(result, ASSIGNED_SENDER_ID)
        self.assertEqual(
            [field["type"] for field in contractor],
            ["DateField", "TextField", "Signature"],
        )
        self.assertEqual(
            [field["type"] for field in sender],
            ["Signature", "DateField"],
        )
        self.assertEqual(contractor[0]["component"]["options"]["fieldId"], "contact_date")
        self.assertEqual(contractor[0]["responsiveStyles"]["large"]["position"]["top"], 111)
        self.assertTrue(contractor[0]["component"]["options"]["required"])
        self.assertEqual(sender[0]["component"]["options"]["fieldId"], "sender_signature")
        self.assertEqual(sender[0]["responsiveStyles"]["large"]["position"]["top"], 222)
        self.assertTrue(sender[0]["component"]["options"]["required"])

    def test_update_normalizes_nested_builder_values(self):
        original = native_template()
        original.update({
            "timezone": None,
            "paymentInfo": {"invoiceType": "one-time", "_id": "metadata"},
            "grandTotal": {"currency": "USD", "amount": 0, "_id": "metadata"},
            "notificationSettings": {"value": "ui-only", "sender": {"name": "Jay"}},
            "redirectSettings": {"documentRedirectUrl": "example.com/thanks"},
            "roles": None,
            "recipients": [
                {"id": "assignedContact", "entityName": "contacts"},
                {"id": "role-1", "entityName": "role"},
                {"id": "contact-1", "entityName": "contacts"},
            ],
        })
        with patch.dict(os.environ, {"GHL_CONTRACT_TIMEZONE": "America/Los_Angeles"}):
            result = apply_template_input(original, {"name": "Revised"}, "loc-1")
        self.assertEqual(result["timezone"]["zone"], "America/Los_Angeles")
        self.assertTrue(result["timezone"]["abbreviation"])
        self.assertEqual(result["paymentInfo"], {"invoiceType": "one-time"})
        self.assertEqual(result["grandTotal"], {"currency": "USD", "amount": 0})
        self.assertEqual(result["notificationSettings"], {"sender": {"name": "Jay"}})
        self.assertEqual(result["recipients"], [{"id": "contact-1", "entityName": "contacts"}])
        self.assertEqual(result["roles"], [])
        self.assertEqual(result["redirectSettings"]["documentRedirectUrl"], "https://example.com/thanks")

    def test_completed_redirect_uses_current_builder_schema(self):
        result = set_completed_redirect(
            native_template(), "leadgenjay.com/team-buildout/welcome-call", "existingTab"
        )
        self.assertEqual(result["redirectSettings"], {
            "enableDocumentRedirectUrl": True,
            "documentRedirectUrl": "https://leadgenjay.com/team-buildout/welcome-call",
            "documentRedirectType": "existingTab",
        })

    def test_completed_redirect_rejects_invalid_url_and_target(self):
        with self.assertRaisesRegex(ContractTemplateError, "valid HTTP"):
            set_completed_redirect(native_template(), "not a url")
        with self.assertRaisesRegex(ContractTemplateError, "valid HTTP"):
            set_completed_redirect(native_template(), "javascript:alert(1)")
        with self.assertRaisesRegex(ContractTemplateError, "valid HTTP"):
            set_completed_redirect(native_template(), "ftp://example.com/file")
        with self.assertRaisesRegex(ContractTemplateError, "existingTab"):
            set_completed_redirect(native_template(), "https://example.com", "popup")

    def test_export_makes_disabled_redirect_settings_explicit(self):
        exported = prepare_template_export(native_template())
        self.assertEqual(exported["redirectSettings"], {
            "enableDocumentRedirectUrl": False,
            "documentRedirectUrl": "",
            "documentRedirectType": "newTab",
        })
        self.assertNotIn("redirectSettings", native_template())

    def test_timezone_override_wins_and_invalid_zone_fails(self):
        original = native_template()
        original["timezone"] = {"zone": "UTC", "abbreviation": "UTC"}
        with patch.dict(os.environ, {"GHL_CONTRACT_TIMEZONE": "America/New_York"}):
            result = apply_template_input(original, {"name": "Revised"}, "loc-1")
        self.assertEqual(result["timezone"]["zone"], "America/New_York")
        with patch.dict(os.environ, {"GHL_CONTRACT_TIMEZONE": "not/a-zone"}):
            with self.assertRaisesRegex(ContractTemplateError, "valid IANA timezone"):
                apply_template_input(original, {"name": "Revised"}, "loc-1")

    def test_product_list_page_edits_are_blocked(self):
        original = native_template()
        original["pages"][0]["children"].append({
            "type": "ProductList", "version": 2, "id": "products-1",
            "children": [], "component": {"options": {"lineItems": []}},
        })
        replacement_pages = deepcopy(original["pages"])
        replacement_pages[0]["children"] = []
        with self.assertRaisesRegex(ContractTemplateError, "ProductList page edits"):
            apply_template_input(original, {"pages": replacement_pages}, "loc-1")

    def test_invalid_page_and_type_are_rejected(self):
        with self.assertRaises(ContractTemplateError):
            add_field(native_template(), {"type": "signature", "page": 2})
        with self.assertRaises(ContractTemplateError):
            add_field(native_template(), {"type": "phone"})


class ContractClientTests(unittest.TestCase):
    def setUp(self):
        self.client = InternalGHLClient(Mock(), "loc/a")

    def test_no_iam_token_still_calls_the_service_on_token_id(self):
        # Measured against the live service on 2026-08-24: a template GET with
        # token-id and NO Authorization header returns 200 and the full
        # template. This used to raise before making any request, which is why
        # the requirement went untested for as long as it did.
        self.client.request = Mock(return_value={"id": "template-1"})
        with patch.dict(os.environ, {"GHL_IAM_TOKEN": ""}, clear=False):
            self.client.get_contract_template("template-1")
        headers = self.client.request.call_args.kwargs["extra_headers"]
        self.assertNotIn("Authorization", headers)
        self.assertEqual(headers["Version"], "2021-07-28")

    def test_an_explicit_iam_token_is_still_passed_through(self):
        self.client.request = Mock(return_value={"id": "template-1"})
        with patch.dict(os.environ, {"GHL_IAM_TOKEN": "Bearer iam-secret"}, clear=False):
            self.client.get_contract_template("template-1")
        headers = self.client.request.call_args.kwargs["extra_headers"]
        self.assertEqual(headers["Authorization"], "Bearer iam-secret")

    def test_401_with_a_token_set_says_to_drop_it_rather_than_refresh_it(self):
        # The service resolves a bearer when it gets one, so a stale token is
        # worse than none. Sending someone hunting for a fresh one is the wrong
        # advice when unsetting it is the fix.
        self.client.request = Mock(return_value={"_error": True, "code": 401, "message": "old"})
        with patch.dict(os.environ, {"GHL_IAM_TOKEN": "stale"}, clear=False):
            result = self.client.get_contract_template("template-1")
        self.assertIn("unset", result["message"].lower())

    def test_named_methods_use_dual_auth_service_routes(self):
        self.client.request = Mock(return_value={"id": "template-1"})
        with patch.dict(os.environ, {"GHL_IAM_TOKEN": "iam-secret"}, clear=False):
            self.client.create_contract_template("Agreement")
            self.client.get_contract_template("template 1")
            self.client.update_contract_template("template-1", {"name": "New"})
        create, get, update = self.client.request.call_args_list
        self.assertEqual(create.args[:2], ("POST", "https://services.leadconnectorhq.com/proposals/templates"))
        self.assertEqual(create.args[2]["isPublicDocument"], False)
        self.assertEqual(get.args[:2], ("GET", "https://services.leadconnectorhq.com/proposals/templates/template%201?locationId=loc%2Fa"))
        self.assertEqual(update.args[:2], ("PUT", "https://services.leadconnectorhq.com/proposals/templates/template-1"))
        for call in (create, get, update):
            self.assertEqual(call.kwargs["extra_headers"]["Authorization"], "Bearer iam-secret")
            self.assertEqual(call.kwargs["extra_headers"]["Version"], "2021-07-28")

    def test_proposal_401_with_no_token_set_still_guides(self):
        self.client.request = Mock(return_value={"_error": True, "code": 401, "message": "old"})
        with patch.dict(os.environ, {"GHL_IAM_TOKEN": ""}, clear=False):
            result = self.client.get_contract_template("template-1")
        self.assertIn("GHL_IAM_TOKEN", result["message"])


class ContractCliTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def _client_with_persisted_write(self, before):
        client = Mock()
        writes = []

        def update(template_id, payload):
            writes.append(deepcopy(payload))
            return {"ok": True}

        def get(template_id):
            if writes:
                return {**deepcopy(writes[-1]), "id": template_id}
            return deepcopy(before)

        client.update_contract_template.side_effect = update
        client.get_contract_template.side_effect = get
        return client, writes

    def test_authoring_requires_experimental_flag(self):
        result = self.runner.invoke(cli, ["--location-id", "loc-1", "documents", "get-template", "template-1"])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("requires --experimental", result.output)

    def test_update_reads_before_and_after_write(self):
        before = native_template()
        client, writes = self._client_with_persisted_write(before)
        with self.runner.isolated_filesystem():
            with open("update.json", "w", encoding="utf-8") as handle:
                json.dump({"name": "Revised"}, handle)
            with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
                result = self.runner.invoke(
                    cli,
                    ["--experimental", "--json", "--location-id", "loc-1", "documents", "update-template", "template-1", "--from-json", "update.json"],
                )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(client.get_contract_template.call_count, 2)
        client.update_contract_template.assert_called_once()
        payload = client.update_contract_template.call_args.args[1]
        self.assertNotIn("futureGhlProperty", payload)
        self.assertNotIn("id", payload)

    def test_create_with_spec_creates_shell_updates_and_verifies(self):
        shell = native_template()
        shell["pages"] = []
        client, writes = self._client_with_persisted_write(shell)
        client.create_contract_template.return_value = {"id": "template-1"}
        with self.runner.isolated_filesystem():
            with open("contract.json", "w", encoding="utf-8") as handle:
                json.dump({"fields": [{"type": "name"}, {"type": "signature"}]}, handle)
            with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
                result = self.runner.invoke(
                    cli,
                    ["--experimental", "--json", "--location-id", "loc-1", "documents", "create-template", "--name", "Agreement", "--from-json", "contract.json"],
                )
        self.assertEqual(result.exit_code, 0, result.output)
        client.create_contract_template.assert_called_once_with("Agreement", is_public_document=False)
        self.assertEqual(client.get_contract_template.call_count, 2)
        payload = client.update_contract_template.call_args.args[1]
        children = payload["pages"][0]["children"]
        contractor = [
            item for item in children
            if item["component"]["options"]["recipient"] == ASSIGNED_CONTACT_ID
        ]
        sender = [
            item for item in children
            if item["component"]["options"]["recipient"] == ASSIGNED_SENDER_ID
        ]
        self.assertEqual([item["type"] for item in contractor], ["TextField", "Signature", "DateField"])
        self.assertEqual([item["type"] for item in sender], ["DateField", "Signature"])
        self.assertEqual(len(children), 5)

    def test_create_name_option_overrides_json_name(self):
        shell = native_template()
        shell["pages"] = []
        client, writes = self._client_with_persisted_write(shell)
        client.create_contract_template.return_value = {"id": "template-1"}
        with self.runner.isolated_filesystem():
            with open("contract.json", "w", encoding="utf-8") as handle:
                json.dump({"name": "Name from JSON", "fields": []}, handle)
            with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
                result = self.runner.invoke(
                    cli,
                    ["--experimental", "--json", "--location-id", "loc-1", "documents", "create-template", "--name", "Explicit CLI Name", "--from-json", "contract.json"],
                )
        self.assertEqual(result.exit_code, 0, result.output)
        client.create_contract_template.assert_called_once_with("Explicit CLI Name", is_public_document=False)
        self.assertEqual(client.update_contract_template.call_args.args[1]["name"], "Explicit CLI Name")

    def test_create_without_spec_persists_and_verifies_default_signer_fields(self):
        shell = native_template()
        shell["pages"] = []
        client, writes = self._client_with_persisted_write(shell)
        client.create_contract_template.return_value = {"id": "template-1"}
        with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
            result = self.runner.invoke(
                cli,
                ["--experimental", "--json", "--location-id", "loc-1", "documents", "create-template", "--name", "Agreement"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(client.get_contract_template.call_count, 2)
        client.update_contract_template.assert_called_once()
        payload = client.update_contract_template.call_args.args[1]
        self.assertEqual(
            [item["type"] for item in payload["pages"][-1]["children"]],
            ["DateField", "Signature", "TextField", "DateField", "Signature"],
        )
        called_methods = [call[0].lower() for call in client.method_calls]
        self.assertFalse(any("publish" in method for method in called_methods))
        self.assertFalse(any("send" in method for method in called_methods))

    def test_invalid_create_spec_does_not_create_remote_shell(self):
        client = Mock()
        with self.runner.isolated_filesystem():
            with open("invalid.json", "w", encoding="utf-8") as handle:
                json.dump({"fields": [{"type": "phone"}]}, handle)
            with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
                result = self.runner.invoke(
                    cli,
                    ["--experimental", "--location-id", "loc-1", "documents", "create-template", "--name", "Agreement", "--from-json", "invalid.json"],
                )
        self.assertEqual(result.exit_code, 1, result.output)
        client.create_contract_template.assert_not_called()

    def test_add_field_never_sends_or_publishes(self):
        before = native_template()
        client, writes = self._client_with_persisted_write(before)
        with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
            result = self.runner.invoke(
                cli,
                ["--experimental", "--json", "--location-id", "loc-1", "documents", "add-field", "template-1", "--type", "signature", "--top", "700"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(client.get_contract_template.call_count, 2)
        client.update_contract_template.assert_called_once()
        self.assertNotIn("publish", str(client.method_calls).lower())

    def test_silent_write_noop_fails_after_fresh_read(self):
        client = Mock()
        before = native_template()
        client.get_contract_template.return_value = before
        client.update_contract_template.return_value = {"ok": True}
        with self.runner.isolated_filesystem():
            with open("update.json", "w", encoding="utf-8") as handle:
                json.dump({"name": "Should Persist"}, handle)
            with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
                result = self.runner.invoke(
                    cli,
                    ["--experimental", "--location-id", "loc-1", "documents", "update-template", "template-1", "--from-json", "update.json"],
                )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("did not persist", result.output)

    def test_set_redirect_writes_native_shape_and_verifies_fresh_read(self):
        client, writes = self._client_with_persisted_write(native_template())
        with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
            result = self.runner.invoke(
                cli,
                [
                    "--experimental", "--json", "--location-id", "loc-1",
                    "documents", "set-redirect", "template-1",
                    "--url", "leadgenjay.com/team-buildout/welcome-call",
                    "--target", "existing-tab",
                ],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(client.get_contract_template.call_count, 2)
        self.assertEqual(writes[0]["redirectSettings"], {
            "enableDocumentRedirectUrl": True,
            "documentRedirectUrl": "https://leadgenjay.com/team-buildout/welcome-call",
            "documentRedirectType": "existingTab",
        })

    def test_set_redirect_fails_when_backend_silently_drops_it(self):
        client = Mock()
        client.get_contract_template.return_value = native_template()
        client.update_contract_template.return_value = {"ok": True}
        with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
            result = self.runner.invoke(
                cli,
                [
                    "--experimental", "--location-id", "loc-1",
                    "documents", "set-redirect", "template-1",
                    "--url", "https://example.com/complete",
                ],
            )
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("did not persist redirect setting", result.output)

    def test_export_includes_redirect_settings_for_round_trip(self):
        client = Mock()
        client.get_contract_template.return_value = native_template()
        with self.runner.isolated_filesystem():
            with patch("cli_anything.gohighlevel.gohighlevel_cli._get_internal_client", return_value=client):
                result = self.runner.invoke(
                    cli,
                    [
                        "--experimental", "--location-id", "loc-1",
                        "documents", "export-template", "template-1",
                        "--output", "export.json",
                    ],
                )
            with open("export.json", encoding="utf-8") as handle:
                exported = json.load(handle)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(exported["redirectSettings"]["documentRedirectType"], "newTab")


if __name__ == "__main__":
    unittest.main()
