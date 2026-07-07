"""
Module: api/client.py

Purpose:
    This module supports FastAPI service layer for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the FastAPI service layer area and exposes validation, recommendation, and evaluation results to UI and integration clients. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

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
        """
        Executes the recommendations workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                max_records (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        payload: dict[str, Any] = {}
        if max_records:
            payload["Max Records"] = max_records
        response = self._post("/api/v1/ai/recommendation", payload)
        if not isinstance(response, list):
            raise FastAPIClientError("Recommendation API returned an invalid response shape.")
        return response

    def evaluation(self) -> dict[str, Any]:
        """
        Executes the evaluation workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        response = self._post("/api/v1/ai/evaluation", {})
        if not isinstance(response, dict) or "matrix" not in response:
            raise FastAPIClientError("Evaluation API returned an invalid response shape.")
        return response

    def _post(self, path: str, payload: dict[str, Any]) -> Any:
        """
        Executes the _post workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
                payload (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
