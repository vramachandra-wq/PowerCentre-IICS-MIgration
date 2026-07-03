import csv
import unittest
from uuid import uuid4
from pathlib import Path

from automation.ai import AIRecommendationConfig, AIRecommendationService
from automation.ai.prompt_builder import RecommendationPromptBuilder
from automation.ai.recommendation_engine import RecommendationEngine
from automation.ai.recommendation_models import FailureRecord
from automation.ai.response_parser import RecommendationResponseParser
from automation.evaluation_matrix import ReportRepository


class FakeRecommendationClient:
    def recommend(self, failure: FailureRecord) -> dict[str, object]:
        return {
            "root_cause": "PowerCenter uses a mapplet pattern that requires IDMC redesign.",
            "recommendation": "Recreate the reusable logic as a supported IDMC mapping task design and validate ports.",
            "priority": "High",
            "summary": "Manual migration is required for the unresolved reusable logic.",
            "confidence": 91,
        }


class FailingRecommendationClient:
    def recommend(self, failure: FailureRecord) -> dict[str, object]:
        raise ValueError("model timeout")


class AIRecommendationAssistantTests(unittest.TestCase):
    def test_prompt_generation_uses_structured_failure_json(self) -> None:
        prompt = RecommendationPromptBuilder().build(self._failure())

        self.assertIn("Return STRICT JSON only", prompt)
        self.assertIn('"mapping": "M_CUSTOMER"', prompt)
        self.assertIn('"failure_type": "mapplet_nesting"', prompt)

    def test_response_parser_validates_json_and_priority(self) -> None:
        parsed = RecommendationResponseParser.parse(
            '<think>hidden</think>{"root_cause":"x","recommendation":"y","priority":"high","summary":"z","confidence":120}'
        )

        self.assertEqual("High", parsed.priority)
        self.assertEqual(100, parsed.confidence)
        with self.assertRaises(ValueError):
            RecommendationResponseParser.parse(
                {"root_cause": "x", "recommendation": "y", "priority": "urgent", "summary": "z"}
            )

    def test_priority_assignment_follows_guidelines(self) -> None:
        critical = self._failure(failure_type="unsupported_transformation", severity="CRITICAL")
        high = self._failure(validation_message="Unsupported functionality requires manual intervention.")
        medium = self._failure(
            failure_type="datatype_mismatch",
            severity="MEDIUM",
            validation_message="Datatype mismatch requires mapping adjustment.",
            auto_fix_status="Open",
        )

        self.assertEqual("Critical", RecommendationEngine.assign_priority(critical))
        self.assertEqual("High", RecommendationEngine.assign_priority(high))
        self.assertEqual("Medium", RecommendationEngine.assign_priority(medium))

    def test_recommendation_report_generation_uses_unresolved_failures_only(self) -> None:
        root = self._workspace_tmp()
        output = root / "output"
        reports = root / "automation"
        self._write_artifacts(output)
        service = AIRecommendationService(
            ReportRepository(output, reports),
            AIRecommendationConfig(max_records=10),
            client=FakeRecommendationClient(),
        )

        results, report = service.run()

        self.assertEqual(1, len(results))
        rows = self._read_csv(report)
        self.assertEqual("WF_CUSTOMER", rows[0]["Workflow"])
        self.assertEqual("mapplet_nesting", rows[0]["Failures"])
        self.assertEqual("High", rows[0]["Priority"])
        self.assertEqual("91", rows[0]["Confidence"])

    def test_failure_handling_writes_fallback_recommendation(self) -> None:
        root = self._workspace_tmp()
        output = root / "output"
        reports = root / "automation"
        self._write_artifacts(output)
        service = AIRecommendationService(
            ReportRepository(output, reports),
            AIRecommendationConfig(max_records=10),
            client=FailingRecommendationClient(),
        )

        results, report = service.run()

        self.assertEqual("model timeout", results[0].error)
        rows = self._read_csv(report)
        self.assertIn("Manual migration review is required", rows[0]["AI Summary"])
        self.assertEqual("model timeout", rows[0]["Error"])

    @staticmethod
    def _failure(**overrides: str) -> FailureRecord:
        values = {
            "workflow": "WF_CUSTOMER",
            "mapping": "M_CUSTOMER",
            "transformation": "MPL_CUSTOMER",
            "object_name": "MPL_CUSTOMER",
            "failure_type": "mapplet_nesting",
            "validation_rule": "VAL-028",
            "validation_message": "Mapplet nesting detected.",
            "auto_fix_status": "Manual Remediation Required",
            "severity": "HIGH",
            "error_details": "",
            "root_cause": "",
            "rule_based_recommendation": "Flatten nested mapplet logic before migration.",
            "source_file": "customer.XML",
        }
        values.update(overrides)
        return FailureRecord(**values)

    @staticmethod
    def _workspace_tmp() -> Path:
        path = Path.cwd() / ".test_tmp" / f"ai_recommendation_{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write_artifacts(output: Path) -> None:
        metadata = output / "metadata_tables"
        metadata.mkdir(parents=True)
        AIRecommendationAssistantTests._write_csv(
            metadata / "mappings.csv",
            ["file_name", "mapping_name"],
            [{"file_name": "customer.XML", "mapping_name": "M_CUSTOMER"}],
        )
        AIRecommendationAssistantTests._write_csv(
            metadata / "workflows.csv",
            ["file_name", "workflow_name"],
            [{"file_name": "customer.XML", "workflow_name": "WF_CUSTOMER"}],
        )
        AIRecommendationAssistantTests._write_csv(
            metadata / "sessions.csv",
            ["file_name", "session_name", "mapping_name"],
            [{"file_name": "customer.XML", "session_name": "S_CUSTOMER", "mapping_name": "M_CUSTOMER"}],
        )
        AIRecommendationAssistantTests._write_csv(
            metadata / "transformations.csv",
            ["file_name", "mapping_name", "transformation_name", "transformation_type"],
            [
                {
                    "file_name": "customer.XML",
                    "mapping_name": "M_CUSTOMER",
                    "transformation_name": "MPL_CUSTOMER",
                    "transformation_type": "Mapplet",
                }
            ],
        )
        AIRecommendationAssistantTests._write_csv(
            output / "complexity_classification_report.csv",
            ["XML", "Mapping"],
            [{"XML": "customer.XML", "Mapping": "M_CUSTOMER"}],
        )
        AIRecommendationAssistantTests._write_csv(
            output / "validation_report.csv",
            ["Issue", "Severity", "Recommendation", "Auto Fixed", "Status", "Rule ID", "Asset", "Source File"],
            [
                {
                    "Issue": "Mapplet Nesting detected.",
                    "Severity": "HIGH",
                    "Recommendation": "Flatten nested mapplet logic before migration.",
                    "Auto Fixed": "False",
                    "Status": "Open",
                    "Rule ID": "VAL-028",
                    "Asset": "MPL_CUSTOMER",
                    "Source File": "customer.XML",
                }
            ],
        )
        AIRecommendationAssistantTests._write_csv(
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
                "Manual Remediation Required",
                "Approval Required",
            ],
            [
                {
                    "Issue": "mapplet_nesting",
                    "Severity": "HIGH",
                    "Recommendation": "Flatten nested mapplet logic before migration.",
                    "Auto Fixed": "False",
                    "Fix Applied": "",
                    "Before Value": "MPL_CUSTOMER",
                    "After Value": "MPL_CUSTOMER",
                    "Status": "Manual Remediation Required",
                    "Asset": "MPL_CUSTOMER",
                    "Manual Remediation Required": "True",
                    "Approval Required": "False",
                },
                {
                    "Issue": "scale_mismatch",
                    "Severity": "HIGH",
                    "Recommendation": "Copy source scale.",
                    "Auto Fixed": "True",
                    "Fix Applied": "copy_source_scale",
                    "Before Value": "NUMBER(10,0)",
                    "After Value": "NUMBER(10,2)",
                    "Status": "Resolved",
                    "Asset": "M_CUSTOMER",
                    "Manual Remediation Required": "False",
                    "Approval Required": "False",
                },
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
