"""
Module: automation/dashboard_dataset.py

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

    def build(self, records: Iterable[EvaluationMatrixRecord]) -> list[dict[str, object]]:
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
        """
        Executes the write workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                dataset (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return {
            "csv": self.repository.write_csv("dashboard_dataset.csv", dataset, self.FIELDNAMES),
            "json": self.repository.write_json("dashboard_dataset.json", dataset),
        }
