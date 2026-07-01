from __future__ import annotations

from pathlib import Path
from typing import Iterable

from automation.evaluation_matrix import CanonicalEvaluationObject, EvaluationMatrixRecord, ReportRepository


class EvaluationDatasetBuilder:
    """Creates compact rule-based evaluation datasets from matrix records."""

    FIELDNAMES = [
        "workflow",
        "mapping",
        "complexity",
        "risk_score",
        "risk_category",
        "readiness_after",
        "validation_failed",
        "auto_fixable_issues",
        "auto_fixed",
        "remaining_unresolved",
        "top_risk_factor",
        "blocking_issue_count",
        "manual_review",
        "manual_remediation",
        "overall_health_score",
        "migration_status",
    ]

    def __init__(self, repository: ReportRepository | None = None) -> None:
        self.repository = repository or ReportRepository()

    def build(self, records: Iterable[EvaluationMatrixRecord]) -> list[dict[str, object]]:
        dataset: list[dict[str, object]] = []
        for record in records:
            dataset.append(
                {
                    "workflow": record.workflow,
                    "mapping": record.mapping,
                    "complexity": record.complexity_category,
                    "risk_score": record.risk_after,
                    "risk_category": record.risk_category,
                    "readiness_after": record.readiness_after,
                    "validation_failed": record.validation_failed,
                    "auto_fixable_issues": record.auto_fixable_issues,
                    "auto_fixed": record.auto_fixed,
                    "remaining_unresolved": record.remaining_unresolved,
                    "top_risk_factor": record.top_risk_factor,
                    "blocking_issue_count": record.blocking_issues,
                    "manual_review": record.manual_review,
                    "manual_remediation": record.manual_remediation,
                    "overall_health_score": record.overall_health_score,
                    "migration_status": record.migration_status,
                }
            )
        return dataset

    def build_canonical_dataset(self, objects: Iterable[CanonicalEvaluationObject]) -> list[dict[str, object]]:
        return [
            {
                "workflow": item.workflow,
                "mapping": item.mapping,
                "complexity": item.complexity.get("category", ""),
                "risk_score": item.risk.get("after", 0),
                "risk_category": item.risk.get("category", ""),
                "readiness_after": item.readiness.get("after", 0),
                "validation_failed": item.validation.get("failed", 0),
                "auto_fixable_issues": item.remediation.get("auto_fixable_issues", 0),
                "auto_fixed": item.remediation.get("auto_fixed", 0),
                "remaining_unresolved": item.remediation.get("remaining", 0),
                "top_risk_factor": item.risk.get("top_factor", "none"),
                "blocking_issue_count": item.remediation.get("remaining", 0),
                "manual_review": item.remediation.get("manual_review", 0),
                "manual_remediation": item.remediation.get("manual_remediation", 0),
                "overall_health_score": item.risk.get("overall_health_score", 0),
                "migration_status": "",
            }
            for item in objects
        ]

    def write(
        self,
        dataset: list[dict[str, object]],
        canonical_dataset: list[dict[str, object]] | None = None,
    ) -> dict[str, Path]:
        return {
            "csv": self.repository.write_csv("evaluation_dataset.csv", dataset, self.FIELDNAMES),
            "json": self.repository.write_json("evaluation_dataset.json", dataset),
        }
