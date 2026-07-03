from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from automation.evaluation_matrix import ReportRepository
from automation.ai.llm_client import RecommendationModelClient
from automation.ai.recommendation_engine import RecommendationEngine
from automation.ai.recommendation_models import AIRecommendationConfig, RecommendationResult


class AIRecommendationService:
    """Coordinates recommendation generation and report output."""

    FIELDNAMES = [
        "Workflow",
        "Failures",
        "Root Cause",
        "AI Recommendation",
        "Priority",
        "AI Summary",
        "Mapping Name",
        "Transformation",
        "Severity",
        "Validation Rule",
        "Confidence",
        "Processing Time",
        "Auto Fix Status",
        "Error",
    ]

    def __init__(
        self,
        repository: ReportRepository | None = None,
        config: AIRecommendationConfig | None = None,
        client: RecommendationModelClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.repository = repository or ReportRepository()
        self.config = config or AIRecommendationConfig()
        self.engine = RecommendationEngine(self.repository, self.config, client, logger)

    def run(self) -> tuple[list[RecommendationResult], Path]:
        results = self.engine.recommend() if self.config.enabled else []
        return results, self.write(results)

    def write(self, results: list[RecommendationResult]) -> Path:
        return self.repository.write_csv(
            "ai_recommendation_report.csv",
            [self._row(result) for result in results],
            self.FIELDNAMES,
        )

    @staticmethod
    def _row(result: RecommendationResult) -> dict[str, Any]:
        failure = result.failure
        recommendation = result.recommendation
        return {
            "Workflow": failure.workflow,
            "Failures": failure.failure_type,
            "Root Cause": recommendation.root_cause,
            "AI Recommendation": recommendation.recommendation,
            "Priority": recommendation.priority,
            "AI Summary": recommendation.summary,
            "Mapping Name": failure.mapping,
            "Transformation": failure.transformation,
            "Severity": failure.severity,
            "Validation Rule": failure.validation_rule,
            "Confidence": recommendation.confidence,
            "Processing Time": result.processing_time_ms,
            "Auto Fix Status": failure.auto_fix_status,
            "Error": result.error,
        }
