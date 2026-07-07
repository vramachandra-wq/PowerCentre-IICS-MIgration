"""
Module: automation/evaluation_dataset.py

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
        "ai_recommendation",
        "ai_assistance",
        "overall_health_score",
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
                    "ai_recommendation": record.ai_recommendation,
                    "ai_assistance": record.ai_assistance,
                    "overall_health_score": record.overall_health_score,
                    "migration_status": record.migration_status,
                }
            )
        return dataset

    def build_canonical_dataset(self, objects: Iterable[CanonicalEvaluationObject]) -> list[dict[str, object]]:
        """
        Executes the build_canonical_dataset workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                objects (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
                "ai_recommendation": item.remediation.get("ai_recommendation", 0),
                "ai_assistance": item.remediation.get("ai_assistance", 0),
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
                canonical_dataset (object): Value supplied by the caller and used by the workflow.
        
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
            "csv": self.repository.write_csv("evaluation_dataset.csv", dataset, self.FIELDNAMES),
            "json": self.repository.write_json("evaluation_dataset.json", dataset),
        }
