"""
Support test four rules auto fix for automated regression coverage.
Verifies migration parsing, validation, API, and AI behavior.
"""

import csv
import unittest
from pathlib import Path
from uuid import uuid4

from business.validation.Rule_Based_Validation_Engine import Rule_Based_Validation_Engine
from business.validation.validation_engine import ValidationEngine


class FourRulesAutoFixTests(unittest.TestCase):
    """Encapsulates four rules auto fix tests behavior for migration workflows."""

    def test_four_new_remediation_rules_are_loaded(self) -> None:
        """Verify four new remediation rules are loaded behavior."""

        engine = Rule_Based_Validation_Engine(output_folder="output")

        self.assertIn("lookup_hardcoded_schema", engine.rules["auto"])
        self.assertIn("object_name_exceeds_65_characters", engine.rules["auto"])
        self.assertIn("oracle_to_oracle_char_padding", engine.rules["auto"])
        self.assertIn("powercenter_schedule_not_copied", engine.rules["auto"])

    def test_lookup_schema_name_is_removed_before_ai_flow(self) -> None:
        """Verify lookup schema name is removed before ai flow behavior."""

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
        """Verify long name is shortened and references are updated behavior."""

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
        """Verify oracle to oracle char padding detection and trim behavior."""

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
        """Verify schedule config is generated only when metadata is available behavior."""

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
        """Verify auto fixed rows are not used for ai recommendations behavior."""

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
        """Verify oracle tables behavior."""

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
        """Verify write csv behavior."""

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
