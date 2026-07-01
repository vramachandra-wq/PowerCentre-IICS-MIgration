import csv
import tempfile
import unittest
from pathlib import Path

from business.validation.executive_summary import ExecutiveSummaryEngine
from business.validation.readiness_engine import MigrationReadinessEngine
from business.validation.remediation_effectiveness import RemediationEffectivenessEngine
from business.validation.risk_assessment import RiskAssessmentEngine


class RemediationReportingTests(unittest.TestCase):
    def test_readiness_improves_after_auto_fix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self._write_sample_reports(output)

            records = MigrationReadinessEngine(output_folder=output).build_report()
            finance = next(record for record in records if record.mapping_name == "SDE_FINANCE")

            self.assertEqual(3, finance.issues_found)
            self.assertEqual(2, finance.issues_auto_fixed)
            self.assertEqual(1, finance.issues_remaining)
            self.assertGreater(finance.readiness_after, finance.readiness_before)

    def test_risk_scores_only_remaining_issues(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self._write_sample_reports(output)

            records = RiskAssessmentEngine(output_folder=output).build_report()
            finance = next(record for record in records if record.mapping_name == "SDE_FINANCE")

            self.assertEqual(20, finance.risk_score)
            self.assertEqual("mapplet_nesting", finance.top_risk_factor)

    def test_effectiveness_and_executive_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self._write_sample_reports(output)

            effectiveness = RemediationEffectivenessEngine(output_folder=output).build_report()
            finance = next(record for record in effectiveness if record.mapping_name == "SDE_FINANCE")
            self.assertEqual(66.67, finance.auto_fix_percentage)

            metrics = ExecutiveSummaryEngine(output_folder=output).build_report()
            metric_map = {metric.metric: metric.value for metric in metrics}
            self.assertEqual("3", metric_map["Total Issues Found"])
            self.assertEqual("2", metric_map["Total Issues Auto Fixed"])
            self.assertEqual("66.67%", metric_map["Auto Fix Rate"])

    @staticmethod
    def _write_sample_reports(output: Path) -> None:
        RemediationReportingTests._write_csv(
            output / "datatype_mismatch_report.csv",
            ["column", "source", "target", "severity", "recommendation", "issue_type", "mapping_name", "source_file"],
            [
                {
                    "column": "AMOUNT",
                    "source": "DECIMAL(18,6)",
                    "target": "DECIMAL(28,0)",
                    "severity": "HIGH",
                    "recommendation": "Retain source scale.",
                    "issue_type": "scale_mismatch",
                    "mapping_name": "SDE_FINANCE",
                    "source_file": "finance.XML",
                },
                {
                    "column": "DESCRIPTION",
                    "source": "VARCHAR(500)",
                    "target": "VARCHAR(100)",
                    "severity": "HIGH",
                    "recommendation": "Increase target length.",
                    "issue_type": "truncation_risk",
                    "mapping_name": "SDE_FINANCE",
                    "source_file": "finance.XML",
                },
            ],
        )
        RemediationReportingTests._write_csv(
            output / "validation_report.csv",
            ["Issue", "Severity", "Recommendation", "Auto Fixed", "Fix Applied", "Before Value", "After Value", "Status", "Asset"],
            [
                {
                    "Issue": "Oracle Curly Brace Syntax",
                    "Severity": "MEDIUM",
                    "Recommendation": "Replace Oracle escape syntax.",
                    "Auto Fixed": "False",
                    "Fix Applied": "",
                    "Before Value": "SDE_FINANCE",
                    "After Value": "SDE_FINANCE",
                    "Status": "Open",
                    "Asset": "SDE_FINANCE",
                },
                {
                    "Issue": "Mapplet Nesting Detected",
                    "Severity": "HIGH",
                    "Recommendation": "Flatten nested mapplet logic.",
                    "Auto Fixed": "False",
                    "Fix Applied": "",
                    "Before Value": "SDE_FINANCE",
                    "After Value": "SDE_FINANCE",
                    "Status": "Open",
                    "Asset": "SDE_FINANCE",
                }
            ],
        )
        RemediationReportingTests._write_csv(
            output / "remediation_report.csv",
            [
                "Issue",
                "Severity",
                "Recommendation",
                "Auto Fixed",
                "Fix Applied",
                "Before Value",
                "After Value",
                "Status",
                "Asset",
                "Approval Required",
                "Manual Remediation Required",
            ],
            [
                {
                    "Issue": "scale_mismatch",
                    "Severity": "HIGH",
                    "Recommendation": "Retain source scale.",
                    "Auto Fixed": "True",
                    "Fix Applied": "copy_source_scale",
                    "Before Value": "DECIMAL(28,0)",
                    "After Value": "DECIMAL(18,6)",
                    "Status": "Resolved",
                    "Asset": "SDE_FINANCE",
                    "Approval Required": "False",
                    "Manual Remediation Required": "False",
                },
                {
                    "Issue": "oracle_curly_brace_syntax",
                    "Severity": "MEDIUM",
                    "Recommendation": "Replace Oracle escape syntax.",
                    "Auto Fixed": "True",
                    "Fix Applied": "propose_oracle_escape_fix",
                    "Before Value": "{fn NOW()}",
                    "After Value": "NOW()",
                    "Status": "Resolved",
                    "Asset": "SDE_FINANCE",
                    "Approval Required": "False",
                    "Manual Remediation Required": "False",
                },
                {
                    "Issue": "mapplet_nesting",
                    "Severity": "HIGH",
                    "Recommendation": "Flatten nested mapplet logic.",
                    "Auto Fixed": "False",
                    "Fix Applied": "",
                    "Before Value": "SDE_FINANCE",
                    "After Value": "SDE_FINANCE",
                    "Status": "Manual Remediation Required",
                    "Asset": "SDE_FINANCE",
                    "Approval Required": "False",
                    "Manual Remediation Required": "True",
                },
            ],
        )

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
