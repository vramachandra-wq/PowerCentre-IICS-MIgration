from __future__ import annotations

from pathlib import Path
from typing import Iterable

from automation.evaluation_matrix import EvaluationMatrixRecord, ReportRepository
from automation.metrics import MetricsCalculator


class DashboardDatasetBuilder:
    """Creates Power BI friendly dashboard extracts."""

    FIELDNAMES = [
        "workflow",
        "mapping_name",
        "failures",
        "readiness_before",
        "readiness_after",
        "risk_before",
        "risk_after",
        "overall_health_score",
        "auto_fix_success_rate",
        "ai_recommendation_count",
        "ai_assistance_count",
        "migration_status",
    ]

    def __init__(self, repository: ReportRepository | None = None) -> None:
        self.repository = repository or ReportRepository()
        self.metrics = MetricsCalculator()

    def build(self, records: Iterable[EvaluationMatrixRecord]) -> list[dict[str, object]]:
        dataset: list[dict[str, object]] = []
        for record in records:
            dataset.append(
                {
                    "workflow": record.workflow,
                    "mapping_name": record.mapping,
                    "failures": record.validation_failed,
                    "readiness_before": record.readiness_before,
                    "readiness_after": record.readiness_after,
                    "risk_before": record.risk_before,
                    "risk_after": record.risk_after,
                    "overall_health_score": record.overall_health_score,
                    "auto_fix_success_rate": record.auto_fix_success_rate,
                    "ai_recommendation_count": record.ai_recommendation,
                    "ai_assistance_count": record.ai_assistance,
                    "migration_status": record.migration_status,
                }
            )
        return dataset

    def write(self, dataset: list[dict[str, object]]) -> dict[str, Path]:
        return {
            "csv": self.repository.write_csv("dashboard_dataset.csv", dataset, self.FIELDNAMES),
            "json": self.repository.write_json("dashboard_dataset.json", dataset),
        }
