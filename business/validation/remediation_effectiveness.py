"""
Module: business/validation/remediation_effectiveness.py

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

from business.validation.readiness_engine import RemediationReportLoader
from common.config.config import AppConfig


@dataclass(frozen=True)
class RemediationEffectivenessRecord:
    """
    Represents the RemediationEffectivenessRecord component in the migration validation and readiness logic area.
    
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
    issues_found: int
    auto_fixed: int
    ai_recommendation: int
    ai_assistance: int
    auto_fix_percentage: float


class RemediationEffectivenessEngine:
    """Calculates measurable automation lift from remediation outputs."""

    REPORT_COLUMNS = [
        "mapping_name",
        "issues_found",
        "auto_fixed",
        "ai_recommendation",
        "ai_assistance",
        "auto_fix_percentage",
    ]

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
        self.report_path = self.output_folder / "post_remediation_auto_fix_effectiveness_report.csv"
        self.loader = RemediationReportLoader(
            self.output_folder,
            scoring_rules_path or Path("common/config/readiness_rules.json"),
        )

    def build_report(self) -> list[RemediationEffectivenessRecord]:
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

        remediation = self.loader.load_remediation_issues()
        mappings = sorted(
            {issue.mapping_name for issue in remediation}
            or self.loader.mapping_names
            or {"UNMAPPED_ASSET"}
        )
        records: list[RemediationEffectivenessRecord] = []
        for mapping in mappings:
            remediation_for_mapping = [issue for issue in remediation if issue.mapping_name == mapping]
            found = len(remediation_for_mapping)
            auto_fixed = len(
                [
                    issue
                    for issue in remediation_for_mapping
                    if issue.mapping_name == mapping and (issue.auto_fixed or issue.status.lower() == "resolved")
                ]
            )
            auto_fixed = min(auto_fixed, found)
            ai_recommendation = len(
                [issue for issue in remediation_for_mapping if issue.approval_required]
            )
            ai_assistance = len(
                [
                    issue
                    for issue in remediation_for_mapping
                    if issue.ai_assistance_required
                ]
            )
            records.append(
                RemediationEffectivenessRecord(
                    mapping_name=mapping,
                    issues_found=found,
                    auto_fixed=auto_fixed,
                    ai_recommendation=ai_recommendation,
                    ai_assistance=ai_assistance,
                    auto_fix_percentage=round((auto_fixed / found) * 100, 2) if found else 0.0,
                )
            )
        self.write_report(records)
        if self.logger:
            self.logger.info(
                "Remediation effectiveness report written to %s. rows=%s", self.report_path, len(records)
            )
        return records

    def write_report(
        self, records: list[RemediationEffectivenessRecord], report_path: str | Path | None = None
    ) -> None:
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


def build_remediation_effectiveness_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    scoring_rules_path: str | Path | None = None,
) -> list[RemediationEffectivenessRecord]:
    """
    Executes the build_remediation_effectiveness_report workflow for migration validation and readiness logic.
    
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

    return RemediationEffectivenessEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        scoring_rules_path=scoring_rules_path,
    ).build_report()
