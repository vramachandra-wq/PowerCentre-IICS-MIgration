"""Automated validation framework package."""

__all__ = [
    "AutomatedValidationFramework",
    "ConsolidatedFindingsBuilder",
    "DashboardDatasetBuilder",
    "EvaluationDatasetBuilder",
    "EvaluationMatrixBuilder",
    "MetricsCalculator",
    "ValidationSummaryBuilder",
]


def __getattr__(name: str):
    if name == "AutomatedValidationFramework":
        from automation.automated_validation_framework import AutomatedValidationFramework

        return AutomatedValidationFramework
    if name == "ConsolidatedFindingsBuilder":
        from automation.consolidated_findings import ConsolidatedFindingsBuilder

        return ConsolidatedFindingsBuilder
    if name == "DashboardDatasetBuilder":
        from automation.dashboard_dataset import DashboardDatasetBuilder

        return DashboardDatasetBuilder
    if name == "EvaluationDatasetBuilder":
        from automation.evaluation_dataset import EvaluationDatasetBuilder

        return EvaluationDatasetBuilder
    if name == "EvaluationMatrixBuilder":
        from automation.evaluation_matrix import EvaluationMatrixBuilder

        return EvaluationMatrixBuilder
    if name == "MetricsCalculator":
        from automation.metrics import MetricsCalculator

        return MetricsCalculator
    if name == "ValidationSummaryBuilder":
        from automation.validation_summary import ValidationSummaryBuilder

        return ValidationSummaryBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
