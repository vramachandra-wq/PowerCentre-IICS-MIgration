import csv
import json
import tempfile
import unittest
from pathlib import Path

from automation.automated_validation_framework import AutomatedValidationFramework


class AutomatedValidationFrameworkTests(unittest.TestCase):
    def test_framework_generates_ai_ready_outputs_from_existing_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output"
            reports = root / "reports"
            logs = root / "logs"
            config_path = root / "automation_config.json"
            self._write_artifacts(output, root / "validation_rules.json")
            config_path.write_text(
                json.dumps(
                    {
                        "output_folder": str(output),
                        "logs_folder": str(logs),
                        "validation_rules_path": str(root / "validation_rules.json"),
                        "features": {
                            "enable_metrics": True,
                            "enable_dashboard_export": True,
                            "enable_evaluation_dataset": True,
                            "enable_consolidated_findings": True,
                            "enable_validation_summary": True,
                            "execute_existing_modules": False,
                        },
                        "exports": {"reports_folder": str(reports)},
                    }
                ),
                encoding="utf-8",
            )

            summary = AutomatedValidationFramework(config_path=config_path).run()

            self.assertEqual(1, summary["evaluation_records"])
            self.assertTrue((reports / "evaluation_matrix.csv").exists())
            self.assertTrue((reports / "evaluation_dataset.csv").exists())
            self.assertTrue((reports / "evaluation_dataset.json").exists())
            self.assertTrue((reports / "consolidated_findings.json").exists())
            self.assertTrue((reports / "validation_summary.json").exists())
            self.assertTrue((reports / "dashboard_dataset.csv").exists())
            self.assertTrue((reports / "dashboard_dataset.json").exists())
            self.assertTrue((logs / "automation.log").exists())

            matrix = self._read_csv(reports / "evaluation_matrix.csv")
            self.assertEqual("M_SAMPLE", matrix[0]["mapping"])
            self.assertEqual("0", matrix[0]["remaining_unresolved"])
            self.assertIn(matrix[0]["migration_status"], {"READY", "READY_WITH_MONITORING", "NEEDS_REVIEW"})
            dashboard = self._read_csv(reports / "dashboard_dataset.csv")
            self.assertNotIn("root_cause", dashboard[0])
            self.assertNotIn("recommendation", dashboard[0])
            self.assertNotIn("priority", dashboard[0])

    @staticmethod
    def _write_artifacts(output: Path, rules_path: Path) -> None:
        metadata = output / "metadata_tables"
        metadata.mkdir(parents=True)
        rules_path.write_text(json.dumps({"rules": [{"rule_id": "VAL-001"}, {"rule_id": "VAL-002"}]}), encoding="utf-8")
        AutomatedValidationFrameworkTests._write_csv(
            metadata / "mappings.csv",
            [
                "file_name",
                "repository_name",
                "folder_name",
                "mapping_name",
                "is_valid",
                "transformation_count",
                "source_count",
                "target_count",
                "connector_count",
                "instance_count",
                "sql_override_count",
            ],
            [
                {
                    "file_name": "sample.XML",
                    "repository_name": "REP",
                    "folder_name": "FOLDER",
                    "mapping_name": "M_SAMPLE",
                    "is_valid": "YES",
                    "transformation_count": "2",
                    "source_count": "1",
                    "target_count": "1",
                    "connector_count": "0",
                    "instance_count": "0",
                    "sql_override_count": "1",
                }
            ],
        )
        AutomatedValidationFrameworkTests._write_csv(
            metadata / "transformations.csv",
            ["file_name", "mapping_name", "transformation_name", "transformation_type"],
            [
                {
                    "file_name": "sample.XML",
                    "mapping_name": "M_SAMPLE",
                    "transformation_name": "LKP_CUSTOMER",
                    "transformation_type": "Lookup",
                },
                {
                    "file_name": "sample.XML",
                    "mapping_name": "M_SAMPLE",
                    "transformation_name": "RTR_SAMPLE",
                    "transformation_type": "Router",
                },
            ],
        )
        AutomatedValidationFrameworkTests._write_csv(
            metadata / "sessions.csv",
            ["file_name", "session_name", "mapping_name"],
            [{"file_name": "sample.XML", "session_name": "S_SAMPLE", "mapping_name": "M_SAMPLE"}],
        )
        AutomatedValidationFrameworkTests._write_csv(
            metadata / "workflows.csv",
            ["file_name", "workflow_name"],
            [{"file_name": "sample.XML", "workflow_name": "WF_SAMPLE"}],
        )
        AutomatedValidationFrameworkTests._write_csv(
            output / "complexity_classification_report.csv",
            ["XML", "Folder", "Mapping", "Transformation Count", "Complexity", "Score", "Reason"],
            [
                {
                    "XML": "sample.XML",
                    "Folder": "FOLDER",
                    "Mapping": "M_SAMPLE",
                    "Transformation Count": "2",
                    "Complexity": "Medium",
                    "Score": "45",
                    "Reason": "Lookup exists",
                }
            ],
        )
        AutomatedValidationFrameworkTests._write_csv(
            output / "validation_report.csv",
            ["Issue", "Severity", "Asset", "Source File"],
            [{"Issue": "SQL issue", "Severity": "HIGH", "Asset": "M_SAMPLE", "Source File": "sample.XML"}],
        )
        AutomatedValidationFrameworkTests._write_csv(
            output / "datatype_mismatch_report.csv",
            ["issue_type", "severity", "mapping_name", "source_file"],
            [{"issue_type": "scale_mismatch", "severity": "HIGH", "mapping_name": "M_SAMPLE", "source_file": "sample.XML"}],
        )
        AutomatedValidationFrameworkTests._write_csv(
            output / "remediation_report.csv",
            ["Issue", "Auto Fixed", "Asset", "Manual Remediation Required", "Approval Required"],
            [{"Issue": "scale_mismatch", "Auto Fixed": "True", "Asset": "M_SAMPLE", "Manual Remediation Required": "False", "Approval Required": "False"}],
        )
        AutomatedValidationFrameworkTests._write_csv(
            output / "migration_readiness_report.csv",
            [
                "mapping_name",
                "issues_found",
                "issues_auto_fixed",
                "issues_remaining",
                "readiness_before",
                "readiness_after",
                "readiness_category",
            ],
            [
                {
                    "mapping_name": "M_SAMPLE",
                    "issues_found": "2",
                    "issues_auto_fixed": "1",
                    "issues_remaining": "1",
                    "readiness_before": "65",
                    "readiness_after": "82",
                    "readiness_category": "READY",
                }
            ],
        )
        AutomatedValidationFrameworkTests._write_csv(
            output / "risk_assessment_report.csv",
            ["mapping_name", "risk_score", "risk_level", "top_risk_factor"],
            [{"mapping_name": "M_SAMPLE", "risk_score": "20", "risk_level": "LOW", "top_risk_factor": "scale_mismatch"}],
        )
        AutomatedValidationFrameworkTests._write_csv(
            output / "remediation_effectiveness_report.csv",
            ["mapping_name", "issues_found", "auto_fixed", "manual_review", "manual_remediation", "auto_fix_percentage"],
            [
                {
                    "mapping_name": "M_SAMPLE",
                    "issues_found": "2",
                    "auto_fixed": "1",
                    "manual_review": "0",
                    "manual_remediation": "0",
                    "auto_fix_percentage": "50.0",
                }
            ],
        )

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        with path.open("r", newline="", encoding="utf-8") as csv_file:
            return list(csv.DictReader(csv_file))


if __name__ == "__main__":
    unittest.main()
