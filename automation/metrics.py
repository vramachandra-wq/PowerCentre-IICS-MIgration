"""
Module: automation/metrics.py

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

import re
from collections import Counter
from typing import Iterable, Mapping


class MetricsCalculator:
    """Reusable calculations for automation-level validation metrics."""

    @staticmethod
    def percentage(numerator: int | float, denominator: int | float) -> float:
        """
        Executes the percentage workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                numerator (object): Value supplied by the caller and used by the workflow.
                denominator (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not denominator:
            return 0.0
        value = (float(numerator) / float(denominator)) * 100
        return round(max(0.0, min(value, 100.0)), 2)

    @staticmethod
    def average(values: Iterable[int | float]) -> float:
        """
        Executes the average workflow for automated validation reporting.
        
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
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        numbers = [float(value) for value in values]
        if not numbers:
            return 0.0
        return round(sum(numbers) / len(numbers), 2)

    @staticmethod
    def pass_rate(passed: int, failed: int) -> float:
        """
        Executes the pass_rate workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                passed (object): Value supplied by the caller and used by the workflow.
                failed (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return MetricsCalculator.percentage(passed, passed + failed)

    @staticmethod
    def failure_rate(passed: int, failed: int) -> float:
        """
        Executes the failure_rate workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                passed (object): Value supplied by the caller and used by the workflow.
                failed (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return MetricsCalculator.percentage(failed, passed + failed)

    @staticmethod
    def readiness_improvement(readiness_before: int | float, readiness_after: int | float) -> float:
        """
        Executes the readiness_improvement workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                readiness_before (object): Value supplied by the caller and used by the workflow.
                readiness_after (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return round(float(readiness_after) - float(readiness_before), 2)

    @staticmethod
    def risk_reduction(risk_before: int | float, risk_after: int | float) -> float:
        """
        Executes the risk_reduction workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                risk_before (object): Value supplied by the caller and used by the workflow.
                risk_after (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return round(float(risk_before) - float(risk_after), 2)

    @staticmethod
    def distribution(values: Iterable[str]) -> dict[str, int]:
        """
        Executes the distribution workflow for automated validation reporting.
        
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
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return dict(Counter(value or "UNKNOWN" for value in values))

    @staticmethod
    def validation_coverage(rules_executed: int, mapping_count: int) -> float:
        """
        Executes the validation_coverage workflow for automated validation reporting.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                rules_executed (object): Value supplied by the caller and used by the workflow.
                mapping_count (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return MetricsCalculator.percentage(rules_executed, mapping_count) if mapping_count else 0.0

    @staticmethod
    def most_common(values: Iterable[str]) -> str:
        """
        Executes the most_common workflow for automated validation reporting.
        
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
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        counter = Counter(value for value in values if value)
        if not counter:
            return "none"
        return counter.most_common(1)[0][0]

    @staticmethod
    def sum_field(rows: Iterable[Mapping[str, object]], field: str) -> int:
        """
        Executes the sum_field workflow for automated validation reporting.
        
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

        return sum(MetricsCalculator.to_int(row.get(field, 0)) for row in rows)

    @staticmethod
    def to_int(value: object) -> int:
        """
        Executes the to_int workflow for automated validation reporting.
        
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
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        try:
            return int(float(str(value or "0").strip()))
        except ValueError:
            return 0

    @staticmethod
    def to_float(value: object) -> float:
        """
        Executes the to_float workflow for automated validation reporting.
        
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
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        try:
            return float(str(value or "0").strip())
        except ValueError:
            return 0.0

    @staticmethod
    def normalize_text(value: object) -> str:
        """
        Executes the normalize_text workflow for automated validation reporting.
        
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
            This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
