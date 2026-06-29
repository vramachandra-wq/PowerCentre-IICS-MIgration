from __future__ import annotations

from pathlib import Path
from typing import Iterable

from automation.evaluation_matrix import EvaluationMatrixRecord, ReportRepository
from automation.metrics import MetricsCalculator


class ValidationSummaryBuilder:
    """Builds high-level validation readiness metrics."""

    def __init__(self, repository: ReportRepository | None = None) -> None:
        self.repository = repository or ReportRepository()
        self.metrics = MetricsCalculator()

    def build(self, records: Iterable[EvaluationMatrixRecord]) -> dict[str, object]:
        rows = list(records)
        overall_readiness = round(self.metrics.average(row.readiness_after for row in rows))
        average_risk = self.metrics.average(row.risk_score for row in rows)
        passed = sum(row.validation_passed for row in rows)
        failed = sum(row.validation_failed for row in rows)
        remediation_rows = self.repository.read_csv("remediation_report.csv")
        remediated = sum(1 for row in remediation_rows if str(row.get("Auto Fixed", "")).lower() == "true")
        not_remediated = len(remediation_rows) - remediated
        return {
            "overall_readiness": overall_readiness,
            "overall_risk": self._overall_risk(average_risk),
            "total_auto_fixed": remediated,
            "total_remediation_items": len(remediation_rows),
            "total_not_auto_fixed": not_remediated,
            "remaining_issues": sum(row.remaining_issues for row in rows),
            "manual_review": sum(row.manual_review for row in rows),
            "manual_remediation": sum(row.manual_remediation for row in rows),
            "validation_pass_rate": self.metrics.pass_rate(passed, failed),
            "validation_failure_rate": self.metrics.failure_rate(passed, failed),
            "auto_fix_percentage": self.metrics.percentage(remediated, len(remediation_rows)),
            "auto_fix_accuracy": self.metrics.percentage(remediated, len(remediation_rows)),
            "manual_review_percentage": self.metrics.percentage(sum(row.manual_review for row in rows), failed),
            "manual_remediation_percentage": self.metrics.percentage(
                sum(row.manual_remediation for row in rows), failed
            ),
            "average_readiness_improvement": self.metrics.average(
                self.metrics.readiness_improvement(row.readiness_before, row.readiness_after) for row in rows
            ),
        }

    def write(self, summary: dict[str, object]) -> Path:
        return self.repository.write_json("validation_summary.json", summary)

    @staticmethod
    def _overall_risk(score: float) -> str:
        if score >= 100:
            return "CRITICAL"
        if score >= 60:
            return "HIGH"
        if score >= 25:
            return "MEDIUM"
        return "LOW"
