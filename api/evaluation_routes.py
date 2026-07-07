"""
Module: api/evaluation_routes.py

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

import time

from fastapi import APIRouter, Depends, HTTPException

from api.ai_services import AIEvaluationAPIService, APIReportError
from api.dependencies import get_logger, get_repository
from api.schemas import EvaluationRequest, EvaluationResponse
from automation.evaluation_matrix import ReportRepository

router = APIRouter(prefix="/api/v1/ai", tags=["AI"])


@router.post("/evaluation", response_model=EvaluationResponse, response_model_by_alias=True)
def get_evaluation(
    request_body: EvaluationRequest | None = None,
    repository: ReportRepository = Depends(get_repository),
    logger=Depends(get_logger),
) -> dict[str, object]:
    """
    Executes the get_evaluation workflow for FastAPI service layer.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
            request_body (object): Value supplied by the caller and used by the workflow.
            repository (object): Value supplied by the caller and used by the workflow.
            logger (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    started = time.perf_counter()
    logger.info("API request started: POST /api/v1/ai/evaluation")
    try:
        response = AIEvaluationAPIService(repository=repository, logger=logger).evaluation(
            refresh=bool(request_body.refresh) if request_body else False
        )
    except APIReportError as exc:
        logger.error("AI evaluation API request failed: %s", exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    logger.info("API request completed: POST /api/v1/ai/evaluation elapsed_ms=%s", elapsed)
    return response


