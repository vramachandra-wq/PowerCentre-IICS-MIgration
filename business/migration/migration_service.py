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
        self.config = config
        self.logger = logger

    def run(self, persist_to_mysql: bool = False) -> dict[str, Any]:
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
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return Path.cwd() / candidate
