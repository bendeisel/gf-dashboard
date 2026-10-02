"""The contact-id join, and the ways it must refuse to guess.

Email was the wrong key: a member took two free sub-accounts on two addresses and no email
match could see they were one person. GoHighLevel had already merged them onto one contact id
via their shared phone number, and the SaaS subscription record carries it as ``customerId``.
These cover that join and, just as importantly, the over-merge it creates in the other
direction.
"""
from __future__ import annotations

import unittest

from cli_anything.gohighlevel.utils import saas_audit


def _loc(location_id: str, email: str) -> dict:
    return {"locationId": location_id, "email": email, "name": f"Location {location_id}"}


def _pay(sub_id: str, contact_id: str, email: str, status: str = "active") -> dict:
    return {
        "subscriptionId": sub_id,
        "contactId": contact_id,
        "contactEmail": email,
        "status": status,
    }


class ContactIdJoinTests(unittest.TestCase):
    def test_one_contact_across_two_emails_joins_as_one_person(self):
        """The original incident. Two addresses, one contact, one sub-account."""
        locations = [_loc("loc-1", "second@gmail.com")]
        details = {"loc-1": {"customerId": "contact-1"}}
        by_contact = {"contact-1": [
            _pay("sub-old", "contact-1", "first@company.com", "canceled"),
            _pay("sub-new", "contact-1", "second@gmail.com", "active"),
        ]}
        # The email index deliberately cannot see the older subscription.
        by_email = {"second@gmail.com": [_pay("sub-new", "contact-1", "second@gmail.com")]}

        candidates, joins, errors = saas_audit.resolve_joins(
            locations, details, by_contact, by_email
        )

        self.assertEqual(joins["loc-1"]["method"], "contactId")
        self.assertEqual(joins["loc-1"]["contactId"], "contact-1")
        self.assertEqual(len(candidates["loc-1"]), 2)
        self.assertNotIn("loc-1", errors)

    def test_no_contact_id_falls_back_to_email_and_says_so(self):
        locations = [_loc("loc-1", "solo@example.com")]
        details = {"loc-1": {}}
        by_email = {"solo@example.com": [_pay("sub-1", "contact-9", "solo@example.com")]}

        candidates, joins, errors = saas_audit.resolve_joins(locations, details, {}, by_email)

        self.assertEqual(joins["loc-1"]["method"], "email")
        self.assertEqual(len(candidates["loc-1"]), 1)
        self.assertNotIn("loc-1", errors)

    def test_shared_contact_with_enough_active_subs_resolves(self):
        """Two locations on one contact, two active subscriptions: both are covered."""
        locations = [_loc("loc-1", "a@firm.com"), _loc("loc-2", "b@firm.com")]
        details = {"loc-1": {"customerId": "shared"}, "loc-2": {"customerId": "shared"}}
        by_contact = {"shared": [
            _pay("sub-1", "shared", "a@firm.com", "active"),
            _pay("sub-2", "shared", "b@firm.com", "active"),
        ]}

        _, joins, errors = saas_audit.resolve_joins(locations, details, by_contact, {})

        for location_id in ("loc-1", "loc-2"):
            self.assertEqual(joins[location_id]["locationsOnContact"], 2)
            self.assertTrue(joins[location_id]["sharedContactResolved"])
            self.assertNotIn(location_id, errors)

    def test_shared_contact_with_too_few_active_subs_is_unknown(self):
        """One active subscription cannot pay for two sub-accounts.

        GoHighLevel merges on phone, so two unrelated people can share a contact. Spreading
        a single active subscription across both would invent a payment that is not there.
        """
        locations = [_loc("loc-1", "a@firm.com"), _loc("loc-2", "b@firm.com")]
        details = {"loc-1": {"customerId": "shared"}, "loc-2": {"customerId": "shared"}}
        by_contact = {"shared": [
            _pay("sub-1", "shared", "a@firm.com", "active"),
            _pay("sub-2", "shared", "b@firm.com", "canceled"),
        ]}

        rows_errors = saas_audit.resolve_joins(locations, details, by_contact, {})[2]

        for location_id in ("loc-1", "loc-2"):
            self.assertIn(location_id, rows_errors)
            self.assertIn("cannot say which is covered", rows_errors[location_id][0])

    def test_own_active_saas_subscription_beats_a_shared_contact(self):
        """A shared contact must not demote a location that is plainly paying.

        The SaaS subscription is attached to one location, so an active one is per-location
        evidence and owes nothing to how the contact's payment records distribute. Counting
        only payment subscriptions here sent a paying account to `unknown` on the first live
        run of this join.
        """
        locations = [_loc("loc-1", "a@firm.com"), _loc("loc-2", "b@firm.com")]
        details = {
            "loc-1": {"customerId": "shared", "subscriptionStatus": "active"},
            "loc-2": {"customerId": "shared", "subscriptionStatus": "canceled"},
        }
        # No payment subscriptions on that contact at all within the audited product.
        _, joins, errors = saas_audit.resolve_joins(locations, details, {"shared": []}, {})

        self.assertTrue(joins["loc-1"]["sharedContactResolved"])
        self.assertEqual(joins["loc-1"]["resolvedBy"], "own-active-saas-subscription")
        self.assertNotIn("loc-1", errors)
        # The sibling has no active subscription of its own, so it stays ambiguous.
        self.assertIn("loc-2", errors)

    def test_no_contact_and_no_email_is_an_error(self):
        candidates, joins, errors = saas_audit.resolve_joins([_loc("loc-1", "")], {}, {}, {})
        self.assertEqual(candidates["loc-1"], [])
        self.assertEqual(joins["loc-1"]["method"], "email")
        self.assertIn("no contact id and no email join key", errors["loc-1"][0])


class PastDueClassificationTests(unittest.TestCase):
    """``past_due`` is a failed card, not a decision to leave.

    Folding it in with deliberate cancellations invites the wrong action: pausing deletes the
    account's phone numbers and A2P registrations after 14 days.
    """

    @staticmethod
    def _row(saas_status: str, payment_status: str | None) -> dict:
        payments = [] if payment_status is None else [{"status": payment_status}]
        return {
            "email": "person@example.com",
            "saasMode": "activated",
            "saas": {"status": saas_status},
            "payment": {"subscriptions": payments},
            "errors": [],
        }

    def test_past_due_saas_is_its_own_class(self):
        self.assertEqual(
            saas_audit.classify_row(self._row("past_due", None), set(), set()),
            "active-past-due",
        )

    def test_past_due_payment_is_its_own_class(self):
        self.assertEqual(
            saas_audit.classify_row(self._row("canceled", "past_due"), set(), set()),
            "active-past-due",
        )

    def test_canceled_stays_unpaid(self):
        self.assertEqual(
            saas_audit.classify_row(self._row("canceled", "canceled"), set(), set()),
            "active-unpaid",
        )

    def test_active_still_beats_past_due(self):
        self.assertEqual(
            saas_audit.classify_row(self._row("active", "past_due"), set(), set()),
            "active-paid",
        )


if __name__ == "__main__":
    unittest.main()
