"""
Business orchestrator for complete PowerCenter to IICS migration workflow.
"""

from __future__ import annotations

import base64
import csv
import json
from pathlib import Path
from typing import Any, Callable

from business.integration import IICSAdapter
from business.migration.migration_service import EnterpriseMigrationPipeline
from business.validation.Rule_Based_Validation_Engine import build_remediation_report
from business.validation.batch_xml_processor import run_batch_xml_remediation
from business.validation.datatype_harmonization import build_datatype_mismatch_report
from business.validation.readiness_engine import build_migration_readiness_report
from business.validation.remediation_effectiveness import build_remediation_effectiveness_report
from business.validation.risk_assessment import build_risk_assessment_report
from business.validation.validation_engine import build_validation_report
from common.config.config import AppConfig
from automation.automated_validation_framework import AutomatedValidationFramework


ProgressCallback = Callable[[int, str], None]


class MigrationOrchestrator:
    """Coordinates the existing migration modules for REST APIs."""

    REPORT_FILES = {
        "migration_readiness_report": "post_remediation_migration_readiness_report.csv",
        "validation_report": "validation_report.csv",
        "remediation_report": "remediation_report.csv",
        "auto_fix_effectiveness_report": "post_remediation_auto_fix_effectiveness_report.csv",
        "risk_assessment_report": "risk_assessment_report.csv",
        "dashboard_dataset_csv": "automation/dashboard_dataset.csv",
        "dashboard_dataset_json": "automation/dashboard_dataset.json",
        "evaluation_dataset_csv": "automation/evaluation_dataset.csv",
        "evaluation_dataset_json": "automation/evaluation_dataset.json",
        "evaluation_matrix_csv": "automation/evaluation_matrix.csv",
        "ai_evaluation_matrix_csv": "automation/ai_evaluation_matrix.csv",
    }

    def __init__(
        self,
        config: AppConfig,
        logger,
        iics_adapter: IICSAdapter | None = None,
        automation_config: str | Path = "config/automation_config.json",
    ) -> None:
        self.config = config
        self.logger = logger
        self.iics_adapter = iics_adapter or IICSAdapter(logger=logger)
        self.automation_config = automation_config
        self.project_root = Path.cwd()
        self.output_folder = self._resolve(config.paths.output_folder)
        self.input_folder = self._resolve(config.paths.xml_folder)

    def run(
        self,
        *,
        job_id: str,
        uploaded_xml_name: str | None = None,
        uploaded_xml_content: str | None = None,
        persist_to_mysql: bool = False,
        progress: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Execute the complete migration workflow and return a summary."""

        self._progress(job_id, progress, 5, "Preparing migration inputs.")
        self._prepare_uploaded_xml(uploaded_xml_name, uploaded_xml_content)
        self._ensure_xml_inputs()

        self._progress(job_id, progress, 15, "Running metadata extraction and complexity analysis.")
        enterprise_summary = EnterpriseMigrationPipeline(config=self.config, logger=self.logger).run(
            persist_to_mysql=persist_to_mysql
        )

        self._progress(job_id, progress, 40, "Running datatype, validation, and remediation engines.")
        datatype_findings = build_datatype_mismatch_report(config=self.config, logger=self.logger)
        validation_issues = build_validation_report(config=self.config, logger=self.logger)
        remediation_results, revalidation_summary = build_remediation_report(config=self.config, logger=self.logger)
        run_batch_xml_remediation(input_folder=self.config.paths.xml_folder, output_folder=self.config.paths.output_folder)

        self._progress(job_id, progress, 60, "Generating readiness, risk, and effectiveness reports.")
        readiness_records = build_migration_readiness_report(config=self.config, logger=self.logger)
        risk_records = build_risk_assessment_report(config=self.config, logger=self.logger)
        effectiveness_records = build_remediation_effectiveness_report(config=self.config, logger=self.logger)

        self._progress(job_id, progress, 75, "Generating dashboard and evaluation datasets.")
        automation_summary = AutomatedValidationFramework(config_path=self.automation_config).run()

        self._progress(job_id, progress, 90, "Invoking IICS adapter.")
        iics_deployment = self.iics_adapter.deploy(
            {
                "name": f"migration_job_{job_id}",
                "enterprise_summary": enterprise_summary,
                "readiness_records": len(readiness_records),
            }
        )

        result = {
            "job_id": job_id,
            "status": "Completed",
            "readiness_score": self._readiness_score(readiness_records),
            "validation_summary": self._validation_summary(),
            "auto_fix_accuracy": self._auto_fix_accuracy(effectiveness_records),
            "generated_report_locations": self.generated_reports(),
            "iics_deployment": iics_deployment,
            "details": {
                "enterprise": enterprise_summary,
                "datatype_findings": len(datatype_findings),
                "validation_issues": len(validation_issues),
                "remediation_results": len(remediation_results),
                "revalidation": {
                    "before_fix_issues": revalidation_summary.before_fix_issues,
                    "after_fix_issues": revalidation_summary.after_fix_issues,
                    "resolved_issues": revalidation_summary.resolved_issues,
                },
                "risk_records": len(risk_records),
                "automation": automation_summary,
            },
        }
        self._progress(job_id, progress, 100, "Migration completed.")
        return result

    def generated_reports(self) -> dict[str, str]:
        """Return generated report paths that currently exist."""

        reports: dict[str, str] = {}
        for name, relative in self.REPORT_FILES.items():
            path = self.output_folder / relative
            if path.exists():
                reports[name] = str(path)
        return reports

    def dashboard_dataset(self) -> tuple[list[dict[str, Any]], str | None]:
        """Return dashboard dataset rows from JSON or CSV artifact."""

        json_path = self.output_folder / "automation" / "dashboard_dataset.json"
        if json_path.exists():
            with json_path.open("r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
            return (payload if isinstance(payload, list) else [], str(json_path))
        csv_path = self.output_folder / "automation" / "dashboard_dataset.csv"
        if csv_path.exists():
            return self._read_csv(csv_path), str(csv_path)
        return [], None

    def _prepare_uploaded_xml(self, name: str | None, content: str | None) -> None:
        if not content:
            return
        file_name = Path(name or "uploaded_powercenter.xml").name
        if not file_name.lower().endswith(".xml"):
            raise ValueError("Uploaded file name must end with .xml.")
        self.input_folder.mkdir(parents=True, exist_ok=True)
        xml_text = self._decode_xml_content(content)
        (self.input_folder / file_name).write_text(xml_text, encoding="utf-8")

    def _ensure_xml_inputs(self) -> None:
        if not self.input_folder.exists() or not list(self.input_folder.glob("*.XML")) + list(self.input_folder.glob("*.xml")):
            raise FileNotFoundError(f"No XML files found in {self.input_folder}.")

    def _decode_xml_content(self, content: str) -> str:
        stripped = content.strip()
        if stripped.startswith("<"):
            return stripped
        try:
            return base64.b64decode(stripped).decode("utf-8")
        except Exception as exc:
            raise ValueError("uploaded_xml_content must be raw XML or base64-encoded XML.") from exc

    def _readiness_score(self, readiness_records: list[Any]) -> float | None:
        scores = [
            float(getattr(record, "readiness_after"))
            for record in readiness_records
            if getattr(record, "readiness_after", None) is not None
        ]
        return round(sum(scores) / len(scores), 2) if scores else None

    def _auto_fix_accuracy(self, effectiveness_records: list[Any]) -> float | None:
        scores = [
            float(getattr(record, "auto_fix_percentage"))
            for record in effectiveness_records
            if getattr(record, "auto_fix_percentage", None) is not None
        ]
        return round(sum(scores) / len(scores), 2) if scores else None

    def _validation_summary(self) -> dict[str, Any]:
        rows = self._read_csv(self.output_folder / "validation_report.csv")
        severity_counts: dict[str, int] = {}
        open_issues = 0
        resolved_issues = 0
        for row in rows:
            severity = (row.get("Severity") or "UNKNOWN").upper()
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            status = (row.get("Status") or "").lower()
            if status in {"resolved", "fixed", "closed"}:
                resolved_issues += 1
            else:
                open_issues += 1
        return {
            "total_issues": len(rows),
            "open_issues": open_issues,
            "resolved_issues": resolved_issues,
            "severity_counts": severity_counts,
        }

    def _read_csv(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    def _progress(self, job_id: str, callback: ProgressCallback | None, percentage: int, message: str) -> None:
        if callback:
            callback(percentage, message)
        self.logger.info("Migration job %s progress=%s message=%s", job_id, percentage, message)

    def _resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate
