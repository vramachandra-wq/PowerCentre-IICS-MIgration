from __future__ import annotations

from pathlib import Path
from typing import Iterable

from automation.evaluation_matrix import EvaluationMatrixRecord, ReportRepository
from automation.metrics import MetricsCalculator


class DashboardDatasetBuilder:
    """Creates Power BI friendly dashboard extracts."""

    FIELDNAMES = [
        "xml_name",
        "mapping_name",
        "complexity_category",
        "complexity_score",
        "readiness_before",
        "readiness_after",
        "readiness_improvement",
        "risk_category",
        "risk_score",
        "validation_failed",
        "auto_fixed",
        "remaining_issues",
        "manual_review",
        "manual_remediation",
        "auto_fix_success_rate",
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
                    "xml_name": record.xml_name,
                    "mapping_name": record.mapping,
                    "complexity_category": record.complexity_category,
                    "complexity_score": record.complexity_score,
                    "readiness_before": record.readiness_before,
                    "readiness_after": record.readiness_after,
                    "readiness_improvement": self.metrics.readiness_improvement(
                        record.readiness_before, record.readiness_after
                    ),
                    "risk_category": record.risk_category,
                    "risk_score": record.risk_score,
                    "validation_failed": record.validation_failed,
                    "auto_fixed": record.auto_fixed,
                    "remaining_issues": record.remaining_issues,
                    "manual_review": record.manual_review,
                    "manual_remediation": record.manual_remediation,
                    "auto_fix_success_rate": record.auto_fix_success_rate,
                    "migration_status": record.migration_status,
                }
            )
        return dataset

    def write(self, dataset: list[dict[str, object]]) -> dict[str, Path]:
        return {
            "csv": self.repository.write_csv("dashboard_dataset.csv", dataset, self.FIELDNAMES),
            "json": self.repository.write_json("dashboard_dataset.json", dataset),
        }
