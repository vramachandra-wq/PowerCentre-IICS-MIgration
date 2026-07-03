import json
import unittest
from unittest.mock import patch

from api.client import AIAPIClient, FastAPIClientError


class FakeHTTPResponse:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class StreamlitAPIClientTests(unittest.TestCase):
    def test_recommendations_posts_to_fastapi_endpoint(self) -> None:
        payload = [
            {
                "Workflow": "WF_CUSTOMER",
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

    def test_evaluation_requires_matrix_shape(self) -> None:
        with patch("api.client.urlopen", return_value=FakeHTTPResponse({"not_matrix": {}})):
            with self.assertRaises(FastAPIClientError):
                AIAPIClient("http://api.local").evaluation()


if __name__ == "__main__":
    unittest.main()
