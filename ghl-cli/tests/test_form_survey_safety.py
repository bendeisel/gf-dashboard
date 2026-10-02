import json
import unittest
from unittest.mock import Mock, patch

from click.testing import CliRunner

from cli_anything.gohighlevel.gohighlevel_cli import cli
from cli_anything.gohighlevel.utils.form_survey_builder import (
    build_form_action,
    build_form_payload,
    build_survey_payload,
)
from cli_anything.gohighlevel.utils.ghl_internal_client import InternalGHLClient


class FormSurveyTypographyTests(unittest.TestCase):
    def test_native_form_defaults_to_inter_and_roboto(self):
        payload = build_form_payload({
            "name": "Lead Magnet",
            "fields": [
                {"kind": "header", "text": "Get the blueprint"},
                {"type": "submit", "tag": "submit", "label": "Send It"},
            ],
        })
        header, button = payload["formData"]["form"]["fields"]
        self.assertEqual((header["fontFamily"], header["weight"]), ("Inter", 700))
        self.assertEqual((button["fontFamily"], button["weight"]), ("Roboto", 700))

    def test_survey_button_defaults_to_roboto(self):
        payload = build_survey_payload({
            "name": "Fit Survey",
            "slides": [{"name": "Start", "button": "Continue", "fields": []}],
        })
        button = payload["formData"]["slides"][0]["button"]
        self.assertEqual((button["fontFamily"], button["weight"]), ("Roboto", 700))


class FormActionShapeTests(unittest.TestCase):
    """Pin formAction to what GoHighLevel actually stores.

    The expected values here were read off live UI-created forms in the
    leadgenjay location with `forms get` on 2026-08-24, not inferred. GHL
    accepts unknown keys silently and forms have no update route, so a drift
    here produces a form that has to be deleted and rebuilt.
    """

    def test_a_message_form_matches_the_stored_shape(self):
        action = build_form_action({"thankYouMessage": "Thanks, we got it."})
        self.assertEqual(action, {
            "actionType": "2",
            "redirectUrl": "",
            "thankyouText": "<p>Thanks, we got it.</p>",
            "headerImageSrc": "",
            "mobileHeaderImageSrc": "",
            "mobileHeaderImageSrcDeleted": False,
        })

    def test_a_redirect_form_matches_the_stored_shape(self):
        action = build_form_action({
            "redirectUrl": "https://leadgenjay.com/team-buildout/agreement",
            "thankYouMessage": "Thanks, we got it.",
        })
        self.assertEqual(action["actionType"], "1")
        self.assertEqual(
            action["redirectUrl"], "https://leadgenjay.com/team-buildout/agreement"
        )

    def test_action_type_is_a_string_not_an_int(self):
        # The live records store "1"/"2". An int here would be a different key
        # value to GHL and is the kind of drift nothing else would catch.
        for spec in ({"thankYouMessage": "x"}, {"redirectUrl": "https://example.com"}):
            self.assertIsInstance(build_form_action(spec)["actionType"], str)

    def test_existing_html_in_a_thank_you_message_is_left_alone(self):
        action = build_form_action({"thankYouMessage": "<p style='x'>Done</p>"})
        self.assertEqual(action["thankyouText"], "<p style='x'>Done</p>")

    def test_the_retired_type_message_shape_is_refused(self):
        # What this builder emitted before 2026-08-24. GHL stored it without
        # complaint and could not interpret it.
        with self.assertRaises(ValueError) as caught:
            build_form_action({"formAction": {"type": "message", "message": "Thanks"}})
        self.assertIn("does not store", str(caught.exception))

    def test_a_redirect_with_no_url_is_refused_at_build_time(self):
        with self.assertRaises(ValueError):
            build_form_action({"formAction": {"actionType": "1", "redirectUrl": "  "}})

    def test_a_relative_redirect_is_refused(self):
        with self.assertRaises(ValueError):
            build_form_action({"redirectUrl": "/team-buildout/agreement"})

    def test_an_unknown_action_type_is_refused(self):
        with self.assertRaises(ValueError):
            build_form_action({"formAction": {"actionType": "9"}})

    def test_the_payload_carries_the_action_at_the_stored_path(self):
        payload = build_form_payload({
            "name": "Team Buildout Intake",
            "redirectUrl": "https://my.leadgenjay.com/documents/doc-form/abc",
            "fields": [{"type": "email", "tag": "email", "label": "Email"}],
        })
        action = payload["formData"]["form"]["formAction"]
        self.assertEqual(action["actionType"], "1")
        self.assertNotIn("type", action)
        self.assertNotIn("message", action)


class DestructiveCommandConfirmationTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def _client_for(self, command):
        client = Mock()
        getattr(client, f"delete_{command}").return_value = True
        return client

    def test_delete_aborts_without_confirmation(self):
        for command in ("form", "survey", "funnel"):
            with self.subTest(command=command):
                client = self._client_for(command)
                with patch(
                    "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
                    return_value=client,
                ):
                    result = self.runner.invoke(
                        cli, ["--experimental", f"{command}s", "delete", f"{command}-id"],
                        input="n\n",
                    )
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertIn("Aborted.", result.output)
                getattr(client, f"delete_{command}").assert_not_called()

    def test_delete_runs_after_confirmation_or_yes_flag(self):
        for command, input_text, extra in (
            ("form", "y\n", []),
            ("survey", "", ["--yes"]),
            ("funnel", "", ["-y"]),
        ):
            with self.subTest(command=command):
                client = self._client_for(command)
                with patch(
                    "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
                    return_value=client,
                ):
                    result = self.runner.invoke(
                        cli,
                        ["--experimental", f"{command}s", "delete", f"{command}-id", *extra],
                        input=input_text,
                    )
                self.assertEqual(result.exit_code, 0, result.output)
                getattr(client, f"delete_{command}").assert_called_once_with(f"{command}-id")


class FormReadCommandTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_get_requires_experimental_flag(self):
        result = self.runner.invoke(cli, ["forms", "get", "form-id"])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("requires --experimental", result.output)

    def test_get_returns_full_stored_form_data(self):
        client = Mock()
        client.get_form.return_value = {
            "_id": "form-id",
            "name": "Team Buildout Intake",
            "formData": {
                "form": {
                    "fields": [{"tag": "company_name", "label": "Company name"}],
                    # The real stored shape, copied from a live record. Reading
                    # this back is the entire point of the command.
                    "formAction": {
                        "actionType": "1",
                        "redirectUrl": "https://example.com/agreement",
                        "thankyouText": "<p>Thank you.</p>",
                    },
                }
            },
        }
        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli._get_internal_client",
            return_value=client,
        ):
            result = self.runner.invoke(
                cli,
                ["--experimental", "--json", "forms", "get", "form-id"],
            )
        self.assertEqual(result.exit_code, 0, result.output)
        action = json.loads(result.output)["formData"]["form"]["formAction"]
        self.assertEqual(action["redirectUrl"], "https://example.com/agreement")
        client.get_form.assert_called_once_with("form-id")

    def test_internal_get_form_quotes_id_and_preserves_structured_error(self):
        client = InternalGHLClient(Mock(), "loc-1")
        client.request = Mock(return_value={"_error": True, "message": "forbidden"})
        result = client.get_form("form/id")
        self.assertEqual(result, {"_error": True, "message": "forbidden"})
        client.request.assert_called_once_with(
            "GET",
            "/forms/form%2Fid",
            extra_headers={"Version": "2021-07-28"},
        )


if __name__ == "__main__":
    unittest.main()
