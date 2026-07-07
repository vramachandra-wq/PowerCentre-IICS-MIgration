"""
Support test validation engine for automated regression coverage.
Verifies migration parsing, validation, API, and AI behavior.
"""

import unittest

from business.validation.validation_engine import ValidationEngine


class ValidationEngineTests(unittest.TestCase):
    """Encapsulates validation engine tests behavior for migration workflows."""

    def test_rules_repository_loads_required_day2_rules(self) -> None:
        """Verify rules repository loads required day2 rules behavior."""

        engine = ValidationEngine(output_folder="output")

        self.assertGreaterEqual(len(engine.rules), 40)
        self.assertTrue(all("rule_id" in rule for rule in engine.rules))
        self.assertTrue(all("detection_logic" in rule for rule in engine.rules))

    def test_select_columns_handles_nested_functions(self) -> None:
        """Verify select columns handles nested functions behavior."""

        columns = ValidationEngine._select_columns(
            "select a, concat(b, c) as bc, to_date(d, 'YYYY-MM-DD') as d1 from table_a"
        )

        self.assertEqual(["a", "concat(b, c) as bc", "to_date(d, 'YYYY-MM-DD') as d1"], columns)

    def test_datatype_issue_rule_consumes_day1_findings(self) -> None:
        """Verify datatype issue rule consumes day1 findings behavior."""

        engine = ValidationEngine(output_folder="output")
        rule = {
            "rule_id": "VAL-012",
            "rule_name": "Scale Mismatch",
            "category": "Datatype Rules",
            "severity": "HIGH",
            "detection_logic": {"type": "datatype_issue", "issue_types": ["scale_mismatch"]},
            "recommendation": "Retain original numeric scale and review rounding behavior.",
        }
        engine.datatype_findings = [
            {
                "column": "SALARY_ANNL",
                "source": "DECIMAL(18,6)",
                "target": "DECIMAL(28,0)",
                "issue_type": "scale_mismatch",
                "source_file": "sample.XML",
            }
        ]

        issues = engine._datatype_issue(rule)

        self.assertEqual(1, len(issues))
        self.assertEqual("VAL-012", issues[0].rule_id)


if __name__ == "__main__":
    unittest.main()
