"""
Module: api/recommendation_routes.py

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

from api.ai_services import AIRecommendationAPIService, APIReportError
from api.dependencies import get_logger, get_repository
from api.schemas import RecommendationRequest, RecommendationResponse
from automation.evaluation_matrix import ReportRepository

router = APIRouter(prefix="/api/v1/ai", tags=["AI"])


@router.post("/recommendation", response_model=list[RecommendationResponse], response_model_by_alias=True)
def create_recommendation(
    request_body: RecommendationRequest | None = None,
    repository: ReportRepository = Depends(get_repository),
    logger=Depends(get_logger),
) -> list[dict[str, object]]:
    """
    Executes the create_recommendation workflow for FastAPI service layer.
    
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
    logger.info("API request started: POST /api/v1/ai/recommendation")
    if request_body and request_body.validation_report is not None and not request_body.validation_report:
        raise HTTPException(status_code=422, detail="Validation Report cannot be empty when provided.")
    try:
        service = AIRecommendationAPIService(repository=repository, logger=logger)
        rows = service.recommend(max_records=request_body.max_records if request_body else None)
    except APIReportError as exc:
        logger.error("AI recommendation API request failed: %s", exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    logger.info("API request completed: POST /api/v1/ai/recommendation rows=%s elapsed_ms=%s", len(rows), elapsed)
    return rows
