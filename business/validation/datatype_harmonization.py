"""
Module: business/validation/datatype_harmonization.py

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
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from business.validation.datatype_mapping_engine import DatatypeMappingEngine, DatatypeSpec
from common.config.config import AppConfig


@dataclass(frozen=True)
class MetadataColumn:
    """
    Represents the MetadataColumn component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    column: str
    datatype: str
    precision: int | None
    scale: int | None
    table_name: str = ""
    table_type: str = ""
    mapping_name: str = ""
    transformation_name: str = ""
    transformation_type: str = ""
    source_file: str = ""
    repository_name: str = ""
    folder_name: str = ""


@dataclass(frozen=True)
class DatatypeMismatch:
    """
    Represents the DatatypeMismatch component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    column: str
    source: str
    target: str
    severity: str
    recommendation: str
    issue_type: str
    transformation: str = ""
    mapping_name: str = ""
    source_file: str = ""


class DatatypeHarmonizationEngine:
    """Compares source, target, and transformation metadata using JSON datatype rules."""

    REPORT_COLUMNS = [
        "column",
        "source",
        "target",
        "severity",
        "recommendation",
        "issue_type",
        "transformation",
        "mapping_name",
        "source_file",
    ]

    def __init__(
        self,
        config: AppConfig | None = None,
        logger=None,
        output_folder: str | Path | None = None,
        rules_path: str | Path | None = None,
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
                rules_path (object): Value supplied by the caller and used by the workflow.
        
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
        self.metadata_folder = self.output_folder / "metadata_tables"
        self.report_path = self.output_folder / "datatype_mismatch_report.csv"
        self.mapping_engine = DatatypeMappingEngine(rules_path=rules_path)

    def harmonize(self) -> list[DatatypeMismatch]:
        """
        Executes the harmonize workflow for migration validation and readiness logic.
        
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

        source_columns = self._load_columns(self.metadata_folder / "source_columns.csv", "SOURCE")
        target_columns = self._load_columns(self.metadata_folder / "target_columns.csv", "TARGET")
        transformation_columns = self._load_ports(self.metadata_folder / "ports.csv")

        findings: list[DatatypeMismatch] = []
        findings.extend(self.compare_source_target(source_columns, target_columns))
        findings.extend(self.compare_transformation_metadata(source_columns, target_columns, transformation_columns))

        deduped = self._deduplicate(findings)
        self.write_report(deduped)
        if self.logger:
            self.logger.info("Datatype mismatch report written to %s. rows=%s", self.report_path, len(deduped))
        return deduped

    def compare_source_target(
        self,
        source_columns: Iterable[MetadataColumn],
        target_columns: Iterable[MetadataColumn],
    ) -> list[DatatypeMismatch]:
        """
        Executes the compare_source_target workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                source_columns (object): Value supplied by the caller and used by the workflow.
                target_columns (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        targets_by_context = self._index_columns(target_columns)
        findings: list[DatatypeMismatch] = []
        for source_column in source_columns:
            context = (source_column.source_file, source_column.repository_name, source_column.folder_name)
            target_column = targets_by_context.get(context, {}).get(self._normalize_name(source_column.column))
            if not target_column:
                continue
            findings.extend(self._compare_pair(source_column, target_column, "source_target"))
        return findings

    def compare_transformation_metadata(
        self,
        source_columns: Iterable[MetadataColumn],
        target_columns: Iterable[MetadataColumn],
        transformation_columns: Iterable[MetadataColumn],
    ) -> list[DatatypeMismatch]:
        """
        Executes the compare_transformation_metadata workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                source_columns (object): Value supplied by the caller and used by the workflow.
                target_columns (object): Value supplied by the caller and used by the workflow.
                transformation_columns (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        columns_by_context = self._index_columns([*source_columns, *target_columns])
        findings: list[DatatypeMismatch] = []
        for port in transformation_columns:
            context = (port.source_file, port.repository_name, port.folder_name)
            related = columns_by_context.get(context, {}).get(self._normalize_name(port.column))
            if not related:
                continue
            findings.extend(self._compare_pair(related, port, "transformation"))
            if port.transformation_type.upper() == "LOOKUP":
                findings.extend(self._compare_pair(related, port, "lookup"))
        return findings

    def write_report(self, findings: list[DatatypeMismatch], report_path: str | Path | None = None) -> None:
        """
        Executes the write_report workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                findings (object): Value supplied by the caller and used by the workflow.
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
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(asdict(finding) for finding in findings)

    def _compare_pair(
        self,
        left_column: MetadataColumn,
        right_column: MetadataColumn,
        comparison_scope: str,
    ) -> list[DatatypeMismatch]:
        """
        Executes the _compare_pair workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                left_column (object): Value supplied by the caller and used by the workflow.
                right_column (object): Value supplied by the caller and used by the workflow.
                comparison_scope (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        left = self.mapping_engine.map_datatype(
            left_column.datatype,
            precision=left_column.precision,
            scale=left_column.scale,
        )
        right = self.mapping_engine.map_datatype(
            right_column.datatype,
            precision=right_column.precision,
            scale=right_column.scale,
        )

        findings: list[DatatypeMismatch] = []
        self._append_if(findings, not self.mapping_engine.are_compatible(left, right), "datatype_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._precision_mismatch(left, right), "precision_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._scale_mismatch(left, right), "scale_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._length_mismatch(left, right), "length_mismatch", left_column, right_column, left, right)
        self._append_if(findings, left.unicode != right.unicode and left.family == right.family == "STRING", "unicode_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._varchar_vs_nvarchar(left, right), "varchar_vs_nvarchar", left_column, right_column, left, right)
        self._append_if(findings, self._decimal_vs_double(left, right), "decimal_vs_double", left_column, right_column, left, right)
        self._append_if(findings, self._native_precision_mismatch(left, right), "native_precision_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._truncation_risk(left, right), "truncation_risk", left_column, right_column, left, right)
        self._append_if(findings, left.base_type == "CLOB" or right.base_type == "CLOB", "clob_to_text_conversion", left_column, right_column, left, right)
        if comparison_scope == "lookup" and findings:
            findings.append(self._finding("lookup_datatype_mismatch", left_column, right_column, left, right))
        return findings

    def _append_if(
        self,
        findings: list[DatatypeMismatch],
        condition: bool,
        issue_code: str,
        left_column: MetadataColumn,
        right_column: MetadataColumn,
        left: DatatypeSpec,
        right: DatatypeSpec,
    ) -> None:
        """
        Executes the _append_if workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                findings (object): Value supplied by the caller and used by the workflow.
                condition (object): Value supplied by the caller and used by the workflow.
                issue_code (object): Value supplied by the caller and used by the workflow.
                left_column (object): Value supplied by the caller and used by the workflow.
                right_column (object): Value supplied by the caller and used by the workflow.
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if condition:
            findings.append(self._finding(issue_code, left_column, right_column, left, right))

    def _finding(
        self,
        issue_code: str,
        left_column: MetadataColumn,
        right_column: MetadataColumn,
        left: DatatypeSpec,
        right: DatatypeSpec,
    ) -> DatatypeMismatch:
        """
        Executes the _finding workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                issue_code (object): Value supplied by the caller and used by the workflow.
                left_column (object): Value supplied by the caller and used by the workflow.
                right_column (object): Value supplied by the caller and used by the workflow.
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        rule = self.mapping_engine.issue_rule(issue_code)
        return DatatypeMismatch(
            column=left_column.column,
            source=self._display_type(left),
            target=self._display_type(right),
            severity=rule["severity"],
            recommendation=rule["recommendation"],
            issue_type=issue_code,
            transformation=right_column.transformation_name,
            mapping_name=right_column.mapping_name or left_column.mapping_name,
            source_file=right_column.source_file or left_column.source_file,
        )

    @staticmethod
    def _precision_mismatch(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        """
        Executes the _precision_mismatch workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return left.family in {"NUMERIC", "FLOATING"} and right.family in {"NUMERIC", "FLOATING"} and left.precision != right.precision

    @staticmethod
    def _scale_mismatch(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        """
        Executes the _scale_mismatch workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return left.family in {"NUMERIC", "FLOATING"} and right.family in {"NUMERIC", "FLOATING"} and left.scale != right.scale

    @staticmethod
    def _length_mismatch(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        """
        Executes the _length_mismatch workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return left.family == right.family == "STRING" and left.length is not None and right.length is not None and left.length != right.length

    @staticmethod
    def _varchar_vs_nvarchar(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        """
        Executes the _varchar_vs_nvarchar workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return {left.base_type, right.base_type} & {"VARCHAR", "VARCHAR2"} and {left.base_type, right.base_type} & {"NCHAR", "NVARCHAR2"}

    @staticmethod
    def _decimal_vs_double(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        """
        Executes the _decimal_vs_double workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return {left.family, right.family} == {"NUMERIC", "FLOATING"}

    @staticmethod
    def _native_precision_mismatch(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        """
        Executes the _native_precision_mismatch workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return (
            left.family in {"NUMERIC", "FLOATING"}
            and right.family in {"NUMERIC", "FLOATING"}
            and left.precision is not None
            and right.precision is not None
            and abs(left.precision - right.precision) >= 10
        )

    @staticmethod
    def _truncation_risk(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        """
        Executes the _truncation_risk workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                left (object): Value supplied by the caller and used by the workflow.
                right (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if left.family == right.family == "STRING" and left.length and right.length:
            return right.length < left.length
        if left.family in {"NUMERIC", "FLOATING"} and right.family in {"NUMERIC", "FLOATING"}:
            return (
                left.precision is not None
                and right.precision is not None
                and right.precision < left.precision
            ) or (
                left.scale is not None
                and right.scale is not None
                and right.scale < left.scale
            )
        return False

    @staticmethod
    def _display_type(spec: DatatypeSpec) -> str:
        """
        Executes the _display_type workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                spec (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if spec.length is not None:
            return f"{spec.canonical_type}({spec.length})"
        if spec.precision is not None and spec.scale is not None:
            return f"{spec.canonical_type}({spec.precision},{spec.scale})"
        if spec.precision is not None:
            return f"{spec.canonical_type}({spec.precision})"
        return spec.canonical_type

    def _load_columns(self, path: Path, table_type: str) -> list[MetadataColumn]:
        """
        Executes the _load_columns workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
                table_type (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        rows = self._read_csv(path)
        name_key = "source_name" if table_type == "SOURCE" else "target_name"
        return [
            MetadataColumn(
                column=row.get("column_name", ""),
                datatype=row.get("datatype", ""),
                precision=self._to_int(row.get("precision")),
                scale=self._to_int(row.get("scale")),
                table_name=row.get(name_key, ""),
                table_type=table_type,
                source_file=row.get("file_name", ""),
                repository_name=row.get("repository_name", ""),
                folder_name=row.get("folder_name", ""),
            )
            for row in rows
        ]

    def _load_ports(self, path: Path) -> list[MetadataColumn]:
        """
        Executes the _load_ports workflow for migration validation and readiness logic.
        
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

        transformations = {
            (
                row.get("file_name", ""),
                row.get("repository_name", ""),
                row.get("folder_name", ""),
                row.get("mapping_name", ""),
                row.get("transformation_name", ""),
            ): row.get("transformation_type", "")
            for row in self._read_csv(self.metadata_folder / "transformations.csv")
        }
        return [
            MetadataColumn(
                column=row.get("port_name", ""),
                datatype=row.get("datatype", ""),
                precision=self._to_int(row.get("precision")),
                scale=self._to_int(row.get("scale")),
                table_type=row.get("port_scope", "TRANSFORMATION"),
                mapping_name=row.get("mapping_name", ""),
                transformation_name=row.get("transformation_name", ""),
                transformation_type=transformations.get(
                    (
                        row.get("file_name", ""),
                        row.get("repository_name", ""),
                        row.get("folder_name", ""),
                        row.get("mapping_name", ""),
                        row.get("transformation_name", ""),
                    ),
                    "",
                ),
                source_file=row.get("file_name", ""),
                repository_name=row.get("repository_name", ""),
                folder_name=row.get("folder_name", ""),
            )
            for row in self._read_csv(path)
        ]

    @staticmethod
    def _index_columns(columns: Iterable[MetadataColumn]) -> dict[tuple[str, str, str], dict[str, MetadataColumn]]:
        """
        Executes the _index_columns workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                columns (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        indexed: dict[tuple[str, str, str], dict[str, MetadataColumn]] = {}
        for column in columns:
            context = (column.source_file, column.repository_name, column.folder_name)
            indexed.setdefault(context, {})[DatatypeHarmonizationEngine._normalize_name(column.column)] = column
        return indexed

    @staticmethod
    def _deduplicate(findings: Iterable[DatatypeMismatch]) -> list[DatatypeMismatch]:
        """
        Executes the _deduplicate workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                findings (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        seen: set[tuple[str, str, str, str, str]] = set()
        deduped: list[DatatypeMismatch] = []
        for finding in findings:
            key = (finding.column, finding.issue_type, finding.source, finding.target, finding.transformation)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(finding)
        return deduped

    @staticmethod
    def _normalize_name(value: str) -> str:
        """
        Executes the _normalize_name workflow for migration validation and readiness logic.
        
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

        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    @staticmethod
    def _to_int(value: object) -> int | None:
        """
        Executes the _to_int workflow for migration validation and readiness logic.
        
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

        if value in {None, ""}:
            return None
        try:
            return int(str(value).strip())
        except ValueError:
            return None

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        """
        Executes the _read_csv workflow for migration validation and readiness logic.
        
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

        if not path.exists():
            raise FileNotFoundError(f"Required datatype harmonization input not found: {path}")
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

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


def build_datatype_mismatch_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    rules_path: str | Path | None = None,
) -> list[DatatypeMismatch]:
    """
    Executes the build_datatype_mismatch_report workflow for migration validation and readiness logic.
    
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
            rules_path (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    return DatatypeHarmonizationEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        rules_path=rules_path,
    ).harmonize()
