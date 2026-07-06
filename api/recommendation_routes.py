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
