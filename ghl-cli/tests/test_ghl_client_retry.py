"""Tests for public-API rate-limit handling and location-id resolution."""
from __future__ import annotations

import unittest
from unittest import mock

import requests

from cli_anything.gohighlevel.utils import ghl_client


def _resp(status: int, headers: dict | None = None, payload: dict | None = None):
    """Build a real requests.Response so raise_for_status behaves normally."""
    r = requests.Response()
    r.status_code = status
    r.headers.update(headers or {})
    r._content = b'{"ok": true}' if payload is None else __import__("json").dumps(payload).encode()
    r.url = "https://services.leadconnectorhq.com/test"
    return r


class RetryDelayTests(unittest.TestCase):
    def test_honors_numeric_retry_after(self):
        self.assertEqual(ghl_client._retry_delay(_resp(429, {"Retry-After": "7"}), 1), 7.0)

    def test_caps_absurd_retry_after(self):
        delay = ghl_client._retry_delay(_resp(429, {"Retry-After": "99999"}), 1)
        self.assertEqual(delay, ghl_client.MAX_BACKOFF_SECONDS)

    def test_falls_back_to_exponential_on_http_date(self):
        # GHL may send an HTTP-date, which float() cannot parse.
        r = _resp(429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})
        self.assertEqual(ghl_client._retry_delay(r, 1), ghl_client.BACKOFF_BASE_SECONDS)
        self.assertEqual(ghl_client._retry_delay(r, 3), ghl_client.BACKOFF_BASE_SECONDS * 4)

    def test_exponential_growth_is_capped(self):
        delay = ghl_client._retry_delay(_resp(429), 20)
        self.assertEqual(delay, ghl_client.MAX_BACKOFF_SECONDS)


class RequestRetryTests(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(
            "os.environ",
            {"GHL_API_KEY": "pit-test", "GHL_LOCATION_ID": "loc-test"},
        )
        env.start()
        self.addCleanup(env.stop)
        sleep = mock.patch.object(ghl_client.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def test_retries_429_then_succeeds(self):
        with mock.patch.object(
            ghl_client.requests, "request", side_effect=[_resp(429, {"Retry-After": "1"}), _resp(200)]
        ) as req:
            out = ghl_client.get("/contacts/")
        self.assertEqual(out, {"ok": True})
        self.assertEqual(req.call_count, 2)
        self.sleep.assert_called_once_with(1.0)

    def test_retries_transient_5xx(self):
        with mock.patch.object(
            ghl_client.requests, "request", side_effect=[_resp(503), _resp(200)]
        ) as req:
            ghl_client.get("/contacts/")
        self.assertEqual(req.call_count, 2)

    def test_gives_up_after_max_attempts_and_raises(self):
        with mock.patch.object(
            ghl_client.requests, "request", return_value=_resp(429)
        ) as req:
            with self.assertRaises(requests.exceptions.HTTPError):
                ghl_client.get("/contacts/")
        self.assertEqual(req.call_count, ghl_client.MAX_ATTEMPTS)

    def test_does_not_retry_client_errors(self):
        # A 422 is a bad request, not a transient condition — retrying wastes quota.
        with mock.patch.object(
            ghl_client.requests, "request", return_value=_resp(422)
        ) as req:
            with self.assertRaises(requests.exceptions.HTTPError):
                ghl_client.get("/contacts/")
        self.assertEqual(req.call_count, 1)
        self.sleep.assert_not_called()


class LocationIdTests(unittest.TestCase):
    def test_missing_location_id_exits_rather_than_defaulting(self):
        # Regression: this used to silently fall back to a hardcoded
        # production location, so a typo'd env var wrote to the wrong account.
        with mock.patch.dict("os.environ", {"GHL_LOCATION_ID": ""}):
            with self.assertRaises(SystemExit):
                ghl_client._get_location_id()

    def test_returns_trimmed_location_id(self):
        with mock.patch.dict("os.environ", {"GHL_LOCATION_ID": "  loc-abc  "}):
            self.assertEqual(ghl_client._get_location_id(), "loc-abc")


if __name__ == "__main__":
    unittest.main()
