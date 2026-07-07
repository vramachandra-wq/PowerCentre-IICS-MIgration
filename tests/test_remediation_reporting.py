"""
Module: tests/test_remediation_reporting.py

Purpose:
    This module supports automated regression tests for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the automated regression tests area and verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from business.validation.executive_summary import ExecutiveSummaryEngine
from business.validation.readiness_engine import MigrationReadinessEngine
from business.validation.remediation_effectiveness import RemediationEffectivenessEngine
from business.validation.risk_assessment import RiskAssessmentEngine


class RemediationReportingTests(unittest.TestCase):
    """
    Represents the RemediationReportingTests component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def test_readiness_improves_after_auto_fix(self) -> None:
        """
        Executes the test_readiness_improves_after_auto_fix workflow for automated regression tests.
        
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
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the test_risk_scores_only_remaining_issues workflow for automated regression tests.
        
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
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self._write_sample_reports(output)

            records = RiskAssessmentEngine(output_folder=output).build_report()
            finance = next(record for record in records if record.mapping_name == "SDE_FINANCE")

            self.assertEqual(20, finance.risk_score)
            self.assertEqual("mapplet_nesting", finance.top_risk_factor)

    def test_effectiveness_and_executive_summary(self) -> None:
        """
        Executes the test_effectiveness_and_executive_summary workflow for automated regression tests.
        
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
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the _write_sample_reports workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                output (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
                "AI Assistance Required",
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
                    "AI Assistance Required": "False",
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
                    "AI Assistance Required": "False",
                },
                {
                    "Issue": "mapplet_nesting",
                    "Severity": "HIGH",
                    "Recommendation": "Flatten nested mapplet logic.",
                    "Auto Fixed": "False",
                    "Fix Applied": "",
                    "Before Value": "SDE_FINANCE",
                    "After Value": "SDE_FINANCE",
                    "Status": "AI Assistance Required",
                    "Asset": "SDE_FINANCE",
                    "Approval Required": "False",
                    "AI Assistance Required": "True",
                },
            ],
        )

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        """
        Executes the _write_csv workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
                fieldnames (object): Value supplied by the caller and used by the workflow.
                rows (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
