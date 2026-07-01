from __future__ import annotations

from pathlib import Path
from typing import Iterable

from automation.evaluation_matrix import EvaluationMatrixRecord, ReportRepository
from automation.metrics import MetricsCalculator


class ConsolidatedFindingsBuilder:
    """Aggregates mapping-level records into a portfolio-level findings report."""

    def __init__(self, repository: ReportRepository | None = None) -> None:
        self.repository = repository or ReportRepository()
        self.metrics = MetricsCalculator()

    def build(self, records: Iterable[EvaluationMatrixRecord]) -> dict[str, object]:
        rows = list(records)
        validation_rows = self.repository.read_csv("validation_report.csv")
        datatype_rows = self.repository.read_csv("datatype_mismatch_report.csv")
        remediation_rows = self.repository.read_csv("remediation_report.csv")
        transformations = self.repository.read_csv("metadata_tables/transformations.csv")
        remediated = sum(1 for row in remediation_rows if row.get("Auto Fixed", "").lower() == "true")

        readiness_after = [row.readiness_after for row in rows]
        complexity_scores = [row.complexity_score for row in rows]
        risk_scores = [row.risk_score for row in rows]

        return {
            "total_xml_files": len({row.xml_name for row in rows if row.xml_name}),
            "total_workflows": len({row.workflow for row in rows if row.workflow}),
            "total_sessions": len({row.session for row in rows if row.session}),
            "total_mappings": len(rows),
            "total_sources": sum(row.source_count for row in rows),
            "total_targets": sum(row.target_count for row in rows),
            "total_transformations": sum(row.transformation_count for row in rows),
            "total_validation_rules_executed": sum(row.validation_passed + row.validation_failed for row in rows),
            "total_validation_failures": sum(row.validation_failed for row in rows),
            "total_validation_passed": sum(row.validation_passed for row in rows),
            "total_auto_fixed": remediated,
            "total_remediation_items": len(remediation_rows),
            "total_not_auto_fixed": len(remediation_rows) - remediated,
            "total_remaining_issues": sum(row.remaining_issues for row in rows),
            "total_manual_reviews": sum(row.manual_review for row in rows),
            "total_manual_remediation": sum(row.manual_remediation for row in rows),
            "average_complexity": self.metrics.average(complexity_scores),
            "average_readiness_before": self.metrics.average(row.readiness_before for row in rows),
            "average_readiness_after": self.metrics.average(readiness_after),
            "average_risk_score": self.metrics.average(risk_scores),
            "most_common_validation_issue": self.metrics.most_common(row.get("Issue", "") for row in validation_rows),
            "most_common_datatype_issue": self.metrics.most_common(row.get("issue_type", "") for row in datatype_rows),
            "most_common_runtime_issue": self._most_common_issue(validation_rows, "runtime"),
            "most_common_sql_issue": self._most_common_issue(validation_rows, "sql"),
            "most_common_transformation_issue": self._most_common_transformation_issue(transformations),
            "highest_risk_mapping": self._mapping_by_max(rows, "risk_score"),
            "highest_complexity_mapping": self._mapping_by_max(rows, "complexity_score"),
            "highest_readiness_mapping": self._mapping_by_max(rows, "readiness_after"),
            "lowest_readiness_mapping": self._mapping_by_min(rows, "readiness_after"),
            "complexity_distribution": self.metrics.distribution(row.complexity_category for row in rows),
            "transformation_distribution": self.metrics.distribution(
                row.get("transformation_type", "UNKNOWN") for row in transformations
            ),
        }

    def write(self, findings: dict[str, object]) -> Path:
        return self.repository.write_json("consolidated_findings.json", findings)

    @staticmethod
    def _most_common_issue(rows: list[dict[str, str]], token: str) -> str:
        return MetricsCalculator.most_common(
            row.get("Issue", "") for row in rows if token in row.get("Issue", "").lower()
        )

    @staticmethod
    def _most_common_transformation_issue(rows: list[dict[str, str]]) -> str:
        return MetricsCalculator.most_common(row.get("transformation_type", "") for row in rows)

    @staticmethod
    def _mapping_by_max(rows: list[EvaluationMatrixRecord], field: str) -> str:
        if not rows:
            return "none"
        return max(rows, key=lambda row: getattr(row, field)).mapping

    @staticmethod
    def _mapping_by_min(rows: list[EvaluationMatrixRecord], field: str) -> str:
        if not rows:
            return "none"
        return min(rows, key=lambda row: getattr(row, field)).mapping
