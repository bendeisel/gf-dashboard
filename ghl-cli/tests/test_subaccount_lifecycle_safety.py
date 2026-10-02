"""Safety coverage for single-target SaaS lifecycle commands."""
from __future__ import annotations

import os
import stat
import tempfile
import unittest
from unittest.mock import patch

import requests
from click.testing import CliRunner

from cli_anything.gohighlevel.gohighlevel_cli import cli
from cli_anything.gohighlevel.utils import saas_lifecycle


def _target(*, status="canceled", mode="paused", errors=None):
    return {
        "locationId": "loc-1",
        "name": "Client One",
        "email": "client@example.com",
        "createdAt": "2026-01-02T03:04:05Z",
        "saasMode": mode,
        "classification": "paused/deleted" if mode == "paused" else "active-unpaid",
        "join": {"method": "contactId", "contactId": "contact-1", "cardinality": 1},
        "saas": {"status": status, "subscriptionId": "saas-sub-1"},
        "payment": {
            "subscriptions": [{"id": "pay-sub-1", "status": status}],
            "lastInvoice": {"date": "2026-08-01", "amount": 49, "currency": "USD"},
        },
        "errors": list(errors or []),
    }


class LifecycleCommandSafetyTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()
        self.env = {
            "GHL_AGENCY_API_KEY": "agency-token",
            "GHL_LOCATION_ID": "primary-loc",
            "GHL_SAAS_PRODUCT_ID": "product-1",
        }

    def invoke(self, command, extra=None, input=None):
        args = ["saas", command, "loc-1", "--company-id", "company-1"]
        if command == "delete":
            args += ["--reason", "Customer requested closure", "--keep-twilio-account"]
        args += extra or []
        return self.runner.invoke(cli, args, input=input, env=self.env)

    def test_all_commands_are_dry_run_and_write_nothing_by_default(self):
        for command in ("disable", "pause", "delete"):
            with self.subTest(command=command), \
                 patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target()), \
                 patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post, \
                 patch("cli_anything.gohighlevel.gohighlevel_cli.api.delete") as delete:
                result = self.invoke(command)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("dry-run", result.output)
            self.assertIn("loc-1", result.output)
            self.assertIn("Client One", result.output)
            self.assertIn("pay-sub-1", result.output)
            post.assert_not_called()
            delete.assert_not_called()

    def test_protected_primary_location_is_refused_before_reads(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target") as read:
            result = self.runner.invoke(
                cli,
                ["saas", "pause", "primary-loc", "--company-id", "company-1"],
                env=self.env,
            )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("permanently protected", result.output)
        read.assert_not_called()

    def test_apply_requires_click_confirmation(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(mode="activated")), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post:
            result = self.invoke("pause", ["--apply"], input="n\n")
        self.assertNotEqual(result.exit_code, 0)
        post.assert_not_called()

    def test_apply_refuses_unproven_target(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(errors=["join failed"])), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post:
            result = self.invoke("pause", ["--apply"], input="y\n")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("reads or joins are not proven", result.output)
        post.assert_not_called()

    def test_disable_export_failure_blocks_mutation(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(mode="activated")), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.saas_lifecycle_utils.read_wallet_export", side_effect=OSError("export failed")), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post:
            result = self.invoke("disable", ["--apply"], input="y\n")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("export failed", result.output)
        post.assert_not_called()

    def test_disable_does_not_treat_saas_v1_as_disabled(self):
        self.assertFalse(
            saas_lifecycle.is_disabled({"isSaaSV2": False, "saasMode": "activated"})
        )

    def test_disable_requires_location_absent_from_fresh_saas_list(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(mode="activated")), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.saas_lifecycle_utils.read_wallet_export", return_value={"walletBalance": {}, "walletTransactions": []}), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.saas_lifecycle_utils.write_wallet_export", return_value="/private/wallet.json"), \
             patch("cli_anything.gohighlevel.gohighlevel_cli._audit_location_profiles", return_value={"loc-1": {"id": "loc-1"}}), \
             patch("cli_anything.gohighlevel.gohighlevel_cli._audit_saas_locations", return_value=[{"locationId": "loc-1", "isSaaSV2": False, "saasMode": "activated"}]), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post:
            result = self.invoke("disable", ["--apply"], input="y\n")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("still found SaaS enabled", result.output)
        post.assert_called_once_with(
            "/saas/bulk-disable-saas/company-1",
            data={"locationIds": ["loc-1"]},
            version="v3",
            agency=True,
        )

    def test_disable_verifies_location_exists_and_saas_list_absence(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(mode="activated")), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.saas_lifecycle_utils.read_wallet_export", return_value={"walletBalance": {}, "walletTransactions": []}), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.saas_lifecycle_utils.write_wallet_export", return_value="/private/wallet.json"), \
             patch("cli_anything.gohighlevel.gohighlevel_cli._audit_location_profiles", return_value={"loc-1": {"id": "loc-1"}}), \
             patch("cli_anything.gohighlevel.gohighlevel_cli._audit_saas_locations", return_value=[]), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post:
            result = self.invoke("disable", ["--apply"], input="y\n")
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("verified: True", result.output)
        post.assert_called_once_with(
            "/saas/bulk-disable-saas/company-1",
            data={"locationIds": ["loc-1"]},
            version="v3",
            agency=True,
        )

    def test_delete_refuses_active_subscription(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(status="active")), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.delete") as delete:
            result = self.invoke("delete", ["--apply"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("active subscription", result.output)
        delete.assert_not_called()

    def test_delete_refuses_target_that_is_not_paused(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(mode="activated")), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.delete") as delete:
            result = self.invoke("delete", ["--apply"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("not paused", result.output)
        delete.assert_not_called()

    def test_delete_typed_name_must_match_exactly(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target()), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.delete") as delete:
            result = self.invoke("delete", ["--apply"], input="client one\n")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("did not match exactly", result.output)
        delete.assert_not_called()

    def test_delete_requires_twilio_choice_and_meaningful_reason(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target") as read:
            missing_choice = self.runner.invoke(
                cli,
                ["saas", "delete", "loc-1", "--company-id", "company-1", "--reason", "Customer requested closure"],
                env=self.env,
            )
            short_reason = self.runner.invoke(
                cli,
                ["saas", "delete", "loc-1", "--company-id", "company-1", "--reason", "too short", "--keep-twilio-account"],
                env=self.env,
            )
        self.assertNotEqual(missing_choice.exit_code, 0)
        self.assertIn("Choose --delete-twilio-account or --keep-twilio-account", missing_choice.output)
        self.assertNotEqual(short_reason.exit_code, 0)
        self.assertIn("at least 12 characters", short_reason.output)
        read.assert_not_called()

    def test_pause_post_write_verification_failure_exits_nonzero(self):
        with patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(mode="activated")), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post, \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get", return_value={"data": {"locationId": "loc-1", "saasMode": "activated", "subscriptionStatus": "canceled"}}):
            result = self.invoke("pause", ["--apply"], input="y\n")
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("verification did not show", result.output)
        post.assert_called_once_with(
            "/saas/pause/loc-1",
            data={"paused": True, "companyId": "company-1"},
            version="v3",
            agency=True,
        )

    def test_help_has_no_confirmation_bypass_or_bulk_input(self):
        for command in ("disable", "pause", "delete"):
            result = self.runner.invoke(cli, ["saas", command, "--help"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertNotIn("--yes", result.output)
            self.assertNotIn("--file", result.output)
            self.assertNotIn("--all", result.output)

    def test_json_apply_is_rejected_before_confirmation_or_write(self):
        for command in ("disable", "pause", "delete"):
            with self.subTest(command=command), \
                 patch("cli_anything.gohighlevel.gohighlevel_cli._lifecycle_read_target", return_value=_target(mode="activated")), \
                 patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post, \
                 patch("cli_anything.gohighlevel.gohighlevel_cli.api.delete") as delete:
                args = [
                    "--json", "saas", command, "loc-1", "--company-id", "company-1",
                    "--apply",
                ]
                if command == "delete":
                    args += [
                        "--reason", "Customer requested closure", "--keep-twilio-account",
                    ]
                result = self.runner.invoke(cli, args, env=self.env)
            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("cannot be combined", result.output)
            post.assert_not_called()
            delete.assert_not_called()


class WalletExportSafetyTests(unittest.TestCase):
    def test_wallet_export_paginates_and_is_mode_0600(self):
        first = [{"id": f"tx-{index}"} for index in range(1000)]
        get = unittest.mock.Mock(return_value={"data": {"balance": 123}})
        post = unittest.mock.Mock(side_effect=[{"data": {"transactions": first}}, {"data": {"transactions": [{"id": "last"}]}}])
        payload = saas_lifecycle.read_wallet_export(get, post, "company-1", "loc-1")
        self.assertEqual(len(payload["walletTransactions"]), 1001)
        with tempfile.TemporaryDirectory() as directory:
            path = saas_lifecycle.write_wallet_export(payload, directory, "loc-1")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)

    def test_repeated_full_wallet_page_fails_closed(self):
        page = [{"id": f"tx-{index}"} for index in range(1000)]
        get = unittest.mock.Mock(return_value={"balance": 0})
        post = unittest.mock.Mock(return_value={"data": page})
        with self.assertRaisesRegex(ValueError, "repeated"):
            saas_lifecycle.read_wallet_export(get, post, "company-1", "loc-1")


class LifecycleClientRoutingTests(unittest.TestCase):
    def test_post_and_delete_can_select_agency_token_and_params(self):
        response = unittest.mock.Mock()
        response.json.return_value = {"ok": True}
        response.raise_for_status.return_value = None
        response.status_code = 200
        with patch.dict(os.environ, {"GHL_API_KEY": "location", "GHL_AGENCY_API_KEY": "agency"}, clear=True), \
             patch("cli_anything.gohighlevel.utils.ghl_client.requests.request", return_value=response) as request:
            from cli_anything.gohighlevel.utils import ghl_client
            ghl_client.post("/saas/pause/loc-1", {"paused": True}, agency=True)
            ghl_client.delete("/locations/loc-1", params={"deleteTwilioAccount": False}, agency=True)
        self.assertEqual(request.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer agency")
        self.assertEqual(request.call_args_list[1].kwargs["headers"]["Authorization"], "Bearer agency")
        self.assertEqual(request.call_args_list[1].kwargs["params"], {"deleteTwilioAccount": False})


if __name__ == "__main__":
    unittest.main()
