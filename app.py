"""
Support app for PowerCenter to IICS migration support.
Keeps the application workflow organized.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from common.config.config import ConfigLoader
from common.logger.logger import LoggerFactory


def create_app():
    """Create app for the migration workflow."""
    from fastapi import FastAPI

    from api.routes import evaluation_router, recommendation_router

    fastapi_app = FastAPI(
        title="PowerCenter to IDMC Migration Accelerator API",
        version="1.0.0",
    )
    fastapi_app.include_router(recommendation_router)
    fastapi_app.include_router(evaluation_router)
    return fastapi_app


def parse_args() -> argparse.Namespace:
    """Parse args for the migration workflow."""

    parser = argparse.ArgumentParser(
        description="Explore Informatica PowerCenter XML exports and generate structure summaries."
    )
    parser.add_argument(
        "--mode",
        choices=[
            "canonical",
            "parse",
            "explore",
            "classify",
            "persist",
            "reports",
            "enterprise",
            "automation",
            "iics-package",
            "all",
        ],
        default="canonical",
        help=(
            "Run canonical model build, raw metadata parser, XML structure explorer, complexity classifier, "
            "report builder, MySQL persistence, the enterprise pipeline, automated validation, "
            "IICS package processing, "
            "or all metadata, validation, remediation, and automation outputs."
        ),
    )
    parser.add_argument(
        "--iics-zip",
        default=None,
        help="Path to client-provided IICS export zip. Required when --mode iics-package.",
    )
    parser.add_argument(
        "--fix-checksum",
        action="store_true",
        help="With --mode iics-package and --iics-zip, rewrite exportPackage.chksum only.",
    )
    parser.add_argument(
        "--config",
        default="common/config/config.json",
        help="Path to JSON configuration file.",
    )
    parser.add_argument(
        "--xml-file",
        default=None,
        help="Optional single XML file to explore. Defaults to every XML in configured xml_folder.",
    )
    parser.add_argument(
        "--print-hierarchy",
        action="store_true",
        help="Print tag hierarchy to console in addition to writing report files.",
    )
    parser.add_argument(
        "--persist",
        action="store_true",
        help="With --mode enterprise, also load the central MySQL metadata repository.",
    )
    parser.add_argument(
        "--automation-config",
        default="config/automation_config.json",
        help="Path to Automated Validation Framework configuration file.",
    )
    return parser.parse_args()


def main() -> None:
    """Handle main for the migration workflow."""

    args = parse_args()
    config = ConfigLoader(Path(args.config)).load()
    logger = LoggerFactory.create_logger(config.logging, config.paths.log_folder)

    if args.mode == "all":
        summary = run_all(
            config=config,
            logger=logger,
            persist_to_mysql=args.persist,
            automation_config=args.automation_config,
        )
        logger.info("Full metadata, validation, remediation, and automation run completed. %s", summary)
    elif args.mode == "explore":
        from business.parser.xml_explorer import PowerCenterXmlExplorer

        explorer = PowerCenterXmlExplorer(config=config, logger=logger)
        if args.xml_file:
            summary = explorer.explore_file(Path(args.xml_file), print_hierarchy=args.print_hierarchy)
        else:
            summary = explorer.explore_folder(print_hierarchy=args.print_hierarchy)

        logger.info(
            "XML exploration completed. files=%s folders=%s mappings=%s unique_tags=%s",
            summary.file_count,
            len(summary.folder_summary),
            len(summary.mapping_summary),
            len(summary.tag_counts),
        )
    elif args.mode == "parse":
        from business.parser.xml_parser import XMLParser

        xml_parser = XMLParser(config=config, logger=logger)
        if args.xml_file:
            parsed = xml_parser.parse_file(Path(args.xml_file))
            xml_parser.json_output_folder.mkdir(parents=True, exist_ok=True)
            xml_parser.table_output_folder.mkdir(parents=True, exist_ok=True)
            xml_parser._write_json(parsed)
            tables = xml_parser.to_dataframes([parsed])
            xml_parser._write_tables(tables)
            logger.info("Metadata parsing completed for file=%s", parsed.file_name)
        else:
            result = xml_parser.parse_folder()
            logger.info(
                "Metadata parsing completed. files=%s errors=%s tables=%s",
                len(result["parsed_files"]),
                len(result["errors"]),
                len(result["dataframes"]),
            )
    elif args.mode == "classify":
        from business.complexity.complexity_engine import ComplexityClassifier

        classifier = ComplexityClassifier(config=config, logger=logger)
        results = classifier.classify()
        classifier.write_report(results)
        logger.info("Complexity classification completed. mappings=%s", len(results))
    elif args.mode == "persist":
        from data.repositories.mapping_repository import MySqlMetadataRepository

        repository = MySqlMetadataRepository(config=config, logger=logger)
        summary = repository.persist()
        logger.info(
            "MySQL persistence completed. assets=%s mappings=%s transformations=%s columns=%s sql_overrides=%s connectors=%s",
            summary["assets"],
            summary["mappings"],
            summary["transformations"],
            summary["columns_metadata"],
            summary["sql_overrides"],
            summary["connectors"],
        )
    elif args.mode == "reports":
        from reports.html_report import EnterpriseReportBuilder

        report_builder = EnterpriseReportBuilder(config=config, logger=logger)
        summary = report_builder.build_reports()
        logger.info("Enterprise report generation completed. %s", summary)
    elif args.mode == "enterprise":
        from business.migration.migration_service import EnterpriseMigrationPipeline

        pipeline = EnterpriseMigrationPipeline(config=config, logger=logger)
        summary = pipeline.run(persist_to_mysql=args.persist)
        logger.info("Enterprise pipeline run completed. %s", summary)
    elif args.mode == "automation":
        from automation.automated_validation_framework import AutomatedValidationFramework

        summary = AutomatedValidationFramework(config_path=args.automation_config).run()
        logger.info("Automated validation framework completed. %s", summary)
    elif args.mode == "iics-package":
        from business.iics.iics_package_processor import IICSPackageProcessor
        from business.iics.iics_package_generator import IICSPackageGenerator
        from business.iics.checksum_utils import rewrite_zip_checksums, validate_zip_checksums

        if args.fix_checksum:
            if not args.iics_zip:
                raise ValueError("--iics-zip is required when --fix-checksum is set")
            out_dir = Path(config.paths.output_folder) / "iics"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_zip = out_dir / "iics_checksum_fixed.zip"
            rewrite_zip_checksums(args.iics_zip, out_zip)
            ok, errors = validate_zip_checksums(out_zip)
            if not ok:
                raise RuntimeError(f"Checksum fix failed validation: {errors[0]}")
            logger.info("Checksum fixed and validated. output=%s", out_zip)
        elif args.iics_zip:
            # Validate/repackage a client-supplied zip
            processor = IICSPackageProcessor(
                input_zip=args.iics_zip,
                output_dir=Path(config.paths.output_folder) / "iics",
                logger=logger,
            )
            summary = processor.process()
            logger.info(
                "IICS package processing completed. valid=%s invalid=%s output=%s",
                summary["valid_assets"], summary["invalid_assets"], summary["output_zip"],
            )
        else:
            # Generate a new IICS package from the parsed PowerCenter XML files.
            from business.export.idmc_export_package import generate_individual_idmc_export_packages

            generator = IICSPackageGenerator(
                parsed_json_dir=Path(config.paths.output_folder) / "parsed_json",
                remediated_xml_dir=Path(config.paths.output_folder) / "remediated_xml",
                output_dir=Path(config.paths.output_folder),
                output_zip_name="Custom_Project_Export.zip",
                logger=logger,
            )
            summary = generator.generate()
            logger.info(
                "IICS package generation completed. assets=%s output=%s",
                summary["total_assets"], summary["output_zip"],
            )
            individual_summary = generate_individual_idmc_export_packages(config=config, logger=logger)
            logger.info(
                "Individual IDMC package generation completed. input_xml=%s packages=%s output_folder=%s",
                individual_summary.input_xml_count,
                individual_summary.package_count,
                individual_summary.output_folder,
            )
    else:
        from business.parser.xml_parser import XMLParser
        from data.repositories.metadata_repository import CanonicalMetadataBuilder

        xml_parser = XMLParser(config=config, logger=logger)
        canonical_builder = CanonicalMetadataBuilder(config=config, logger=logger)
        if args.xml_file:
            parsed_files = [xml_parser.parse_file(Path(args.xml_file))]
        else:
            result = xml_parser.parse_folder()
            parsed_files = result["parsed_files"]
            if result["errors"]:
                logger.warning("Canonical build continuing with %s parser error(s)", len(result["errors"]))

        canonical_repository = canonical_builder.build(parsed_files)
        canonical_builder.write_outputs(canonical_repository)
        logger.info(
            "Canonical metadata build completed. assets=%s mappings=%s transformations=%s columns=%s connectors=%s sql_overrides=%s",
            len(canonical_repository.assets),
            len(canonical_repository.mappings),
            len(canonical_repository.transformations),
            len(canonical_repository.columns),
            len(canonical_repository.connectors),
            len(canonical_repository.sql_overrides),
        )


def run_all(
    config,
    logger,
    persist_to_mysql: bool = False,
    automation_config: str | Path = "config/automation_config.json",
) -> dict[str, object]:
    """Run all for the migration workflow."""
    from business.complexity.complexity_engine import ComplexityClassifier
    from business.validation.batch_xml_processor import run_batch_xml_remediation
    from business.validation.datatype_harmonization import build_datatype_mismatch_report
    from business.validation.readiness_engine import build_migration_readiness_report
    from business.validation.Rule_Based_Validation_Engine import build_remediation_report
    from business.validation.validation_engine import build_validation_report
    from business.parser.xml_parser import XMLParser
    from data.repositories.metadata_repository import CanonicalMetadataBuilder
    from reports.html_report import EnterpriseReportBuilder
    from automation.automated_validation_framework import AutomatedValidationFramework
    from business.export.idmc_export_package import generate_idmc_export_package, generate_individual_idmc_export_packages

    logger.info("Starting full metadata, validation, and remediation run.")

    xml_parser = XMLParser(config=config, logger=logger)
    parse_result = xml_parser.parse_folder()
    parsed_files = parse_result["parsed_files"]
    if parse_result["errors"]:
        logger.warning("Full run continuing with %s parser error(s)", len(parse_result["errors"]))

    canonical_builder = CanonicalMetadataBuilder(config=config, logger=logger)
    canonical_repository = canonical_builder.build(parsed_files)
    canonical_builder.write_outputs(canonical_repository)

    complexity_results = ComplexityClassifier(config=config, logger=logger).classify()
    ComplexityClassifier(config=config, logger=logger).write_report(complexity_results)

    enterprise_reports = EnterpriseReportBuilder(config=config, logger=logger).build_reports()
    persistence_summary = None
    if persist_to_mysql:
        from data.repositories.mapping_repository import MySqlMetadataRepository

        try:
            persistence_summary = MySqlMetadataRepository(config=config, logger=logger).persist()
        except Exception as exc:
            logger.warning("MySQL metadata persistence failed; continuing automation run. %s", exc)
            persistence_summary = {"error": str(exc)}

    enterprise_summary = {
        "xml_files": len(parsed_files),
        "parser_errors": len(parse_result["errors"]),
        "canonical_assets": len(canonical_repository.assets),
        "canonical_mappings": len(canonical_repository.mappings),
        "canonical_transformations": len(canonical_repository.transformations),
        "canonical_columns": len(canonical_repository.columns),
        "canonical_connectors": len(canonical_repository.connectors),
        "canonical_sql_overrides": len(canonical_repository.sql_overrides),
        "complexity_mappings": len(complexity_results),
        "reports": enterprise_reports,
        "mysql": persistence_summary,
    }
    datatype_findings = build_datatype_mismatch_report(config=config, logger=logger)
    validation_issues = build_validation_report(config=config, logger=logger)
    remediation_results, revalidation_summary = build_remediation_report(config=config, logger=logger)
    readiness_records = build_migration_readiness_report(config=config, logger=logger)
    xml_summary = run_batch_xml_remediation(
        input_folder=config.paths.xml_folder,
        output_folder=config.paths.output_folder,
    )
    automation_framework = AutomatedValidationFramework(config_path=automation_config)
    if automation_framework.config.execute_existing_modules:
        from dataclasses import replace

        automation_framework.config = replace(automation_framework.config, execute_existing_modules=False)
    automation_summary = automation_framework.run()
    package_path = Path(config.paths.output_folder) / "Custom_Project_Export.zip"
    existing_package = package_path.read_bytes() if package_path.exists() else None
    try:
        idmc_export_summary = generate_idmc_export_package(config=config, logger=logger)
        individual_idmc_export_summary = generate_individual_idmc_export_packages(config=config, logger=logger)
    except Exception:
        if package_path.exists():
            package_path.unlink()
        if existing_package is not None:
            package_path.write_bytes(existing_package)
        logger.exception("IDMC export package generation failed after XML remediation completed.")
        raise

    return {
        "enterprise": enterprise_summary,
        "datatype_findings": len(datatype_findings),
        "validation_issues": len(validation_issues),
        "remediation_results": len(remediation_results),
        "readiness_records": len(readiness_records),
        "revalidation": {
            "before_fix_issues": revalidation_summary.before_fix_issues,
            "after_fix_issues": revalidation_summary.after_fix_issues,
            "resolved_issues": revalidation_summary.resolved_issues,
        },
        "xml": xml_summary,
        "automation": automation_summary,
        "idmc_export": idmc_export_summary,
        "individual_idmc_exports": individual_idmc_export_summary,
    }


if __name__ == "__main__":
    main()
