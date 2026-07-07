"""
Module: business/validation/ai_metrics.py

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
from typing import Iterable

from automation.metrics import MetricsCalculator


@dataclass(frozen=True)
class BinaryConfusionMatrix:
    """Confusion matrix for PASS/FAIL model decisions against rule-engine ground truth."""

    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def total(self) -> int:
        """
        Executes the total workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return self.tp + self.tn + self.fp + self.fn

    @property
    def correct(self) -> int:
        """
        Executes the correct workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return self.tp + self.tn


class AIMetricsCalculator:
    """Reusable AI evaluation metric calculations."""

    @staticmethod
    def confusion_counts(pairs: Iterable[tuple[str, str]]) -> BinaryConfusionMatrix:
        """
        Executes the confusion_counts workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                pairs (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        tp = tn = fp = fn = 0
        for ground_truth, predicted_decision in pairs:
            expected = AIMetricsCalculator.normalize_decision(ground_truth)
            predicted = AIMetricsCalculator.normalize_decision(predicted_decision)
            if expected == "FAIL" and predicted == "FAIL":
                tp += 1
            elif expected == "PASS" and predicted == "PASS":
                tn += 1
            elif expected == "PASS" and predicted == "FAIL":
                fp += 1
            elif expected == "FAIL" and predicted == "PASS":
                fn += 1
        return BinaryConfusionMatrix(tp=tp, tn=tn, fp=fp, fn=fn)

    @staticmethod
    def precision(matrix: BinaryConfusionMatrix) -> float:
        """
        Executes the precision workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                matrix (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return MetricsCalculator.percentage(matrix.tp, matrix.tp + matrix.fp)

    @staticmethod
    def recall(matrix: BinaryConfusionMatrix) -> float:
        """
        Executes the recall workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                matrix (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return MetricsCalculator.percentage(matrix.tp, matrix.tp + matrix.fn)

    @staticmethod
    def f1_score(precision: float, recall: float) -> float:
        """
        Executes the f1_score workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                precision (object): Value supplied by the caller and used by the workflow.
                recall (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if precision + recall == 0:
            return 0.0
        return round((2 * precision * recall) / (precision + recall), 2)

    @staticmethod
    def average_confidence(values: Iterable[int | float]) -> float:
        """
        Executes the average_confidence workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                values (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return MetricsCalculator.average(values)

    @staticmethod
    def normalize_decision(value: object) -> str:
        """
        Executes the normalize_decision workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        normalized = str(value or "").strip().upper()
        if normalized in {"PASS", "PASSED", "READY", "RESOLVED", "TRUE", "YES"}:
            return "PASS"
        if normalized in {"FAIL", "FAILED", "NOT_READY", "NOT READY", "OPEN", "FALSE", "NO"}:
            return "FAIL"
        return normalized or "UNKNOWN"
