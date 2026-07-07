"""
Support evaluation routes for API endpoints and service integration.
Keeps request handling and AI workflow access organized.
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
    """Return evaluation for the migration workflow."""

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


