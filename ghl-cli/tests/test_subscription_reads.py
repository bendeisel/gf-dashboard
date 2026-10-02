"""CLI coverage for public payment and agency SaaS subscription reads."""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from cli_anything.gohighlevel.gohighlevel_cli import cli
from cli_anything.gohighlevel.utils import ghl_client


class PaymentSubscriptionReadTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_list_passes_location_pagination_and_filters(self):
        payload = {"data": [{"_id": "sub-1", "status": "active"}], "totalCount": 1}
        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli.api.get",
            return_value=payload,
        ) as get:
            result = self.runner.invoke(
                cli,
                [
                    "--json",
                    "--location-id",
                    "loc-1",
                    "payments",
                    "subscriptions",
                    "--contact-id",
                    "contact-1",
                    "--status",
                    "active",
                    "--limit",
                    "7",
                    "--offset",
                    "14",
                ],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        get.assert_called_once_with(
            "/payments/subscriptions",
            params={
                "altId": "loc-1",
                "altType": "location",
                "limit": 7,
                "offset": 14,
                "contactId": "contact-1",
                "status": "active",
            },
        )
        self.assertEqual(json.loads(result.output), payload)

    def test_get_uses_subscription_id_and_location_scope(self):
        payload = {"_id": "sub-1", "status": "active"}
        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli.api.get",
            return_value=payload,
        ) as get:
            result = self.runner.invoke(
                cli,
                ["--json", "--location-id", "loc-1", "payments", "subscription", "sub-1"],
            )

        self.assertEqual(result.exit_code, 0, result.output)
        get.assert_called_once_with(
            "/payments/subscriptions/sub-1",
            params={"altId": "loc-1", "altType": "location"},
        )
        self.assertEqual(json.loads(result.output), payload)

    def test_help_lists_both_subscription_commands(self):
        result = self.runner.invoke(cli, ["payments", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("subscription ", result.output)
        self.assertIn("subscriptions", result.output)


class SaaSSubscriptionReadTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def _invoke_and_assert(self, args, path, params=None):
        payload = {"ok": True}
        with patch(
            "cli_anything.gohighlevel.gohighlevel_cli.api.get",
            return_value=payload,
        ) as get:
            result = self.runner.invoke(cli, ["--json", "saas", *args])
        self.assertEqual(result.exit_code, 0, result.output)
        if params is None:
            get.assert_called_once_with(path)
        else:
            get.assert_called_once_with(path, params=params)
        self.assertEqual(json.loads(result.output), payload)

    def test_locations_uses_company_path_and_page(self):
        self._invoke_and_assert(
            ["locations", "--company-id", "company-1", "--page", "3"],
            "/saas/saas-locations/company-1",
            {"page": 3},
        )

    def test_subscription_uses_location_path_and_company_query(self):
        self._invoke_and_assert(
            ["subscription", "loc-1", "--company-id", "company-1"],
            "/saas/get-saas-subscription/loc-1",
            {"companyId": "company-1"},
        )

    def test_find_location_maps_stripe_subscription_to_subaccount(self):
        self._invoke_and_assert(
            [
                "find-location",
                "--company-id",
                "company-1",
                "--subscription-id",
                "stripe-sub-1",
            ],
            "/saas/locations",
            {"companyId": "company-1", "subscriptionId": "stripe-sub-1"},
        )

    def test_find_location_requires_a_stripe_identifier(self):
        result = self.runner.invoke(
            cli,
            ["saas", "find-location", "--company-id", "company-1"],
        )
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Provide --customer-id or --subscription-id", result.output)

    def test_plans_uses_company_path(self):
        self._invoke_and_assert(
            ["plans", "--company-id", "company-1"],
            "/saas/agency-plans/company-1",
        )

    def test_plan_uses_plan_path_and_company_query(self):
        self._invoke_and_assert(
            ["plan", "plan-1", "--company-id", "company-1"],
            "/saas/saas-plan/plan-1",
            {"companyId": "company-1"},
        )

    def test_help_lists_reads_and_guarded_lifecycle_commands(self):
        result = self.runner.invoke(cli, ["saas", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        for command in (
            "locations", "find-location", "subscription", "plans", "plan",
            "audit", "disable", "pause", "delete",
        ):
            self.assertIn(command, result.output)
        for mutation in ("cancel", "enable", "update"):
            self.assertNotIn(f"\n  {mutation} ", result.output.lower())


class SaaSVersionRoutingTests(unittest.TestCase):
    def test_saas_paths_use_v3(self):
        self.assertEqual(ghl_client._version_for_path("/saas/agency-plans/company-1"), "v3")

    def test_payment_paths_keep_existing_version(self):
        self.assertEqual(
            ghl_client._version_for_path("/payments/subscriptions"),
            "2021-07-28",
        )

    def test_saas_prefers_agency_token(self):
        with patch.dict(
            os.environ,
            {"GHL_API_KEY": "location-token", "GHL_AGENCY_API_KEY": "agency-token"},
            clear=True,
        ):
            headers = ghl_client._headers(path="/saas/agency-plans/company-1")
        self.assertEqual(headers["Authorization"], "Bearer agency-token")

    def test_non_saas_paths_keep_location_token(self):
        with patch.dict(
            os.environ,
            {"GHL_API_KEY": "location-token", "GHL_AGENCY_API_KEY": "agency-token"},
            clear=True,
        ):
            headers = ghl_client._headers(path="/payments/subscriptions")
        self.assertEqual(headers["Authorization"], "Bearer location-token")

    def test_saas_falls_back_to_standard_token(self):
        with patch.dict(
            os.environ,
            {"GHL_API_KEY": "location-token", "GHL_AGENCY_API_KEY": ""},
            clear=True,
        ):
            headers = ghl_client._headers(path="/saas/agency-plans/company-1")
        self.assertEqual(headers["Authorization"], "Bearer location-token")


if __name__ == "__main__":
    unittest.main()
