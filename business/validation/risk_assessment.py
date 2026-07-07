"""
Module: business/validation/risk_assessment.py

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

from business.validation.readiness_engine import IssueRecord, RemediationReportLoader
from common.config.config import AppConfig


@dataclass(frozen=True)
class RiskAssessmentRecord:
    """
    Represents the RiskAssessmentRecord component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    mapping_name: str
    risk_score: int
    risk_level: str
    top_risk_factor: str


class RiskAssessmentEngine:
    """Scores residual migration risk from remaining unresolved issues only."""

    REPORT_COLUMNS = ["mapping_name", "risk_score", "risk_level", "top_risk_factor"]

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
        self.report_path = self.output_folder / "risk_assessment_report.csv"
        self.loader = RemediationReportLoader(
            self.output_folder,
            scoring_rules_path or Path("common/config/readiness_rules.json"),
        )

    def build_report(self) -> list[RiskAssessmentRecord]:
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

        remaining = self.loader.unresolved_issues()
        before = self.loader.load_before_issues()
        remediation = self.loader.load_remediation_issues()
        mappings = sorted(
            self.loader.mapping_names
            or {issue.mapping_name for issue in [*before, *remaining, *remediation]}
            or {"UNMAPPED_ASSET"}
        )
        records: list[RiskAssessmentRecord] = []
        for mapping in mappings:
            issues = [issue for issue in remaining if issue.mapping_name == mapping]
            scored = [(issue, self._risk_score(issue)) for issue in issues]
            risk_score = sum(score for _, score in scored)
            top_issue = max(scored, key=lambda item: item[1])[0].issue if scored else "none"
            records.append(
                RiskAssessmentRecord(
                    mapping_name=mapping,
                    risk_score=risk_score,
                    risk_level=self._risk_level(risk_score),
                    top_risk_factor=top_issue,
                )
            )
        self.write_report(records)
        if self.logger:
            self.logger.info("Risk assessment report written to %s. rows=%s", self.report_path, len(records))
        return records

    def write_report(self, records: list[RiskAssessmentRecord], report_path: str | Path | None = None) -> None:
        """
        Executes the write_report workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                records (object): Value supplied by the caller and used by the workflow.
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
            writer.writerows(record.__dict__ for record in records)

    def _risk_score(self, issue: IssueRecord) -> int:
        """
        Executes the _risk_score workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                issue (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        risk_factors = self.loader.rules.get("risk_factors", {})
        if issue.issue in risk_factors:
            return int(risk_factors[issue.issue]["score"])
        defaults = self.loader.rules.get("default_risk_score", {})
        return int(defaults.get(issue.severity.upper(), 8))

    def _risk_level(self, score: int) -> str:
        """
        Executes the _risk_level workflow for migration validation and readiness logic.
        
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
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        for band in self.loader.rules.get("risk_levels", []):
            if int(band["min"]) <= score <= int(band["max"]):
                return str(band["level"])
        return "CRITICAL"

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


def build_risk_assessment_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    scoring_rules_path: str | Path | None = None,
) -> list[RiskAssessmentRecord]:
    """
    Executes the build_risk_assessment_report workflow for migration validation and readiness logic.
    
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

    return RiskAssessmentEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        scoring_rules_path=scoring_rules_path,
    ).build_report()
