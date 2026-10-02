"""Pin the three GHL shapes that fail silently when they are wrong.

Each of these was wrong in a workflow that GHL accepted, stored, and drew
correctly in the UI, while the thing itself never happened. A unit test cannot
prove GHL honours a key, so each assertion here is pinned to a value read off a
live, published workflow that demonstrably works (2026-08-25).
"""

import unittest

from cli_anything.gohighlevel.utils.workflow_builder import (
    CampaignBuilder,
    add_to_workflow_step,
    contact_tag_trigger,
    document_status_trigger,
    email_step,
    form_submission_trigger,
    goal_step,
    link_steps,
    update_field_step,
    validate_campaign,
)


class EmailSenderKeys(unittest.TestCase):
    """`fromName` is stored and never read; the live workflows use from_name."""

    def test_sender_keys_are_snake_case(self):
        step = email_step("Welcome", "Hi", "body",
                          from_name="Agency Team",
                          from_email="owner@example.com")
        attrs = step["attributes"]
        self.assertEqual(attrs["from_name"], "Agency Team")
        self.assertEqual(attrs["from_email"], "owner@example.com")

    def test_the_dead_camelcase_key_is_gone(self):
        # Its presence is the tell that a workflow predates the fix and is
        # sending under the location default.
        self.assertNotIn("fromName", email_step("n", "s", "b")["attributes"])

    def test_sender_is_optional_and_then_empty_not_absent(self):
        attrs = email_step("n", "s", "b")["attributes"]
        self.assertEqual(attrs["from_email"], "")


class TriggerShapes(unittest.TestCase):
    def test_form_submission_value_is_a_list_even_for_one_form(self):
        spec = form_submission_trigger(["YPKim6iQWi5YB6NQgEtA"])
        condition = spec["conditions"][0]
        self.assertEqual(condition["field"], "form.id")
        self.assertEqual(condition["operator"], "is-any-of")
        self.assertEqual(condition["value"], ["YPKim6iQWi5YB6NQgEtA"])

    def test_document_trigger_is_internal_not_highlevel(self):
        # Created as "highlevel" it is accepted and never fires.
        spec = document_status_trigger("6a8cc5b93bf64d7b1632731d")
        self.assertEqual(spec["type"], "proposal_estimate_update")
        self.assertEqual(spec["master_type"], "internal")
        self.assertEqual(spec["workflows_trigger_type"], "INTERNAL")

    def test_document_trigger_defaults_to_completed(self):
        # Of 300 documents on the LGJ account, 188 reach `completed` and none
        # reach `signed`, so SIGNED is a trigger that never fires.
        conditions = document_status_trigger("6a8cc5b93bf64d7b1632731d")["conditions"]
        by_field = {c["field"]: c["value"] for c in conditions}
        self.assertEqual(by_field["status"], "COMPLETED")
        self.assertEqual(by_field["documentCreatedByTemplateId"],
                         "6a8cc5b93bf64d7b1632731d")

    def test_contact_tag_trigger_keeps_its_original_shape(self):
        condition = contact_tag_trigger("whop team buildout")["conditions"][0]
        self.assertEqual(condition["field"], "tagsAdded")
        self.assertEqual(condition["operator"], "index-of-true")
        self.assertEqual(condition["value"], "whop team buildout")

    def test_every_trigger_helper_emits_both_required_keys(self):
        # CampaignBuilder refuses a spec missing either, because a trigger with
        # no conditions matches nothing and looks exactly like one nobody has
        # hit yet.
        for spec in (contact_tag_trigger("t"),
                     form_submission_trigger(["f"]),
                     document_status_trigger("6a8cc5b93bf64d7b1632731d")):
            with self.subTest(spec["type"]):
                self.assertTrue(spec.get("type"))
                self.assertTrue(spec.get("conditions"))


