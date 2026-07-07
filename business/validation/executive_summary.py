"""
Module: business/validation/executive_summary.py

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

import csv
from dataclasses import dataclass
from pathlib import Path

from business.validation.readiness_engine import MigrationReadinessEngine, ReadinessRecord
from business.validation.remediation_effectiveness import (
    RemediationEffectivenessEngine,
    RemediationEffectivenessRecord,
)
from business.validation.risk_assessment import RiskAssessmentEngine, RiskAssessmentRecord
from common.config.config import AppConfig


@dataclass(frozen=True)
class ExecutiveMetric:
    """
    Represents the ExecutiveMetric component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    metric: str
    value: str


class ExecutiveSummaryEngine:
    """Builds stakeholder-friendly summary metrics from post-remediation analytical reports."""

    REPORT_COLUMNS = ["metric", "value"]

    def __init__(
        self,
        config: AppConfig | None = None,
        logger=None,
        output_folder: str | Path | None = None,
        scoring_rules_path: str | Path | None = None,
    ) -> None:
        """
        Executes the __init__ workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                config (object): Value supplied by the caller and used by the workflow.
                logger (object): Value supplied by the caller and used by the workflow.
                output_folder (object): Value supplied by the caller and used by the workflow.
                scoring_rules_path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        configured_output = output_folder or (config.paths.output_folder if config else "output")
        self.output_folder = self._resolve_path(configured_output)
        self.report_path = self.output_folder / "post_remediation_executive_summary_report.csv"
        self.scoring_rules_path = scoring_rules_path

    def build_report(self) -> list[ExecutiveMetric]:
        """
        Executes the build_report workflow for migration validation and readiness logic.
        
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

        readiness = MigrationReadinessEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
            scoring_rules_path=self.scoring_rules_path,
        ).build_report()
        risk = RiskAssessmentEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
            scoring_rules_path=self.scoring_rules_path,
        ).build_report()
        effectiveness = RemediationEffectivenessEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
            scoring_rules_path=self.scoring_rules_path,
        ).build_report()

        metrics = self._metrics(readiness, risk, effectiveness)
        self.write_report(metrics)
        if self.logger:
            self.logger.info("Executive summary report written to %s. rows=%s", self.report_path, len(metrics))
        return metrics

    def write_report(self, metrics: list[ExecutiveMetric], report_path: str | Path | None = None) -> None:
        """
        Executes the write_report workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                metrics (object): Value supplied by the caller and used by the workflow.
                report_path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        path = self._resolve_path(report_path or self.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            csv_file = path.open("w", newline="", encoding="utf-8")
        except PermissionError:
            fallback_path = path.with_name(f"{path.stem}_latest{path.suffix}")
            csv_file = fallback_path.open("w", newline="", encoding="utf-8")
        with csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(metric.__dict__ for metric in metrics)

    @staticmethod
    def _metrics(
        readiness: list[ReadinessRecord],
        risk: list[RiskAssessmentRecord],
        effectiveness: list[RemediationEffectivenessRecord],
    ) -> list[ExecutiveMetric]:
        """
        Executes the _metrics workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                readiness (object): Value supplied by the caller and used by the workflow.
                risk (object): Value supplied by the caller and used by the workflow.
                effectiveness (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        total_found = sum(record.issues_found for record in readiness)
        total_auto_fixed = sum(record.issues_auto_fixed for record in readiness)
        total_remaining = sum(record.issues_remaining for record in readiness)
        average_readiness = (
            round(sum(record.readiness_after for record in readiness) / len(readiness), 2)
            if readiness
            else 0.0
        )
        highest_risk = max(risk, key=lambda record: record.risk_score, default=None)
        lowest_readiness = min(readiness, key=lambda record: record.readiness_after, default=None)
        ready_count = len([record for record in readiness if record.readiness_category == "READY"])
        ai_assistance_count = len(
            [
                record
                for record in effectiveness
                if record.ai_recommendation > 0 or record.ai_assistance > 0
            ]
        )
        auto_fix_rate = round((total_auto_fixed / total_found) * 100, 2) if total_found else 0.0
        ai_assistance_effort_reduction = auto_fix_rate

        return [
            ExecutiveMetric("Total Mappings Analyzed", str(len(readiness))),
            ExecutiveMetric("Total Issues Found", str(total_found)),
            ExecutiveMetric("Total Issues Auto Fixed", str(total_auto_fixed)),
            ExecutiveMetric("Total Issues Remaining", str(total_remaining)),
            ExecutiveMetric("Auto Fix Rate", f"{auto_fix_rate}%"),
            ExecutiveMetric("Average Readiness Score", str(average_readiness)),
            ExecutiveMetric(
                "Highest Risk Mapping",
                f"{highest_risk.mapping_name} ({highest_risk.risk_level}, {highest_risk.risk_score})"
                if highest_risk
                else "",
            ),
            ExecutiveMetric(
                "Lowest Readiness Mapping",
                f"{lowest_readiness.mapping_name} ({lowest_readiness.readiness_after})"
                if lowest_readiness
                else "",
            ),
            ExecutiveMetric("Mappings Ready for Migration", str(ready_count)),
            ExecutiveMetric("Mappings Requiring AI Assistance", str(ai_assistance_count)),
            ExecutiveMetric("Estimated AI Assistance Effort Reduction", f"{ai_assistance_effort_reduction}%"),
        ]

    def _resolve_path(self, path: str | Path) -> Path:
        """
        Executes the _resolve_path workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def build_executive_summary_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    scoring_rules_path: str | Path | None = None,
) -> list[ExecutiveMetric]:
    """
    Executes the build_executive_summary_report workflow for migration validation and readiness logic.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
            config (object): Value supplied by the caller and used by the workflow.
            logger (object): Value supplied by the caller and used by the workflow.
            output_folder (object): Value supplied by the caller and used by the workflow.
            scoring_rules_path (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    return ExecutiveSummaryEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        scoring_rules_path=scoring_rules_path,
    ).build_report()
