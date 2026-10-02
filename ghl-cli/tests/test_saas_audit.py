"""Read-only reconciliation coverage for ``ghl saas audit``."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from click.testing import CliRunner

from cli_anything.gohighlevel.gohighlevel_cli import cli
from cli_anything.gohighlevel.utils import ghl_client
from cli_anything.gohighlevel.utils import saas_audit

# The population check compares against a baseline the operator sets.
os.environ["GHL_SAAS_BASELINE"] = "281/249"
os.environ.setdefault("GHL_LOCATION_ID", "billing-loc")
os.environ.setdefault("GHL_SAAS_PRODUCT_ID", "product-1")


def _saas_location(location_id: str, email: str, status: str, subscription_id: str) -> dict:
    return {
        "locationId": location_id,
        "name": f"Location {location_id}",
        "email": email,
        "saasMode": "activated",
        "subscriptionId": subscription_id,
        "subscriptionInfo": {
            "subscriptionStatus": status,
            "productId": "saas-product",
            "priceId": "saas-price",
            "saasPlanId": "saas-plan",
        },
    }


def _payment(index: int, email: str | None = None, status: str = "canceled") -> dict:
    return {
        "_id": f"payment-record-{index}",
        "subscriptionId": f"payment-sub-{index}",
        "contactId": f"contact-{index % 249}",
        "contactEmail": email or f"person-{index}@example.com",
        "entityId": f"order-{index}",
        "status": status,
        "amount": 49,
        "currency": "USD",
        "recurringProduct": {"product": {"_id": "product-1"}},
    }


class SaaSAuditHelperTests(unittest.TestCase):
    def test_population_check_is_unchecked_without_a_baseline(self):
        with patch.dict(os.environ, {"GHL_SAAS_BASELINE": ""}):
            self.assertEqual(saas_audit.population_check(20, 10)["status"], "unchecked")

    def test_population_check_exact_near_and_failed(self):
        self.assertEqual(saas_audit.population_check(281, 249)["status"], "exact")
        self.assertEqual(saas_audit.population_check(300, 260)["status"], "near")
        self.assertEqual(saas_audit.population_check(20, 10)["status"], "failed")

    def test_classifications_are_fail_closed(self):
        base = {
            "email": "client@example.com",
            "saasMode": "activated",
            "saas": {"status": "canceled"},
            "payment": {"subscriptions": []},
            "errors": [],
        }
        cases = [
            ({"saas": {"status": "active"}}, "active-paid"),
            ({"payment": {"subscriptions": [{"status": "trialing"}]}}, "active-paid"),
            ({"saas": {"status": "paused"}}, "paused/deleted"),
            ({"email": "owner@agency.example"}, "active-comped"),
            ({}, "active-unpaid"),
            ({"saas": {"status": "new-undocumented-status"}}, "unknown"),
            ({"errors": ["read failed"]}, "unknown"),
            ({"saas": {"status": ""}}, "unknown"),
            ({"saasMode": ""}, "unknown"),
        ]
        for changes, expected in cases:
            row = {
                **base,
                **changes,
                "saas": changes.get("saas", base["saas"]),
                "payment": changes.get("payment", base["payment"]),
            }
            self.assertEqual(
                saas_audit.classify_row(row, set(), {"agency.example"}),
                expected,
            )

    def test_comp_file_accepts_lines_and_json(self):
        with tempfile.TemporaryDirectory() as directory:
            line_path = os.path.join(directory, "comped.txt")
            json_path = os.path.join(directory, "comped.json")
            with open(line_path, "w", encoding="utf-8") as handle:
                handle.write("# ledger export\nComp@Example.com\n")
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(["Other@Example.com"], handle)
            self.assertEqual(saas_audit.load_comped_emails(line_path), {"comp@example.com"})
            self.assertEqual(saas_audit.load_comped_emails(json_path), {"other@example.com"})

    def test_latest_invoice_requires_successful_live_transaction(self):
        rows = [
            {"_id": "old", "status": "succeeded", "liveMode": True, "createdAt": "2026-01-01"},
            {"_id": "test", "status": "succeeded", "liveMode": False, "createdAt": "2026-03-01"},
            {"_id": "new", "status": "succeeded", "liveMode": True, "createdAt": "2026-02-01"},
        ]
        self.assertEqual(saas_audit.latest_successful_transaction(rows)["_id"], "new")

    def test_product_identity_uses_only_live_proven_internal_ids(self):
        line_item_only = {"lineItemDetails": {"productId": "not-an-internal-product-id"}}
        recurring = {"recurringProduct": {"product": {"_id": "product-1"}}}
        self.assertIsNone(saas_audit.product_id(line_item_only))
        self.assertEqual(saas_audit.product_id(recurring), "product-1")
        self.assertEqual(
            saas_audit.order_product_ids({"items": [{"product": {"_id": "product-3"}}]}),
            {"product-3"},
        )
        self.assertEqual(
            saas_audit.order_product_ids({"items": [
                {"product": {"_id": "product-3"}},
                {"product": {"_id": "product-4"}},
            ]}),
            {"product-3", "product-4"},
        )


class SaaSAuditCommandTests(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @staticmethod
    def _exact_baseline_payments() -> list[dict]:
        rows = [_payment(index) for index in range(281)]
        rows[0] = _payment(0, email="paid@example.com", status="active")
        return rows

    def _exact_side_effect(self, path, params=None, version=None, agency=False):
        if path.endswith("/saas-locations/company-1"):
            if params["page"] == 1:
                return {
                    "data": {
                        "locations": [_saas_location("loc-paid", "paid@example.com", "active", "agency-sub-paid")],
                        "pagination": {"page": "1", "limit": 1, "total": 2, "totalPages": 2, "hasNext": True},
                    }
                }
            return {
                "data": {
                    "locations": [_saas_location("loc-unpaid", "unpaid@example.com", "canceled", "agency-sub-unpaid")],
                    "pagination": {"page": "2", "limit": 1, "total": 2, "totalPages": 2, "hasNext": False},
                }
            }
        if path == "/payments/subscriptions":
            rows = self._exact_baseline_payments()
            return {"data": rows, "totalCount": len(rows)}
        if path == "/locations/search":
            self.assertTrue(agency)
            self.assertEqual(version, "v3")
            return {
                "locations": [
                    {"id": "loc-paid", "dateAdded": "2026-01-01", "name": "Paid"},
                    {"id": "loc-unpaid", "dateAdded": "2026-01-02", "name": "Unpaid"},
                ]
            }
        if path.startswith("/saas/get-saas-subscription/"):
            location_id = path.rsplit("/", 1)[-1]
            status = "active" if location_id == "loc-paid" else "canceled"
            subscription_id = "agency-sub-paid" if location_id == "loc-paid" else "agency-sub-unpaid"
            return {"data": {"locationId": location_id, "saasMode": "activated", "subscriptionId": subscription_id, "subscriptionStatus": status}}
        if path == "/payments/transactions":
            self.assertEqual(params["subscriptionId"], "payment-sub-0")
            return {
                "data": [{
                    "_id": "transaction-1", "status": "succeeded", "liveMode": True,
                    "createdAt": "2026-08-30T12:00:00Z", "amount": 49, "currency": "USD",
                    "chargeSnapshot": {"invoice": None},
                    "invoiceId": "invoice-1",
                }],
                "totalCount": 1,
            }
        raise AssertionError(f"Unexpected GET {path} {params}")

    def test_json_audit_paginates_and_keeps_two_subscription_sides(self):
        with patch.dict(os.environ, {"GHL_AGENCY_API_KEY": "agency-token"}, clear=False), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get", side_effect=self._exact_side_effect) as get, \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.post") as post, \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.put") as put, \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.delete") as delete:
            result = self.runner.invoke(cli, ["--json", "saas", "audit", "--company-id", "company-1", "--product-id", "product-1"])

        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(result.output)
        self.assertEqual(report["populationCheck"]["status"], "exact")
        self.assertEqual(report["summary"]["classifications"]["active-paid"], 1)
        self.assertEqual(report["summary"]["classifications"]["active-unpaid"], 1)
        paid = next(row for row in report["rows"] if row["locationId"] == "loc-paid")
        self.assertEqual(paid["saas"]["subscriptionId"], "agency-sub-paid")
        self.assertEqual(paid["payment"]["subscriptions"][0]["id"], "payment-sub-0")
        # This fixture's SaaS detail carries no customerId, so the row falls back to the
        # email join and records which key it actually used.
        self.assertEqual(
            paid["join"],
            {"method": "email", "cardinality": 1, "email": "paid@example.com"},
        )
        self.assertEqual(paid["payment"]["lastInvoice"]["date"], "2026-08-30T12:00:00Z")
        self.assertEqual(paid["payment"]["lastInvoice"]["invoiceId"], "invoice-1")
        self.assertGreaterEqual(get.call_count, 7)
        post.assert_not_called()
        put.assert_not_called()
        delete.assert_not_called()

    def test_population_failure_withholds_summary_and_exits_nonzero(self):
        def side_effect(path, params=None, version=None, agency=False):
            if path.endswith("/saas-locations/company-1"):
                return {"data": {"locations": [_saas_location("loc-1", "one@example.com", "canceled", "agency-1")], "pagination": {"page": 1, "limit": 20, "total": 1, "totalPages": 1, "hasNext": False}}}
            if path == "/payments/subscriptions":
                return {"data": [], "totalCount": 0}
            if path == "/locations/search":
                return {"locations": [{"id": "loc-1", "dateAdded": "2026-01-01"}]}
            if path.startswith("/saas/get-saas-subscription/"):
                return {"data": {"locationId": "loc-1", "saasMode": "activated", "subscriptionId": "agency-1", "subscriptionStatus": "canceled"}}
            raise AssertionError(path)

        with patch.dict(os.environ, {"GHL_AGENCY_API_KEY": "agency-token"}, clear=False), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get", side_effect=side_effect):
            result = self.runner.invoke(cli, ["--json", "saas", "audit", "--company-id", "company-1", "--product-id", "product-1"])

        self.assertEqual(result.exit_code, 2, result.output)
        report = json.loads(result.output)
        self.assertEqual(report["populationCheck"]["status"], "failed")
        self.assertIsNone(report["summary"]["classifications"])
        self.assertEqual(report["rows"][0]["classification"], "unknown")
        self.assertIn("classification withheld", report["rows"][0]["errors"][-1])

    def test_missing_list_product_is_resolved_from_fresh_order_detail(self):
        payments = self._exact_baseline_payments()
        payments[0].pop("recurringProduct")

        def side_effect(path, params=None, version=None, agency=False):
            if path == "/payments/subscriptions":
                return {"data": payments, "totalCount": len(payments)}
            if path == "/payments/orders/order-0":
                self.assertEqual(version, "v3")
                return {"items": [{"product": {"_id": "product-1"}}]}
            return self._exact_side_effect(path, params=params, version=version, agency=agency)

        with patch.dict(os.environ, {"GHL_AGENCY_API_KEY": "agency-token"}, clear=False), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get", side_effect=side_effect):
            result = self.runner.invoke(cli, ["--json", "saas", "audit", "--company-id", "company-1", "--product-id", "product-1"])

        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(result.output)
        self.assertEqual(report["populationCheck"]["status"], "exact")
        self.assertEqual(report["diagnostics"]["orderProductLookups"], 1)
        self.assertEqual(report["diagnostics"]["unidentifiedProductSubscriptions"], 0)

    def test_unresolved_order_product_fails_population_safety_check(self):
        payments = self._exact_baseline_payments()
        payments[0].pop("recurringProduct")

        def side_effect(path, params=None, version=None, agency=False):
            if path == "/payments/subscriptions":
                return {"data": payments, "totalCount": len(payments)}
            if path == "/payments/orders/order-0":
                return {"items": []}
            return self._exact_side_effect(path, params=params, version=version, agency=agency)

        with patch.dict(os.environ, {"GHL_AGENCY_API_KEY": "agency-token"}, clear=False), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get", side_effect=side_effect):
            result = self.runner.invoke(cli, ["--json", "saas", "audit", "--company-id", "company-1", "--product-id", "product-1"])

        self.assertEqual(result.exit_code, 2, result.output)
        report = json.loads(result.output)
        self.assertEqual(report["populationCheck"]["status"], "failed")
        self.assertTrue(all(row["classification"] == "unknown" for row in report["rows"]))

    def test_multiple_payment_records_make_the_row_unknown(self):
        payments = self._exact_baseline_payments()
        payments[1]["contactEmail"] = "paid@example.com"

        def side_effect(path, params=None, version=None, agency=False):
            if path == "/payments/subscriptions":
                return {"data": payments, "totalCount": len(payments)}
            if path == "/payments/transactions":
                return {"data": [], "totalCount": 0}
            return self._exact_side_effect(path, params=params, version=version, agency=agency)

        with patch.dict(os.environ, {"GHL_AGENCY_API_KEY": "agency-token"}, clear=False), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get", side_effect=side_effect):
            result = self.runner.invoke(cli, ["--json", "saas", "audit", "--company-id", "company-1", "--product-id", "product-1"])

        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(result.output)
        paid = next(row for row in report["rows"] if row["locationId"] == "loc-paid")
        self.assertEqual(paid["classification"], "unknown")
        self.assertIn("multiple payment subscriptions", " ".join(paid["errors"]))

    def test_reused_saas_email_makes_each_location_unknown(self):
        original = self._exact_side_effect

        def side_effect(path, params=None, version=None, agency=False):
            payload = original(path, params=params, version=version, agency=agency)
            if path.endswith("/saas-locations/company-1") and params["page"] == 2:
                payload["data"]["locations"][0]["email"] = "paid@example.com"
            return payload

        with patch.dict(os.environ, {"GHL_AGENCY_API_KEY": "agency-token"}, clear=False), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get", side_effect=side_effect):
            result = self.runner.invoke(cli, ["--json", "saas", "audit", "--company-id", "company-1", "--product-id", "product-1"])

        self.assertEqual(result.exit_code, 0, result.output)
        report = json.loads(result.output)
        self.assertTrue(all(row["classification"] == "unknown" for row in report["rows"]))
        self.assertTrue(all("multiple SaaS locations" in " ".join(row["errors"]) for row in report["rows"]))

    def test_truncated_saas_pagination_fails(self):
        def side_effect(path, params=None, version=None, agency=False):
            if path.endswith("/saas-locations/company-1"):
                return {"data": {"locations": [_saas_location("loc-1", "one@example.com", "active", "agency-1")], "pagination": {"page": 1, "limit": 20, "total": 2, "totalPages": 2, "hasNext": False}}}
            raise AssertionError(path)

        with patch.dict(os.environ, {"GHL_AGENCY_API_KEY": "agency-token"}, clear=False), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get", side_effect=side_effect):
            result = self.runner.invoke(cli, ["saas", "audit", "--company-id", "company-1"])
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Invalid SaaS pagination metadata", result.output)

    def test_missing_agency_token_fails_before_any_read(self):
        with patch.dict(os.environ, {"GHL_AGENCY_API_KEY": ""}, clear=False), \
             patch("cli_anything.gohighlevel.gohighlevel_cli.api.get") as get:
            result = self.runner.invoke(cli, ["saas", "audit", "--company-id", "company-1"])
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("GHL_AGENCY_API_KEY is required", result.output)
        get.assert_not_called()

    def test_help_exposes_no_mutation_flags(self):
        result = self.runner.invoke(cli, ["saas", "audit", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--company-id", result.output)
        for forbidden in ("--apply", "--delete", "--pause", "--disable", "--all"):
            self.assertNotIn(forbidden, result.output)

    def test_table_renders_every_row(self):
        rows = []
        for index in range(7):
            rows.append({
                "classification": "active-unpaid", "locationId": f"loc-{index}", "name": f"Name {index}",
                "createdAt": "2026-01-01", "saas": {"status": "canceled", "subscriptionId": f"agency-{index}"},
                "payment": {"subscriptions": [], "lastInvoice": None}, "join": {"cardinality": 0},
            })
        report = {
            "rows": rows,
            "populationCheck": {"status": "near", "observedSubscriptions": 300, "observedContacts": 260, "baselineSubscriptions": 281, "baselineContacts": 249},
            "summary": {"classifications": saas_audit.classification_counts(rows)},
            "warnings": [],
        }
        rendered = saas_audit.render_table(report)
        for index in range(7):
            self.assertIn(f"loc-{index}", rendered)


class SaaSAuditAgencyRoutingTests(unittest.TestCase):
    def test_explicit_agency_route_uses_agency_token(self):
        with patch.dict(os.environ, {"GHL_API_KEY": "location", "GHL_AGENCY_API_KEY": "agency"}, clear=True):
            headers = ghl_client._headers(path="/locations/search", version="v3", agency=True)
        self.assertEqual(headers["Authorization"], "Bearer agency")
        self.assertEqual(headers["Version"], "v3")


if __name__ == "__main__":
    unittest.main()
