"""Firebase token refresh retry and diagnostic safety tests."""
from __future__ import annotations

import io
import json
import unittest
import urllib.error
from contextlib import redirect_stderr
from unittest.mock import patch

from cli_anything.gohighlevel.utils.ghl_internal_client import TokenManager


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def _http_error(code, body):
    return urllib.error.HTTPError(
        "https://securetoken.googleapis.com", code, "error", {}, io.BytesIO(body)
    )


class TokenRefreshTests(unittest.TestCase):
    def setUp(self):
        self.manager = TokenManager()
        self.refresh_token = "secret-refresh-token-must-never-print"
        self.web_key = "secret-web-key-must-never-print"

    def _refresh(self, side_effect):
        stderr = io.StringIO()
        with patch(
            "cli_anything.gohighlevel.utils.ghl_internal_client.urllib.request.urlopen",
            side_effect=side_effect,
        ) as urlopen, patch(
            "cli_anything.gohighlevel.utils.ghl_internal_client.time.sleep"
        ) as sleep, redirect_stderr(stderr):
            result = self.manager._refresh_firebase(self.refresh_token, self.web_key)
        self.assertNotIn(self.refresh_token, stderr.getvalue())
        self.assertNotIn(self.web_key, stderr.getvalue())
        return result, urlopen, sleep, stderr.getvalue()

    def test_refresh_succeeds_after_429(self):
        throttled = _http_error(429, b'{"error":{"message":"TOO_MANY_ATTEMPTS_TRY_LATER"}}')
        result, urlopen, sleep, diagnostic = self._refresh(
            [throttled, _Response({"id_token": "fresh-id-token"})]
        )
        self.assertEqual(result, "fresh-id-token")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1.5)
        self.assertEqual(diagnostic, "")

    def test_terminal_invalid_refresh_token_does_not_retry(self):
        invalid = _http_error(400, b'{"error":{"message":"INVALID_REFRESH_TOKEN"}}')
        result, urlopen, sleep, diagnostic = self._refresh([invalid])
        self.assertIsNone(result)
        self.assertEqual(urlopen.call_count, 1)
        sleep.assert_not_called()
        self.assertIn("HTTP 400 INVALID_REFRESH_TOKEN", diagnostic)

    def test_missing_id_token_exhausts_all_attempts(self):
        result, urlopen, sleep, diagnostic = self._refresh(
            [_Response({}), _Response({"refresh_token": "ignored"}), _Response({})]
        )
        self.assertIsNone(result)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual([call.args for call in sleep.call_args_list], [(1.5,), (3.0,)])
        self.assertIn("response carried no id_token", diagnostic)

    def test_malformed_error_body_retries_and_reports_http_status(self):
        failures = [_http_error(500, b"not-json") for _ in range(3)]
        result, urlopen, sleep, diagnostic = self._refresh(failures)
        self.assertIsNone(result)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertIn("HTTP 500", diagnostic)

    def test_http_server_detail_redacts_both_credentials(self):
        message = f"rejected {self.refresh_token} with key {self.web_key}".encode()
        body = json.dumps({"error": {"message": message.decode()}}).encode()
        failures = [_http_error(500, body) for _ in range(3)]
        result, urlopen, _, diagnostic = self._refresh(failures)
        self.assertIsNone(result)
        self.assertEqual(urlopen.call_count, 3)
        self.assertNotIn(self.refresh_token, diagnostic)
        self.assertNotIn(self.web_key, diagnostic)
        self.assertIn("[REDACTED]", diagnostic)

    def test_arbitrary_exception_redacts_both_credentials(self):
        failures = [
            RuntimeError(f"transport included {self.refresh_token} and {self.web_key}")
            for _ in range(3)
        ]
        result, urlopen, _, diagnostic = self._refresh(failures)
        self.assertIsNone(result)
        self.assertEqual(urlopen.call_count, 3)
        self.assertNotIn(self.refresh_token, diagnostic)
        self.assertNotIn(self.web_key, diagnostic)
        self.assertIn("[REDACTED]", diagnostic)


if __name__ == "__main__":
    unittest.main()
