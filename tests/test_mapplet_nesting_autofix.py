"""
Support mapplet nesting auto-fix regression coverage.
"""

import csv
import unittest
from pathlib import Path
from uuid import uuid4

from automation.ai.recommendation_engine import RecommendationEngine
from automation.evaluation_matrix import ReportRepository
from business.validation.Rule_Based_Validation_Engine import Rule_Based_Validation_Engine
from business.validation.validation_engine import ValidationEngine, ValidationIssue


class MappletNestingAutoFixTests(unittest.TestCase):
    """Encapsulates mapplet nesting rule-based remediation tests."""

    def test_mapplet_depth_classification_for_simple_medium_high_and_no_nesting(self) -> None:
        """Verify mapplet depth classification behavior."""

        validator = ValidationEngine(output_folder="output")
        validator.tables = {"instances": self._nested_instances(depth=1)}

        issues = validator._mapplet_nesting(self._rule())
        by_asset = {issue.asset: issue for issue in issues}

        self.assertEqual(1, by_asset["MPL_A"].mapplet_depth)
        self.assertEqual("SIMPLE", by_asset["MPL_A"].mapplet_complexity)
        self.assertFalse(by_asset["MPL_A"].ai_recommendation_required)
        validator.tables = {"instances": self._nested_instances(depth=2)}
        by_asset = {issue.asset: issue for issue in validator._mapplet_nesting(self._rule())}
        self.assertEqual(2, by_asset["MPL_A"].mapplet_depth)
        self.assertEqual("MEDIUM", by_asset["MPL_A"].mapplet_complexity)
        self.assertFalse(by_asset["MPL_A"].ai_recommendation_required)
        validator.tables = {"instances": self._nested_instances(depth=3)}
        by_asset = {issue.asset: issue for issue in validator._mapplet_nesting(self._rule())}
        self.assertEqual(3, by_asset["MPL_A"].mapplet_depth)
        self.assertEqual("HIGH", by_asset["MPL_A"].mapplet_complexity)
        self.assertTrue(by_asset["MPL_A"].manual_review_required)

        validator.tables = {"instances": [{"file_name": "sample.XML", "mapping_name": "M", "instance_name": "EXP", "instance_type": "TRANSFORMATION", "transformation_name": "EXP", "transformation_type": "Expression"}]}
        self.assertEqual([], validator._mapplet_nesting(self._rule()))

    def test_depth_five_and_circular_reference_are_high_complexity(self) -> None:
        """Verify deep and circular nesting remain AI/manual routed."""

        validator = ValidationEngine(output_folder="output")
        validator.tables = {"instances": self._nested_instances(depth=5)}
        deep = {issue.asset: issue for issue in validator._mapplet_nesting(self._rule())}
        self.assertEqual(5, deep["MPL_A"].mapplet_depth)
        self.assertEqual("HIGH", deep["MPL_A"].mapplet_complexity)
        self.assertTrue(deep["MPL_A"].ai_recommendation_required)

        validator.tables = {
            "instances": [
                self._mapplet("sample.XML", "M_PARENT", "MPL_A"),
                self._mapplet("sample.XML", "MPL_A", "MPL_B"),
                self._mapplet("sample.XML", "MPL_B", "MPL_A"),
            ]
        }
        circular = {issue.asset: issue for issue in validator._mapplet_nesting(self._rule())}
        self.assertEqual("HIGH", circular["MPL_A"].mapplet_complexity)
        self.assertTrue(circular["MPL_A"].manual_review_required)

    def test_medium_mapplet_nesting_is_flattened_recursively(self) -> None:
        """Verify depth-two mapplets are flattened into parent metadata."""

        engine = Rule_Based_Validation_Engine(output_folder="output")
        engine.tables = self._flatten_tables()
        issue = ValidationIssue(
            rule_id="VAL-028",
            issue="Mapplet Nesting detected. Depth=2; Complexity=MEDIUM.",
            severity="MEDIUM",
            asset="MPL_A",
            recommendation="Flatten mapplet.",
            source_file="sample.XML",
            mapplet_depth=2,
            mapplet_complexity="MEDIUM",
        )

        result = engine._remediate_mapplet_nesting(issue)

        self.assertTrue(result.auto_fixed)
        self.assertEqual("Auto Fixed", result.status)
        self.assertEqual("Medium", result.mapplet_complexity)
        self.assertFalse(result.ai_recommendation_required)
        instance_names = {row["instance_name"] for row in engine.tables["instances"]}
        self.assertNotIn("MPL_A", instance_names)
        self.assertIn("MPL_A_MPL_B_EXP_CHILD", instance_names)
        self.assertIn("MPL_A_EXP_PARENT", instance_names)
        self.assertTrue(any(row["transformation_name"] == "MPL_A_MPL_B_EXP_CHILD" for row in engine.tables["ports"]))
        self.assertTrue(any(row["from_instance"] == "SRC" and row["to_instance"] == "MPL_A_Input" for row in engine.tables["connectors"]))

    def test_high_mapplet_nesting_remains_manual_and_ai_routed(self) -> None:
        """Verify high complexity mapplets are not auto-fixed."""

        engine = Rule_Based_Validation_Engine(output_folder="output")
        engine.tables = self._flatten_tables()
        issue = ValidationIssue(
            rule_id="VAL-028",
            issue="Mapplet Nesting detected. Depth=3; Complexity=HIGH.",
            severity="HIGH",
            asset="MPL_A",
            recommendation="Manual review.",
            source_file="sample.XML",
            mapplet_depth=3,
            mapplet_complexity="HIGH",
        )

        result = engine._remediate_mapplet_nesting(issue)

        self.assertFalse(result.auto_fixed)
        self.assertEqual("Manual Review Required", result.status)
        self.assertTrue(result.ai_recommendation_required)
        self.assertIn("MPL_A", {row["instance_name"] for row in engine.tables["instances"]})

    def test_simple_and_medium_mapplet_rows_are_not_sent_to_ai(self) -> None:
        """Verify simple and medium mapplet findings are excluded from AI input."""

        root = Path.cwd() / ".test_tmp" / f"mapplet_ai_{uuid4().hex}"
        output = root / "output"
        reports = root / "automation"
        self._write_csv(
            output / "validation_report.csv",
            ["Issue", "Severity", "Recommendation", "Status", "Asset", "Mapplet Complexity", "AI Recommendation Required"],
            [
                {"Issue": "Mapplet Nesting detected.", "Severity": "MEDIUM", "Recommendation": "Flatten.", "Status": "Open", "Asset": "MPL_A", "Mapplet Complexity": "Simple", "AI Recommendation Required": "False"},
                {"Issue": "Mapplet Nesting detected.", "Severity": "HIGH", "Recommendation": "Review.", "Status": "Open", "Asset": "MPL_C", "Mapplet Complexity": "High", "AI Recommendation Required": "True"},
            ],
        )

        failures = RecommendationEngine(ReportRepository(output, reports)).build_failures()

        self.assertEqual(1, len(failures))
        self.assertEqual("MPL_C", failures[0].object_name)

    @staticmethod
    def _rule() -> dict[str, object]:
        """Return the configured mapplet nesting validation rule."""

        return {
            "rule_id": "VAL-028",
            "rule_name": "Mapplet Nesting",
            "category": "Transformation Rules",
            "severity": "HIGH",
            "detection_logic": {
                "type": "mapplet_nesting",
                "max_auto_fix_depth": 2,
                "complexity_thresholds": {"simple_depth": 1, "medium_depth": 2, "high_depth": 3},
            },
            "severity_by_complexity": {"SIMPLE": "MEDIUM", "MEDIUM": "MEDIUM", "HIGH": "HIGH"},
            "recommendation": "Flatten mapplet.",
        }

    @classmethod
    def _nested_instances(cls, depth: int) -> list[dict[str, str]]:
        """Build nested mapplet instance rows."""

        rows = [cls._mapplet("sample.XML", "M_PARENT", "MPL_A")]
        letters = ["A", "B", "C", "D", "E"]
        for index in range(1, depth):
            rows.append(cls._mapplet("sample.XML", f"MPL_{letters[index - 1]}", f"MPL_{letters[index]}"))
        return rows

    @staticmethod
    def _mapplet(file_name: str, mapping_name: str, instance_name: str) -> dict[str, str]:
        """Build a mapplet instance row."""

        return {
            "file_name": file_name,
            "mapping_name": mapping_name,
            "instance_name": instance_name,
            "instance_type": "MAPPLET",
            "transformation_name": instance_name,
            "transformation_type": "Mapplet",
        }

    @classmethod
    def _flatten_tables(cls) -> dict[str, list[dict[str, str]]]:
        """Build synthetic mapplet metadata for flattening tests."""

        return {
            "instances": [
                cls._mapplet("sample.XML", "M_PARENT", "MPL_A"),
                cls._mapplet("sample.XML", "MPL_A", "MPL_B"),
                {"file_name": "sample.XML", "mapping_name": "MPL_A", "instance_name": "EXP_PARENT", "instance_type": "TRANSFORMATION", "transformation_name": "EXP_PARENT", "transformation_type": "Expression"},
                {"file_name": "sample.XML", "mapping_name": "MPL_B", "instance_name": "EXP_CHILD", "instance_type": "TRANSFORMATION", "transformation_name": "EXP_CHILD", "transformation_type": "Expression"},
            ],
            "transformations": [
                {"file_name": "sample.XML", "mapping_name": "MPL_A", "transformation_name": "EXP_PARENT", "transformation_type": "Expression"},
                {"file_name": "sample.XML", "mapping_name": "MPL_B", "transformation_name": "EXP_CHILD", "transformation_type": "Expression"},
            ],
            "ports": [
                {"file_name": "sample.XML", "mapping_name": "MPL_A", "transformation_name": "EXP_PARENT", "port_name": "PARENT_OUT", "port_type": "OUTPUT"},
                {"file_name": "sample.XML", "mapping_name": "MPL_B", "transformation_name": "EXP_CHILD", "port_name": "CHILD_OUT", "port_type": "OUTPUT"},
            ],
            "connectors": [
                {"file_name": "sample.XML", "mapping_name": "M_PARENT", "from_instance": "SRC", "from_field": "ID", "to_instance": "MPL_A", "to_field": "ID", "from_instance_type": "Source Qualifier", "to_instance_type": "Mapplet"},
                {"file_name": "sample.XML", "mapping_name": "MPL_A", "from_instance": "MPL_B", "from_field": "CHILD_OUT", "to_instance": "EXP_PARENT", "to_field": "PARENT_IN", "from_instance_type": "Mapplet", "to_instance_type": "Expression"},
                {"file_name": "sample.XML", "mapping_name": "MPL_B", "from_instance": "EXP_CHILD", "from_field": "CHILD_OUT", "to_instance": "Output", "to_field": "CHILD_OUT", "from_instance_type": "Expression", "to_instance_type": "Output Transformation"},
            ],
            "sql_overrides": [],
        }

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        """Write a CSV fixture."""

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
