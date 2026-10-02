"""A workflow PUT that omits senderAddress must not wipe it.

GHL resets any top-level workflow field a PUT leaves out. When the sender is
wiped, every blank-From email in the workflow goes out as the contact's
assigned user instead.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from cli_anything.gohighlevel.utils.ghl_internal_client import InternalGHLClient

LOC = "LOCATION123"
WID = "11111111-2222-3333-4444-555555555555"
SENDER = {"from_email": "owner@example.com", "from_name": "Owner"}


class WorkflowPutPreservesSenderTests(unittest.TestCase):
    def setUp(self):
        tm = MagicMock()
        tm.get_token.return_value = "tok"
        self.client = InternalGHLClient(tm, LOC)
        self.calls = []

        def fake(method, path, body, token, extra_headers=None):
            self.calls.append((method, path, body))
            if method == "GET":
                return {"id": WID, "senderAddress": SENDER, "status": "published"}
            return {"ok": True}

        self.client._do_request = fake

    def _put_body(self):
        puts = [c for c in self.calls if c[0] == "PUT"]
        self.assertEqual(len(puts), 1)
        return puts[0][2]

    def test_missing_sender_is_carried_from_current(self):
        self.client.request("PUT", f"/workflow/{LOC}/{WID}", {"name": "x", "workflowData": {"templates": []}})
        self.assertEqual(self._put_body()["senderAddress"], SENDER)

    def test_explicit_sender_is_left_alone(self):
        new = {"from_email": "help@example.com", "from_name": "Support"}
        self.client.request("PUT", f"/workflow/{LOC}/{WID}", {"name": "x", "senderAddress": new})
        self.assertEqual(self._put_body()["senderAddress"], new)
        self.assertFalse([c for c in self.calls if c[0] == "GET"])

    def test_explicit_null_clears_on_purpose(self):
        self.client.request("PUT", f"/workflow/{LOC}/{WID}", {"name": "x", "senderAddress": None})
        self.assertIsNone(self._put_body()["senderAddress"])

    def test_trigger_put_is_untouched(self):
        self.client.request("PUT", f"/workflow/{LOC}/trigger/abc", {"type": "x"})
        self.assertNotIn("senderAddress", self._put_body())
        self.assertFalse([c for c in self.calls if c[0] == "GET"])

    def test_failed_read_does_not_block_the_put(self):
        def fake(method, path, body, token, extra_headers=None):
            self.calls.append((method, path, body))
            return {"_error": True, "code": 500} if method == "GET" else {"ok": True}

        self.client._do_request = fake
        self.client.request("PUT", f"/workflow/{LOC}/{WID}", {"name": "x"})
        self.assertNotIn("senderAddress", self._put_body())


if __name__ == "__main__":
    unittest.main()
