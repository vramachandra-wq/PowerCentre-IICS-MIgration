"""
Module: automation/consolidated_findings.py

Purpose:
    This module supports automated validation reporting for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the automated validation reporting area and builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from automation.evaluation_matrix import EvaluationMatrixRecord, ReportRepository
from automation.metrics import MetricsCalculator


class ConsolidatedFindingsBuilder:
    """Aggregates mapping-level records into a portfolio-level findings report."""

    def __init__(self, repository: ReportRepository | None = None) -> None:
        """
        Executes the __init__ workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                repository (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.repository = repository or ReportRepository()
        self.metrics = MetricsCalculator()

    def build(self, records: Iterable[EvaluationMatrixRecord]) -> dict[str, object]:
        """
        Executes the build workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                records (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
            "total_ai_recommendations": sum(row.ai_recommendation for row in rows),
            "total_ai_assistance": sum(row.ai_assistance for row in rows),
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
        """
        Executes the write workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                findings (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return self.repository.write_json("consolidated_findings.json", findings)

    @staticmethod
    def _most_common_issue(rows: list[dict[str, str]], token: str) -> str:
        """
        Executes the _most_common_issue workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                rows (object): Value supplied by the caller and used by the workflow.
                token (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return MetricsCalculator.most_common(
            row.get("Issue", "") for row in rows if token in row.get("Issue", "").lower()
        )

    @staticmethod
    def _most_common_transformation_issue(rows: list[dict[str, str]]) -> str:
        """
        Executes the _most_common_transformation_issue workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                rows (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return MetricsCalculator.most_common(row.get("transformation_type", "") for row in rows)

    @staticmethod
    def _mapping_by_max(rows: list[EvaluationMatrixRecord], field: str) -> str:
        """
        Executes the _mapping_by_max workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                rows (object): Value supplied by the caller and used by the workflow.
                field (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not rows:
            return "none"
        return max(rows, key=lambda row: getattr(row, field)).mapping

    @staticmethod
    def _mapping_by_min(rows: list[EvaluationMatrixRecord], field: str) -> str:
        """
        Executes the _mapping_by_min workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                rows (object): Value supplied by the caller and used by the workflow.
                field (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not rows:
            return "none"
        return min(rows, key=lambda row: getattr(row, field)).mapping
