from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class FastAPIClientError(RuntimeError):
    """Raised when the Streamlit UI cannot retrieve API data."""


@dataclass(frozen=True)
class AIAPIClient:
    """Small HTTP client used by presentation UIs to call the FastAPI app."""

    base_url: str = "http://127.0.0.1:8000"
    timeout_seconds: int = 120

    def recommendations(self, max_records: int | None = None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {}
        if max_records:
            payload["Max Records"] = max_records
        response = self._post("/api/v1/ai/recommendation", payload)
        if not isinstance(response, list):
            raise FastAPIClientError("Recommendation API returned an invalid response shape.")
        return response

    def evaluation(self) -> dict[str, Any]:
        response = self._post("/api/v1/ai/evaluation", {})
        if not isinstance(response, dict) or "matrix" not in response:
            raise FastAPIClientError("Evaluation API returned an invalid response shape.")
        return response

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        url = self.base_url.rstrip("/") + path
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise FastAPIClientError(f"FastAPI request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise FastAPIClientError(
                f"Unable to reach FastAPI at {self.base_url}. Start it with: uvicorn app:create_app --factory --reload"
            ) from exc
        except json.JSONDecodeError as exc:
            raise FastAPIClientError("FastAPI returned malformed JSON.") from exc
