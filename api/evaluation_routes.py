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
    started = time.perf_counter()
    logger.info("API request started: POST /api/v1/ai/evaluation")
    if request_body and request_body.refresh:
        raise HTTPException(
            status_code=400,
            detail="AI evaluation endpoint reuses existing evaluation reports and does not regenerate them.",
        )
    try:
        response = AIEvaluationAPIService(repository=repository, logger=logger).evaluation()
    except APIReportError as exc:
        logger.error("AI evaluation API request failed: %s", exc)
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    elapsed = int((time.perf_counter() - started) * 1000)
    logger.info("API request completed: POST /api/v1/ai/evaluation elapsed_ms=%s", elapsed)
    return response
