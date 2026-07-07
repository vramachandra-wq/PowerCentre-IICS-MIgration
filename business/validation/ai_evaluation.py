"""
Module: business/validation/ai_evaluation.py

Purpose:
    This module supports migration validation and readiness logic for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the migration validation and readiness logic area and evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from automation.evaluation_matrix import ReportRepository
from business.validation.ai_metrics import AIMetricsCalculator
from business.validation.ai_validation_engine import AIValidationResult
from automation.metrics import MetricsCalculator
 


@dataclass(frozen=True)
class AIEvaluationSummary:
    """
    Represents the AIEvaluationSummary component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    total_evaluations: int
    ml_accuracy: float
    ml_precision: float
    recall: float
    f1_score: float
    average_confidence: float
    model_success_rate: float


class AIEvaluationBuilder:
    """Converts model validation results into executive ML evaluation artifacts."""

    DATASET_FIELDNAMES = [
        "mapping_name",
        "rule_name",
        "ground_truth",
        "ml_decision",
        "confidence",
        "correct",
    ]
    MATRIX_FIELDNAMES = [
        "Total Evaluations",
        "ML Accuracy",
        "ML Precision",
        "Recall",
        "F1 Score",
        "Average Confidence",
        "Model Success Rate",
    ]
    DASHBOARD_FIELDNAMES = MATRIX_FIELDNAMES

    def __init__(self, repository: ReportRepository | None = None, high_confidence_threshold: int = 90) -> None:
        """
        Executes the __init__ workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                repository (object): Value supplied by the caller and used by the workflow.
                high_confidence_threshold (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.repository = repository or ReportRepository()
        self.high_confidence_threshold = high_confidence_threshold

    def build_dataset(self, results: Iterable[AIValidationResult]) -> list[dict[str, Any]]:
        """
        Executes the build_dataset workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                results (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        rows: list[dict[str, Any]] = []
        for result in results:
            ground_truth = AIMetricsCalculator.normalize_decision(result.input.ground_truth)
            ml_decision = AIMetricsCalculator.normalize_decision(result.prediction.decision)
            rows.append(
                {
                    "mapping_name": result.input.mapping_name,
                    "rule_name": result.input.rule_name,
                    "ground_truth": ground_truth,
                    "ml_decision": ml_decision,
                    "confidence": result.prediction.confidence,
                    "correct": str(ground_truth == ml_decision),
                }
            )
        return rows

    def summarize(self, results: list[AIValidationResult], dataset: list[dict[str, Any]]) -> AIEvaluationSummary:
        """
        Executes the summarize workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                results (object): Value supplied by the caller and used by the workflow.
                dataset (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        valid_rows = [row for row in dataset if row["ml_decision"] in {"PASS", "FAIL"}]
        matrix = AIMetricsCalculator.confusion_counts(
            (row["ground_truth"], row["ml_decision"]) for row in valid_rows
        )
        total_evaluations = len(dataset)
        correct = sum(1 for row in dataset if row["correct"] == "True")
        ml_precision = AIMetricsCalculator.precision(matrix)
        recall = AIMetricsCalculator.recall(matrix)
        return AIEvaluationSummary(
            total_evaluations=total_evaluations,
            ml_accuracy=MetricsCalculator.percentage(correct, total_evaluations),
            ml_precision=ml_precision,
            recall=recall,
            f1_score=AIMetricsCalculator.f1_score(ml_precision, recall),
            average_confidence=AIMetricsCalculator.average_confidence(row["confidence"] for row in valid_rows),
            model_success_rate=MetricsCalculator.percentage(len(valid_rows), total_evaluations),
        )

    def write(self, dataset: list[dict[str, Any]], summary: AIEvaluationSummary) -> dict[str, Path]:
        """
        Executes the write workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                dataset (object): Value supplied by the caller and used by the workflow.
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        matrix_row = self._summary_row(summary)
        outputs = {
            "dataset": self.repository.write_csv("ai_evaluation_dataset.csv", dataset, self.DATASET_FIELDNAMES),
            "matrix": self.repository.write_csv("ai_evaluation_matrix.csv", [matrix_row], self.MATRIX_FIELDNAMES),
            "dashboard": self.repository.write_csv("ai_dashboard_dataset.csv", [matrix_row], self.DASHBOARD_FIELDNAMES),
            "json": self.repository.write_json(
                "ai_evaluation_summary.json",
                {"matrix": matrix_row, "dashboard": matrix_row},
            ),
        }
        extended_dashboard = self._extended_dashboard_rows(matrix_row)
        if extended_dashboard:
            base_fields = list(extended_dashboard[0].keys())
            outputs["extended_dashboard"] = self.repository.write_csv(
                "dashboard_dataset.csv", extended_dashboard, base_fields
            )
        return outputs

    def _extended_dashboard_rows(self, dashboard_row: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Executes the _extended_dashboard_rows workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                dashboard_row (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        rows = self.repository.read_csv("automation/dashboard_dataset.csv")
        if not rows:
            return []
        return [{**row, **dashboard_row} for row in rows]

    @staticmethod
    def _summary_row(summary: AIEvaluationSummary) -> dict[str, Any]:
        """
        Executes the _summary_row workflow for migration validation and readiness logic.
        
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
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return {
            "Total Evaluations": summary.total_evaluations,
            "ML Accuracy": summary.ml_accuracy,
            "ML Precision": summary.ml_precision,
            "Recall": summary.recall,
            "F1 Score": summary.f1_score,
            "Average Confidence": summary.average_confidence,
            "Model Success Rate": summary.model_success_rate,
        }
