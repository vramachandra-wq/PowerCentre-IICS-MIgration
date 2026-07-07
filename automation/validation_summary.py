"""
Module: automation/validation_summary.py

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


class ValidationSummaryBuilder:
    """Builds high-level validation readiness metrics."""

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
            "ai_recommendation": sum(row.ai_recommendation for row in rows),
            "ai_assistance": sum(row.ai_assistance for row in rows),
            "validation_pass_rate": self.metrics.pass_rate(passed, failed),
            "validation_failure_rate": self.metrics.failure_rate(passed, failed),
            "auto_fix_percentage": self.metrics.percentage(remediated, len(remediation_rows)),
            "auto_fix_accuracy": self.metrics.percentage(remediated, len(remediation_rows)),
            "ai_recommendation_percentage": self.metrics.percentage(sum(row.ai_recommendation for row in rows), failed),
            "ai_assistance_percentage": self.metrics.percentage(
                sum(row.ai_assistance for row in rows), failed
            ),
            "average_readiness_improvement": self.metrics.average(
                self.metrics.readiness_improvement(row.readiness_before, row.readiness_after) for row in rows
            ),
        }

    def write(self, summary: dict[str, object]) -> Path:
        """
        Executes the write workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return self.repository.write_json("validation_summary.json", summary)

    @staticmethod
    def _overall_risk(score: float) -> str:
        """
        Executes the _overall_risk workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                score (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if score >= 100:
            return "CRITICAL"
        if score >= 60:
            return "HIGH"
        if score >= 25:
            return "MEDIUM"
        return "LOW"
