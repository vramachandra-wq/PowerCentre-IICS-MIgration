"""
Support ai assistance service for automation data and validation workflows.
Prepares metrics, findings, and AI assistance outputs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from automation.evaluation_matrix import ReportRepository
from automation.ai.llm_client import RecommendationModelClient
from automation.ai.recommendation_engine import RecommendationEngine
from automation.ai.recommendation_models import AIRecommendationConfig, RecommendationResult


class AIRecommendationService:
    """Coordinates service operations for migration workflows."""

    FIELDNAMES = [
        "Workflow -> Session -> Mapping -> Transformations",
        "Assets",
        "Failures",
        "Root Cause",
        "AI Recommendation",
        "Priority",
        "AI Summary",
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
        """Initialize migration data for the migration workflow."""

        self.repository = repository or ReportRepository()
        self.config = config or AIRecommendationConfig()
        self.engine = RecommendationEngine(self.repository, self.config, client, logger)

    def run(self) -> tuple[list[RecommendationResult], Path]:
        """Run migration data for the migration workflow."""

        results = self.engine.recommend() if self.config.enabled else []
        return results, self.write(results)

    def write(self, results: list[RecommendationResult]) -> Path:
        # Keep the CSV column order aligned with the Streamlit and API table order.
        """Handle write using the provided results."""

        return self.repository.write_csv(
            "ai_recommendation_report.csv",
            [self._row(result) for result in results],
            self.FIELDNAMES,
        )

    @staticmethod
    def _row(result: RecommendationResult) -> dict[str, Any]:
        """Handle row using the provided result."""

        failure = result.failure
        recommendation = result.recommendation
        # The hierarchy column intentionally combines the workflow path into one field.
        return {
            "Workflow -> Session -> Mapping -> Transformations": AIRecommendationService.hierarchy(failure),
            "Assets": failure.object_name,
            "Failures": failure.failure_type,
            "Root Cause": recommendation.root_cause,
            "AI Recommendation": recommendation.recommendation,
            "Priority": recommendation.priority,
            "AI Summary": recommendation.summary,
            "Severity": failure.severity,
            "Validation Rule": failure.validation_rule,
            "Confidence": recommendation.confidence,
            "Processing Time": result.processing_time_ms,
            "Auto Fix Status": failure.auto_fix_status,
            "Error": result.error,
        }

    @staticmethod
    def hierarchy(failure: RecommendationResult | Any) -> str:
        """Handle hierarchy using the provided failure."""
        record = failure.failure if isinstance(failure, RecommendationResult) else failure
        parts = [
            record.workflow,
            getattr(record, "session", ""),
            record.mapping,
            record.transformation,
        ]
        return " -> ".join(str(part) for part in parts if part)