class StepShapes(unittest.TestCase):
    def test_add_to_workflow_carries_the_id_in_attributes(self):
        step = add_to_workflow_step("Chase", "7de90ce1-c17b-48d1-9701-8b917ea1cac0")
        self.assertEqual(step["type"], "add_to_workflow")
        self.assertEqual(step["attributes"]["workflow_id"],
                         "7de90ce1-c17b-48d1-9701-8b917ea1cac0")
        self.assertIs(step["attributes"]["input_trigger_params"], False)

    def test_update_field_step_matches_the_live_action_type(self):
        step = update_field_step("Assign", [
            {"field": "9Z3AkUUzfZkj3PQoDIYw", "value": "jonathan@leadgenjay.com",
             "title": "Account Manager Email", "type": "text"},
        ])
        self.assertEqual(step["attributes"]["actionType"], "update_field_data")
        self.assertEqual(step["attributes"]["fields"][0]["field"],
                         "9Z3AkUUzfZkj3PQoDIYw")

    def test_the_new_step_types_pass_campaign_validation(self):
        steps = link_steps([
            update_field_step("Assign", [{"field": "f", "value": "v",
                                          "title": "t", "type": "text"}]),
            email_step("Welcome", "Hi", "body", from_email="owner@example.com"),
            add_to_workflow_step("Chase", "wf-1"),
            goal_step("Done", ["tag"]),
        ])
        self.assertEqual(validate_campaign({"wf": {"name": "n", "templates": steps}}), [])


class CampaignBuilderTriggerIntegration(unittest.TestCase):
    class FakeClient:
        location_id = "loc-1"

        def __init__(self):
            self.calls = []
            self.created_tags = []

        @property
        def call_count(self):
            return len(self.calls)

        def create_location_tag(self, tag):
            self.created_tags.append(tag)
            return True

        def request(self, method, path, body=None):
            self.calls.append((method, path, body))
            if method == "POST" and path == "/workflow/loc-1":
                return {"id": "workflow-1"}
            if method == "POST" and path == "/workflow/loc-1/trigger":
                return {"id": "trigger-1"}
            if method == "GET" and path == "/workflow/loc-1/workflow-1":
                return {"version": 2, "meta": {}}
            return {"ok": True}

    def _build(self, workflow):
        client = self.FakeClient()
        stats = CampaignBuilder(client).build({"wf": workflow}, folder_id="folder-1")
        self.assertEqual(stats["errors"], [])
        return client

    def test_legacy_tag_pipeline_creates_tag_and_links_trigger(self):
        first = email_step("Welcome", "Hi", "Body")
        client = self._build({"name": "Legacy", "tag": "legacy-tag", "templates": [first]})
        self.assertEqual(client.created_tags, ["legacy-tag"])
        trigger_post = next(
            body for method, path, body in client.calls
            if method == "POST" and path.endswith("/trigger")
        )
        self.assertEqual(trigger_post["masterType"], "highlevel")
        trigger_put = next(
            body for method, path, body in client.calls
            if method == "PUT" and path == "/workflow/loc-1/trigger/trigger-1"
        )
        self.assertEqual(trigger_put["targetActionId"], first["id"])

    def test_explicit_internal_trigger_forwards_workflow_trigger_type(self):
        spec = document_status_trigger("template-1")
        client = self._build({
            "name": "Document complete",
            "trigger": spec,
            "templates": [email_step("Done", "Done", "Body")],
        })
        self.assertEqual(client.created_tags, [])
        trigger_post = next(
            body for method, path, body in client.calls
            if method == "POST" and path.endswith("/trigger")
        )
        self.assertEqual(trigger_post["masterType"], "internal")
        self.assertEqual(trigger_post["workflowsTriggerType"], "INTERNAL")

    def test_invalid_explicit_trigger_makes_no_client_request(self):
        client = self.FakeClient()
        stats = CampaignBuilder(client).build({
            "wf": {
                "name": "Invalid trigger",
                "trigger": {"type": "form_submission"},
                "templates": [email_step("Step", "Subject", "Body")],
            }
        }, folder_id="folder-1")
        self.assertTrue(any("invalid trigger spec" in error for error in stats["errors"]))
        self.assertEqual(client.calls, [])
        self.assertEqual(client.created_tags, [])


if __name__ == "__main__":
    unittest.main()
