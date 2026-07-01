from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from automation.consolidated_findings import ConsolidatedFindingsBuilder
from automation.dashboard_dataset import DashboardDatasetBuilder
from automation.evaluation_dataset import EvaluationDatasetBuilder
from automation.evaluation_matrix import EvaluationMatrixBuilder, ReportRepository
from automation.validation_summary import ValidationSummaryBuilder


@dataclass(frozen=True)
class AutomationConfig:
    """Runtime configuration for the automated validation framework."""

    output_folder: Path
    reports_folder: Path
    logs_folder: Path
    validation_rules_path: Path
    enable_metrics: bool = True
    enable_dashboard_export: bool = True
    enable_evaluation_dataset: bool = True
    enable_consolidated_findings: bool = True
    enable_validation_summary: bool = True
    execute_existing_modules: bool = True


class AutomatedValidationFramework:
    """
    Orchestrates Week-1 and Week-2 outputs into rule-based Week-3 reports.

    This class does not reimplement validation, datatype, remediation, readiness,
    or risk logic. It consumes existing artifacts and normalizes them into a
    single mapping-level evaluation matrix plus derived datasets.
    """

    DEFAULT_CONFIG_PATH = Path("config/automation_config.json")

    def __init__(self, config_path: str | Path | None = None, logger: logging.Logger | None = None) -> None:
        self.project_root = Path.cwd()
        self.config_path = self._resolve(config_path or self.DEFAULT_CONFIG_PATH)
        self.config = self._load_config(self.config_path)
        self.logger = logger or self._create_logger()
        self.repository = ReportRepository(self.config.output_folder, self.config.reports_folder)

    def run(self) -> dict[str, Any]:
        start_time = datetime.now(UTC)
        try:
            self.logger.info("Automated validation framework started at %s", start_time.isoformat())
            self._validate_prerequisites()
            modules_executed = self._execute_existing_modules() if self.config.execute_existing_modules else []

            outputs: dict[str, Any] = {}
            matrix_builder = EvaluationMatrixBuilder(
                repository=self.repository,
                validation_rules_path=self.config.validation_rules_path,
            )
            matrix_records = matrix_builder.build()
            outputs["evaluation_matrix"] = str(matrix_builder.write(matrix_records))
            canonical_objects = matrix_builder.build_canonical_objects(matrix_records)
            self.logger.info("Evaluation matrix generated. mappings=%s", len(matrix_records))

            if self.config.enable_evaluation_dataset:
                builder = EvaluationDatasetBuilder(self.repository)
                dataset = builder.build(matrix_records)
                canonical_dataset = builder.build_canonical_dataset(canonical_objects)
                outputs["evaluation_dataset"] = {
                    key: str(path) for key, path in builder.write(dataset, canonical_dataset).items()
                }
                self.logger.info("Evaluation dataset generated. rows=%s", len(dataset))

            if self.config.enable_consolidated_findings:
                builder = ConsolidatedFindingsBuilder(self.repository)
                findings = builder.build(matrix_records)
                outputs["consolidated_findings"] = str(builder.write(findings))
                self.logger.info("Consolidated findings generated.")

            if self.config.enable_validation_summary:
                builder = ValidationSummaryBuilder(self.repository)
                summary = builder.build(matrix_records)
                outputs["validation_summary"] = str(builder.write(summary))
                self.logger.info("Validation summary generated.")

            if self.config.enable_dashboard_export:
                builder = DashboardDatasetBuilder(self.repository)
                dashboard = builder.build(matrix_records)
                outputs["dashboard_dataset"] = {key: str(path) for key, path in builder.write(dashboard).items()}
                self.logger.info("Dashboard dataset generated. rows=%s", len(dashboard))

            end_time = datetime.now(UTC)
            self.logger.info(
                "Automated validation framework completed at %s. files_processed=%s outputs=%s",
                end_time.isoformat(),
                len({record.xml_name for record in matrix_records if record.xml_name}),
                outputs,
            )
            return {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "files_processed": len({record.xml_name for record in matrix_records if record.xml_name}),
                "evaluation_records": len(matrix_records),
                "modules_executed": modules_executed,
                "outputs": outputs,
            }
        finally:
            self._close_logger_handlers()

    def _validate_prerequisites(self) -> None:
        required = [
            self.config.output_folder / "metadata_tables" / "mappings.csv",
            self.config.output_folder / "complexity_classification_report.csv",
            self.config.output_folder / "validation_report.csv",
            self.config.output_folder / "datatype_mismatch_report.csv",
            self.config.output_folder / "migration_readiness_report.csv",
            self.config.output_folder / "risk_assessment_report.csv",
            self.config.output_folder / "remediation_effectiveness_report.csv",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            message = "Missing prerequisite output artifact(s): " + ", ".join(missing)
            self.logger.error(message)
            raise FileNotFoundError(message)

    def _load_config(self, path: Path) -> AutomationConfig:
        if not path.exists():
            raise FileNotFoundError(f"Automation config not found: {path}")
        with path.open("r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        exports = payload.get("exports", {})
        features = payload.get("features", {})
        return AutomationConfig(
            output_folder=self._resolve(payload.get("output_folder", "output")),
            reports_folder=self._resolve(exports.get("reports_folder", "output/automation")),
            logs_folder=self._resolve(payload.get("logs_folder", "logs")),
            validation_rules_path=self._resolve(payload.get("validation_rules_path", "common/config/validation_rules.json")),
            enable_metrics=bool(features.get("enable_metrics", True)),
            enable_dashboard_export=bool(features.get("enable_dashboard_export", True)),
            enable_evaluation_dataset=bool(features.get("enable_evaluation_dataset", True)),
            enable_consolidated_findings=bool(features.get("enable_consolidated_findings", True)),
            enable_validation_summary=bool(features.get("enable_validation_summary", True)),
            execute_existing_modules=bool(features.get("execute_existing_modules", True)),
        )

    def _execute_existing_modules(self) -> list[str]:
        """Runs existing Week-2 report builders without duplicating their logic."""
        from business.validation.Rule_Based_Validation_Engine import build_remediation_report
        from business.validation.batch_xml_processor import run_batch_xml_remediation
        from business.validation.datatype_harmonization import build_datatype_mismatch_report
        from business.validation.readiness_engine import build_migration_readiness_report
        from business.validation.remediation_effectiveness import build_remediation_effectiveness_report
        from business.validation.risk_assessment import build_risk_assessment_report
        from business.validation.validation_engine import build_validation_report

        modules: list[tuple[str, object]] = [
            ("datatype_harmonization", build_datatype_mismatch_report),
            ("validation", build_validation_report),
            ("rule_based_remediation", build_remediation_report),
            ("updated_xml_generation", run_batch_xml_remediation),
            ("migration_readiness", build_migration_readiness_report),
            ("risk_assessment", build_risk_assessment_report),
            ("remediation_effectiveness", build_remediation_effectiveness_report),
        ]
        executed: list[str] = []
        for name, builder in modules:
            self.logger.info("Executing existing module: %s", name)
            try:
                if name == "updated_xml_generation":
                    self._sync_latest_remediation_report()
                    builder(output_folder=self.config.output_folder)
                else:
                    builder(output_folder=self.config.output_folder)
            except PermissionError as exc:
                self.logger.warning(
                    "Skipping existing module %s because an output file is locked. Existing artifact will be used. %s",
                    name,
                    exc,
                )
            executed.append(name)
        return executed

    def _sync_latest_remediation_report(self) -> None:
        latest = self.config.output_folder / "remediation_report_latest.csv"
        target = self.config.output_folder / "remediation_report.csv"
        if not latest.exists():
            return
        if target.exists() and latest.stat().st_mtime < target.stat().st_mtime:
            return
        try:
            target.write_bytes(latest.read_bytes())
        except PermissionError:
            self.logger.warning(
                "Unable to replace locked remediation_report.csv with remediation_report_latest.csv before XML generation."
            )

    def _create_logger(self) -> logging.Logger:
        self.config.logs_folder.mkdir(parents=True, exist_ok=True)
        logger = logging.getLogger("automation")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s - %(message)s")
        file_handler = logging.FileHandler(self.config.logs_folder / "automation.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        return logger

    def _close_logger_handlers(self) -> None:
        for handler in list(self.logger.handlers):
            handler.flush()
            handler.close()
            self.logger.removeHandler(handler)

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Week-3 automated validation evaluation artifacts.")
    parser.add_argument(
        "--config",
        default=str(AutomatedValidationFramework.DEFAULT_CONFIG_PATH),
        help="Path to automation_config.json.",
    )
    args = parser.parse_args()
    summary = AutomatedValidationFramework(config_path=args.config).run()
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
