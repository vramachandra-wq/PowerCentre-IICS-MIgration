"""
Module: business/migration/migration_service.py

Purpose:
    This module supports migration orchestration services for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the migration orchestration services area and coordinates high-level migration processing around parsed metadata and validation outputs. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from business.complexity.complexity_engine import ComplexityClassifier
from business.parser.xml_parser import XMLParser
from reports.html_report import EnterpriseReportBuilder
from data.repositories.metadata_repository import CanonicalMetadataBuilder
from data.repositories.mapping_repository import MySqlMetadataRepository
from common.config.config import AppConfig


class EnterpriseMigrationPipeline:
    """Coordinates the complete enterprise metadata pipeline."""

    def __init__(self, config: AppConfig, logger) -> None:
        """
        Executes the __init__ workflow for migration orchestration services.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                config (object): Value supplied by the caller and used by the workflow.
                logger (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that coordinates high-level migration processing around parsed metadata and validation outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.config = config
        self.logger = logger

    def run(self, persist_to_mysql: bool = False) -> dict[str, Any]:
        """
        Executes the run workflow for migration orchestration services.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                persist_to_mysql (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that coordinates high-level migration processing around parsed metadata and validation outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        xml_parser = XMLParser(config=self.config, logger=self.logger)
        canonical_builder = CanonicalMetadataBuilder(config=self.config, logger=self.logger)
        classifier = ComplexityClassifier(config=self.config, logger=self.logger)
        report_builder = EnterpriseReportBuilder(config=self.config, logger=self.logger)

        parse_result = xml_parser.parse_folder()
        parsed_files = parse_result["parsed_files"]
        if parse_result["errors"]:
            self.logger.warning("Enterprise pipeline continuing with %s parser error(s)", len(parse_result["errors"]))

        canonical_repository = canonical_builder.build(parsed_files)
        canonical_builder.write_outputs(canonical_repository)

        complexity_results = classifier.classify()
        classifier.write_report(complexity_results)

        report_summary = report_builder.build_reports()
        persistence_summary = None
        if persist_to_mysql:
            persistence_summary = MySqlMetadataRepository(config=self.config, logger=self.logger).persist()

        summary = {
            "xml_files": len(parsed_files),
            "parser_errors": len(parse_result["errors"]),
            "canonical_assets": len(canonical_repository.assets),
            "canonical_mappings": len(canonical_repository.mappings),
            "canonical_transformations": len(canonical_repository.transformations),
            "canonical_columns": len(canonical_repository.columns),
            "canonical_connectors": len(canonical_repository.connectors),
            "canonical_sql_overrides": len(canonical_repository.sql_overrides),
            "complexity_mappings": len(complexity_results),
            "reports": report_summary,
            "mysql": persistence_summary,
        }
        self.logger.info("Enterprise pipeline completed. %s", summary)
        return summary

    @staticmethod
    def resolve_path(path: str | Path) -> Path:
        """
        Executes the resolve_path workflow for migration orchestration services.
        
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
            This function belongs to the layer that coordinates high-level migration processing around parsed metadata and validation outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return Path.cwd() / candidate
