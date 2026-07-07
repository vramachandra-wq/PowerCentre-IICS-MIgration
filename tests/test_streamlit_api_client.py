"""
Support test streamlit api client for automated regression coverage.
Verifies migration parsing, validation, API, and AI behavior.
"""

import json
import unittest
from unittest.mock import patch

from api.client import AIAPIClient, FastAPIClientError


class FakeHTTPResponse:
    """Defines response data returned by API endpoints."""

    def __init__(self, payload: object) -> None:
        """Verify init behavior."""

        self.payload = payload

    def __enter__(self):
        """Verify enter behavior."""

        return self

    def __exit__(self, exc_type, exc, traceback):
        """Verify exit behavior."""

        return False

    def read(self) -> bytes:
        """Verify read behavior."""

        return json.dumps(self.payload).encode("utf-8")


class StreamlitAPIClientTests(unittest.TestCase):
    """Encapsulates streamlit apiclient tests behavior for migration workflows."""

    def test_recommendations_posts_to_fastapi_endpoint(self) -> None:
        """Verify recommendations posts to fastapi endpoint behavior."""

        payload = [
            {
                "Workflow -> Session -> Mapping -> Transformations": "WF_CUSTOMER -> S_CUSTOMER -> M_CUSTOMER -> MPL_CUSTOMER",
                "Assets": "MPL_CUSTOMER",
                "Failures": "mapplet_nesting",
                "Root Cause": "Nested mapplet.",
                "AI Recommendation": "Flatten logic.",
                "Priority": "High",
                "AI Summary": "Manual migration required.",
            }
        ]
        with patch("api.client.urlopen", return_value=FakeHTTPResponse(payload)) as mocked:
            rows = AIAPIClient("http://api.local").recommendations(max_records=5)

        self.assertEqual(payload, rows)
        request = mocked.call_args.args[0]
        self.assertEqual("http://api.local/api/v1/ai/recommendation", request.full_url)
        self.assertEqual(b'{"Max Records": 5}', request.data)


    def test_recommendations_uses_config_when_no_limit_is_sent(self) -> None:
        """Verify recommendations uses config when no limit is sent behavior."""

        payload = []
        with patch("api.client.urlopen", return_value=FakeHTTPResponse(payload)) as mocked:
            rows = AIAPIClient("http://api.local").recommendations()

        self.assertEqual(payload, rows)
        request = mocked.call_args.args[0]
        self.assertEqual("http://api.local/api/v1/ai/recommendation", request.full_url)
        self.assertEqual(b"{}", request.data)
    def test_evaluation_requires_matrix_shape(self) -> None:
        """Verify evaluation requires matrix shape behavior."""

        with patch("api.client.urlopen", return_value=FakeHTTPResponse({"not_matrix": {}})):
            with self.assertRaises(FastAPIClientError):
                AIAPIClient("http://api.local").evaluation()


if __name__ == "__main__":
    unittest.main()

