"""
Module: tests/test_four_rules_auto_fix.py

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
import unittest
from pathlib import Path
from uuid import uuid4

from business.validation.Rule_Based_Validation_Engine import Rule_Based_Validation_Engine
from business.validation.validation_engine import ValidationEngine


class FourRulesAutoFixTests(unittest.TestCase):
    """
    Represents the FourRulesAutoFixTests component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def test_four_new_remediation_rules_are_loaded(self) -> None:
        """
        Executes the test_four_new_remediation_rules_are_loaded workflow for automated regression tests.
        
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

        engine = Rule_Based_Validation_Engine(output_folder="output")

        self.assertIn("lookup_hardcoded_schema", engine.rules["auto"])
        self.assertIn("object_name_exceeds_65_characters", engine.rules["auto"])
        self.assertIn("oracle_to_oracle_char_padding", engine.rules["auto"])
        self.assertIn("powercenter_schedule_not_copied", engine.rules["auto"])

    def test_lookup_schema_name_is_removed_before_ai_flow(self) -> None:
        """
        Executes the test_lookup_schema_name_is_removed_before_ai_flow workflow for automated regression tests.
        
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

        engine = Rule_Based_Validation_Engine(output_folder="output")
        engine.tables = {
            "transformations": [
                {
                    "file_name": "sample.XML",
                    "mapping_name": "M_CUSTOMER",
                    "transformation_name": "LKP_EMPLOYEE",
                    "transformation_type": "Lookup",
                }
            ],
            "sql_overrides": [
                {
                    "file_name": "sample.XML",
                    "mapping_name": "M_CUSTOMER",
                    "context_name": "LKP_EMPLOYEE",
                    "sql_query": "SELECT ID FROM HR.EMPLOYEE WHERE ID = ${SCHEMA_NAME}.EMPLOYEE.ID",
                }
            ],
        }

        changed, before, after = engine._remove_lookup_schema_prefix("LKP_EMPLOYEE")

        self.assertTrue(changed)
        self.assertIn("HR.EMPLOYEE", before)
        self.assertNotIn("HR.EMPLOYEE", after)
        self.assertIn("FROM EMPLOYEE", after)

    def test_long_name_is_shortened_and_references_are_updated(self) -> None:
        """
        Executes the test_long_name_is_shortened_and_references_are_updated workflow for automated regression tests.
        
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

        long_name = "M_" + "CUSTOMER_ACCOUNT_REVENUE_RECOGNITION_AND_BILLING_STATUS_" * 2
        engine = Rule_Based_Validation_Engine(output_folder="output")
        engine.tables = {
            "mappings": [{"mapping_name": long_name}],
            "sessions": [{"mapping_name": long_name, "session_name": "S_CUSTOMER"}],
            "sql_overrides": [{"mapping_name": long_name, "sql_query": "select 1 from dual"}],
        }

        changed, before, after = engine._shorten_object_names(long_name)

        self.assertTrue(changed)
        self.assertIn(long_name, before)
        self.assertLessEqual(len(after.split(", ")[0]), 65)
        self.assertEqual(engine.tables["mappings"][0]["mapping_name"], engine.tables["sessions"][0]["mapping_name"])

    def test_oracle_to_oracle_char_padding_detection_and_trim(self) -> None:
        """
        Executes the test_oracle_to_oracle_char_padding_detection_and_trim workflow for automated regression tests.
        
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

        rule = {
            "rule_id": "VAL-041",
            "rule_name": "Oracle to Oracle Fixed Character Padding",
            "category": "Datatype Rules",
            "severity": "MEDIUM",
            "detection_logic": {"type": "oracle_to_oracle_char_padding"},
            "recommendation": "Trim fixed character fields.",
        }
        validator = ValidationEngine(output_folder="output")
        validator.tables = self._oracle_tables()

        issues = validator._oracle_to_oracle_char_padding(rule)

        self.assertEqual(1, len(issues))
        self.assertEqual("T_CUSTOMER.CUSTOMER_CODE", issues[0].asset)
        engine = Rule_Based_Validation_Engine(output_folder="output")
        engine.tables = self._oracle_tables()
        changed, before, after = engine._trim_oracle_fixed_char_fields("T_CUSTOMER.CUSTOMER_CODE", "sample.XML")
        self.assertTrue(changed)
        self.assertEqual("CUSTOMER_CODE", before)
        self.assertEqual("RTRIM(CUSTOMER_CODE)", after)
        changed, before, after = engine._trim_oracle_fixed_char_fields("T_CUSTOMER.CUSTOMER_CODE", "sample.XML")
        self.assertFalse(changed)
        self.assertEqual("RTRIM(CUSTOMER_CODE)", before)
        self.assertEqual("RTRIM(CUSTOMER_CODE)", after)

    def test_schedule_config_is_generated_only_when_metadata_is_available(self) -> None:
        """
        Executes the test_schedule_config_is_generated_only_when_metadata_is_available workflow for automated regression tests.
        
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

        engine = Rule_Based_Validation_Engine(output_folder="output")
        engine.tables = {
            "workflows": [
                {
                    "workflow_name": "WF_DAILY",
                    "schedule_type": "DAILY",
                    "schedule_interval": "1",
                    "schedule_timezone": "UTC",
                    "schedule_start_time": "01:00",
                }
            ]
        }

        changed, before, after = engine._generate_idmc_schedule_config("WF_DAILY")

        self.assertTrue(changed)
        self.assertEqual("missing", before)
        self.assertIn('"frequency": "DAILY"', after)
        self.assertIn("schedule", engine.tables["workflows"][0])

        engine.tables = {"workflows": [{"workflow_name": "WF_MISSING"}]}
        changed, before, after = engine._generate_idmc_schedule_config("WF_MISSING")
        self.assertFalse(changed)
        self.assertEqual(before, after)

    def test_auto_fixed_rows_are_not_used_for_ai_recommendations(self) -> None:
        """
        Executes the test_auto_fixed_rows_are_not_used_for_ai_recommendations workflow for automated regression tests.
        
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

        from automation.ai.recommendation_engine import RecommendationEngine
        from automation.evaluation_matrix import ReportRepository

        root = Path.cwd() / ".test_tmp" / f"four_rules_{uuid4().hex}"
        output = root / "output"
        reports = root / "automation"
        self._write_csv(
            output / "remediation_report.csv",
            ["Issue", "Severity", "Recommendation", "Auto Fixed", "Status", "Asset"],
            [
                {
                    "Issue": "lookup_hardcoded_schema",
                    "Severity": "MEDIUM",
                    "Recommendation": "Remove schema.",
                    "Auto Fixed": "True",
                    "Status": "Auto Fixed",
                    "Asset": "LKP_EMPLOYEE",
                },
                {
                    "Issue": "powercenter_schedule_not_copied",
                    "Severity": "MEDIUM",
                    "Recommendation": "Copy schedule.",
                    "Auto Fixed": "False",
                    "Status": "Not Applied",
                    "Asset": "WF_MISSING",
                },
            ],
        )

        failures = RecommendationEngine(ReportRepository(output, reports)).build_failures()

        self.assertEqual(1, len(failures))
        self.assertEqual("powercenter_schedule_not_copied", failures[0].failure_type)

    @staticmethod
    def _oracle_tables() -> dict[str, list[dict[str, str]]]:
        """
        Executes the _oracle_tables workflow for automated regression tests.
        
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

        return {
            "sources": [{"file_name": "sample.XML", "source_name": "S_CUSTOMER", "database_type": "Oracle"}],
            "targets": [{"file_name": "sample.XML", "target_name": "T_CUSTOMER", "database_type": "Oracle"}],
            "source_columns": [
                {
                    "file_name": "sample.XML",
                    "source_name": "S_CUSTOMER",
                    "column_name": "CUSTOMER_CODE",
                    "datatype": "CHAR",
                }
            ],
            "target_columns": [
                {
                    "file_name": "sample.XML",
                    "target_name": "T_CUSTOMER",
                    "column_name": "CUSTOMER_CODE",
                    "datatype": "CHAR",
                }
            ],
            "ports": [
                {
                    "file_name": "sample.XML",
                    "port_name": "CUSTOMER_CODE",
                    "expression": "CUSTOMER_CODE",
                }
            ],
        }

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

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
