"""
Support automated validation framework for automation data and validation workflows.
Prepares metrics, findings, and AI assistance outputs.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from automation.consolidated_findings import ConsolidatedFindingsBuilder
from automation.dashboard_dataset import DashboardDatasetBuilder
from automation.evaluation_dataset import EvaluationDatasetBuilder
from automation.evaluation_matrix import EvaluationMatrixBuilder, ReportRepository
from automation.mysql_persistence import MySQLReportPersistence
from automation.validation_summary import ValidationSummaryBuilder
from automation.ai import AIRecommendationConfig, AIRecommendationService
from business.validation.ai_evaluation import AIEvaluationBuilder
from business.validation.ai_validation_engine import AIValidationConfig, AIValidationEngine


@dataclass(frozen=True)
class AutomationConfig:
    """Stores configuration values used by the application."""

    output_folder: Path
    reports_folder: Path
    logs_folder: Path
    validation_rules_path: Path
    enable_metrics: bool = True
    enable_dashboard_export: bool = True
    enable_evaluation_dataset: bool = True
    enable_consolidated_findings: bool = True
    enable_validation_summary: bool = True
    enable_ai_evaluation: bool = True
    enable_ai_recommendations: bool = True
    execute_existing_modules: bool = True
    ai_validation: AIValidationConfig = field(default_factory=AIValidationConfig)
    ai_recommendation: AIRecommendationConfig = field(default_factory=AIRecommendationConfig)


class AutomatedValidationFramework:
    """Encapsulates automated validation framework behavior for migration workflows."""

    DEFAULT_CONFIG_PATH = Path("config/automation_config.json")

    def __init__(self, config_path: str | Path | None = None, logger: logging.Logger | None = None) -> None:
        """Initialize migration data using the provided config_path and logger."""

        self.project_root = Path.cwd()
        self.config_path = self._resolve(config_path or self.DEFAULT_CONFIG_PATH)
        self.raw_config = self._load_raw_config(self.config_path)
        self.config = self._load_config(self.config_path)
        self.logger = logger or self._create_logger()
        self.repository = ReportRepository(self.config.output_folder, self.config.reports_folder)

    def run(self) -> dict[str, Any]:
        """Run migration data for the migration workflow."""

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

            if self.config.enable_ai_evaluation:
                validation_engine = AIValidationEngine(self.repository, self.config.ai_validation)
                ai_started = datetime.now(UTC)
                ai_results = validation_engine.validate()
                ai_builder = AIEvaluationBuilder(
                    self.repository,
                    high_confidence_threshold=self.config.ai_validation.high_confidence_threshold,
                )
                ai_dataset = ai_builder.build_dataset(ai_results)
                ai_elapsed_ms = int((datetime.now(UTC) - ai_started).total_seconds() * 1000)
                ai_summary = ai_builder.summarize(ai_results, ai_dataset, ai_elapsed_ms, self.config.ai_validation.max_records)
                outputs["ai_evaluation"] = {key: str(path) for key, path in ai_builder.write(ai_dataset, ai_summary).items()}
                error_rows = [row for row in ai_dataset if row.get("ml_decision") == "ERROR"]
                if error_rows:
                    self.logger.warning(
                        "AI evaluation generated %s error rows. First error=%s",
                        len(error_rows),
                        error_rows[0].get("error", ""),
                    )
                self.logger.info("AI evaluation generated. rows=%s accuracy=%s", len(ai_dataset), ai_summary.ml_accuracy)

            end_time = datetime.now(UTC)
            full_automation_seconds = round((end_time - start_time).total_seconds(), 2)
            self.logger.info(
                "Automated validation framework completed at %s. files_processed=%s outputs=%s",
                end_time.isoformat(),
                len({record.xml_name for record in matrix_records if record.xml_name}),
                outputs,
            )
            outputs["mysql_persistence"] = self._persist_reports(start_time)
            mysql_end_time = datetime.now(UTC)
            full_with_mysql_seconds = round((mysql_end_time - start_time).total_seconds(), 2)
            timing_summary = {
                "Start Time": start_time.isoformat(),
                "Automation End Time": end_time.isoformat(),
                "MySQL Persistence End Time": mysql_end_time.isoformat(),
                "Full Automation Time (sec)": full_automation_seconds,
                "End-to-End Process Time (with MySQL) (sec)": full_with_mysql_seconds,
            }
            outputs["timing_summary"] = str(self.repository.write_json("automation_timing_summary.json", timing_summary))
            return {
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "mysql_end_time": mysql_end_time.isoformat(),
                "full_automation_time_seconds": full_automation_seconds,
                "full_automation_mysql_time_seconds": full_with_mysql_seconds,
                "files_processed": len({record.xml_name for record in matrix_records if record.xml_name}),
                "evaluation_records": len(matrix_records),
                "modules_executed": modules_executed,
                "outputs": outputs,
            }
        finally:
            self._close_logger_handlers()

    def _validate_prerequisites(self) -> None:
        """Validate prerequisites for the migration workflow."""

        required = [
            self.config.output_folder / "metadata_tables" / "mappings.csv",
            self.config.output_folder / "complexity_classification_report.csv",
            self.config.output_folder / "validation_report.csv",
            self.config.output_folder / "datatype_mismatch_report.csv",
        ]
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            message = "Missing prerequisite output artifact(s): " + ", ".join(missing)
            self.logger.error(message)
            raise FileNotFoundError(message)

    def _load_config(self, path: Path) -> AutomationConfig:
        """Load config using the provided path."""

        payload = self._load_raw_config(path)
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
            enable_ai_evaluation=bool(features.get("enable_ai_evaluation", True)),
            enable_ai_recommendations=bool(features.get("enable_ai_recommendations", True)),
            execute_existing_modules=bool(features.get("execute_existing_modules", True)),
            ai_validation=self._load_ai_validation_config(payload.get("ai_validation", {})),
            ai_recommendation=self._load_ai_recommendation_config(payload.get("ai_recommendation", {})),
        )

    @staticmethod
    def _load_raw_config(path: Path) -> dict[str, Any]:
        """Load raw JSON config using the provided path."""

        if not path.exists():
            raise FileNotFoundError(f"Automation config not found: {path}")
        with path.open("r", encoding="utf-8-sig") as config_file:
            return json.load(config_file)


    @staticmethod
    def _load_ai_validation_config(payload: dict[str, Any]) -> AIValidationConfig:
        """Load ai validation config using the provided payload."""

        return AIValidationConfig(
            model_name=str(payload.get("model_name", "Qwen/Qwen3-8B")),
            hf_token_env=str(payload.get("hf_token_env", "HF_TOKEN")),
            max_records=int(payload.get("max_records", 200)),
            max_new_tokens=int(payload.get("max_new_tokens", 256)),
            temperature=float(payload.get("temperature", 0.0)),
            timeout_seconds=int(payload.get("timeout_seconds", 60)),
            high_confidence_threshold=int(payload.get("high_confidence_threshold", 90)),
            provider=str(payload.get("provider", "auto")),
            max_workers=int(payload.get("max_workers", 8)),
        )

    @staticmethod
    def _load_ai_recommendation_config(payload: dict[str, Any]) -> AIRecommendationConfig:
        """Load ai recommendation config using the provided payload."""

        return AIRecommendationConfig(
            model_name=str(payload.get("model_name", "Qwen/Qwen3-8B")),
            hf_token_env=str(payload.get("hf_token_env", "HF_TOKEN")),
            max_records=int(payload.get("max_records", 200)),
            max_new_tokens=int(payload.get("max_new_tokens", 512)),
            temperature=float(payload.get("temperature", 0.0)),
            timeout_seconds=int(payload.get("timeout_seconds", 60)),
            provider=str(payload.get("provider", "auto")),
            enabled=bool(payload.get("enabled", True)),
            max_workers=int(payload.get("max_workers", 8)),
        )

    def _execute_existing_modules(self) -> list[str]:
        """Handle execute existing modules for the migration workflow."""
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
            ("migration_readiness", build_migration_readiness_report),
            ("risk_assessment", build_risk_assessment_report),
            ("remediation_effectiveness", build_remediation_effectiveness_report),
            ("updated_xml_generation", run_batch_xml_remediation),
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
        """Handle sync latest remediation report for the migration workflow."""

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

    def _persist_reports(self, runtime_timestamp: datetime) -> dict[str, int]:
        """Persist generated report artifacts into MySQL."""

        try:
            persistence = MySQLReportPersistence.from_project_config(
                project_root=self.project_root,
                output_folder=self.config.output_folder,
                reports_folder=self.config.reports_folder,
                logs_folder=self.config.logs_folder,
                payload=self.raw_config,
                logger=self.logger,
            )
            return persistence.persist_all(runtime_timestamp)
        except Exception as exc:
            self.logger.warning("Generated reports were not persisted to MySQL: %s", exc)
            return {"error": str(exc)}

    def _create_logger(self) -> logging.Logger:
        """Create logger for the migration workflow."""

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
        """Handle close logger handlers for the migration workflow."""

        for handler in list(self.logger.handlers):
            handler.flush()
            handler.close()
            self.logger.removeHandler(handler)

    def _resolve(self, path: str | Path) -> Path:
        """Handle resolve using the provided path."""

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def main() -> None:
    """Handle main for the migration workflow."""

    parser = argparse.ArgumentParser(description="Generate automated validation evaluation artifacts.")
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



