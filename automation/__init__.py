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
    """
    Executes the __getattr__ workflow for automated validation reporting.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
            name (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that builds dashboard, evaluation, summary, and consolidated report artifacts from migration assessment data. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

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
