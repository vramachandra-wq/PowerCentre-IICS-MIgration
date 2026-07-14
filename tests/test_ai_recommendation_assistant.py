"""
Support test ai recommendation assistant for automated regression coverage.
Verifies migration parsing, validation, API, and AI behavior.
"""

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
    """Wraps external service calls used by the application."""

    def recommend(self, failure: FailureRecord) -> dict[str, object]:
        """Verify recommend behavior."""

        return {
            "root_cause": "PowerCenter uses a mapplet pattern that requires IDMC redesign.",
            "recommendation": "Recreate the reusable logic as a supported IDMC mapping task design and validate ports.",
            "priority": "High",
            "summary": "Manual migration is required for the unresolved reusable logic.",
            "confidence": 91,
        }


class FailingRecommendationClient:
    """Wraps external service calls used by the application."""

    def recommend(self, failure: FailureRecord) -> dict[str, object]:
        """Verify recommend behavior."""

        raise ValueError("model timeout")


class AIRecommendationAssistantTests(unittest.TestCase):
    """Encapsulates airecommendation assistant tests behavior for migration workflows."""

    def test_prompt_generation_uses_structured_failure_json(self) -> None:
        """Verify prompt generation uses structured failure json behavior."""

        prompt = RecommendationPromptBuilder().build(self._failure())

        self.assertIn("Return STRICT JSON only", prompt)
        self.assertIn('"mapping": "M_CUSTOMER"', prompt)
        self.assertIn('"failure_type": "mapplet_nesting"', prompt)
        self.assertIn("Recommendation writing requirements", prompt)
        self.assertIn("implementation-oriented", prompt)
        self.assertIn("stakeholder-ready", prompt)
        self.assertIn("Never use the words or phrases: Manual", prompt)

    def test_response_parser_validates_json_and_priority(self) -> None:
        """Verify response parser validates json and priority behavior."""

        parsed = RecommendationResponseParser.parse(
            '<think>hidden</think>{"root_cause":"x","recommendation":"y","priority":"high","summary":"z","confidence":120}'
        )

        self.assertEqual("High", parsed.priority)
        self.assertEqual(100, parsed.confidence)
        sanitized = RecommendationResponseParser.parse(
            {
                "root_cause": "x",
                "recommendation": "Manual fix required.",
                "priority": "High",
                "summary": "Manual intervention is required for this mapping.",
            }
        )
        self.assertNotIn("Manual", sanitized.recommendation)
        self.assertNotIn("Manual", sanitized.summary)
        self.assertEqual("Recreate nested mapplet logic.", RecommendationResponseParser._sanitize_text("Manually recreate nested mapplet logic."))
        with self.assertRaises(ValueError):
            RecommendationResponseParser.parse(
                {"root_cause": "x", "recommendation": "y", "priority": "urgent", "summary": "z"}
            )

    def test_priority_assignment_follows_guidelines(self) -> None:
        """Verify priority assignment follows guidelines behavior."""

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
        """Verify recommendation report generation uses unresolved failures only behavior."""

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
        self.assertEqual("WF_CUSTOMER -> S_CUSTOMER -> M_CUSTOMER -> MPL_CUSTOMER", rows[0]["Workflow -> Session -> Mapping -> Transformations"])
        self.assertEqual("MPL_CUSTOMER", rows[0]["Assets"])
        self.assertEqual("mapplet_nesting", rows[0]["Failures"])
        self.assertEqual("High", rows[0]["Priority"])
        self.assertEqual("91", rows[0]["Confidence"])

    def test_failure_handling_writes_fallback_recommendation(self) -> None:
        """Verify failure handling writes fallback recommendation behavior."""

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
        self.assertIn("AI recommendation assessment indicates", rows[0]["AI Summary"])
        self.assertNotIn("Manual", rows[0]["AI Summary"])
        self.assertIn("AI recommendation", rows[0]["AI Recommendation"])
        self.assertIn("Real-world scenario", rows[0]["AI Recommendation"])
        self.assertIn("readiness posture", rows[0]["AI Recommendation"])
        self.assertNotIn("Manual", rows[0]["AI Recommendation"])
        self.assertEqual("model timeout", rows[0]["Error"])

    def test_ai_only_issue_file_adds_recommendation_rows_without_remediation_rules(self) -> None:
        """Verify ai only issue file adds recommendation rows without remediation rules behavior."""

        root = self._workspace_tmp()
        output = root / "output"
        reports = root / "automation"
        self._write_artifacts(output)
        (output / "pc to iics  errors 1.txt").write_text(
            "\n".join(
                [
                    "1.Error Name=Repository Metadata Synchronization Error",
                    "(Low)",
                    "Why it Occurs=Repository metadata is not refreshed after migration, causing object mismatches.",
                    "How to Fix=Refresh metadata, synchronize repository, and revalidate mappings.",
                ]
            ),
            encoding="utf-8",
        )
        service = AIRecommendationService(
            ReportRepository(output, reports),
            AIRecommendationConfig(max_records=10),
            client=FailingRecommendationClient(),
        )

        results, report = service.run()

        rows = self._read_csv(report)
        added = [row for row in rows if row["Failures"] == "Repository Metadata Synchronization Error"]
        self.assertEqual(2, len(results))
        self.assertEqual(1, len(added))
        self.assertEqual("Low", added[0]["Priority"])
        self.assertEqual("AI-RECOMMENDATION-ONLY", added[0]["Validation Rule"])
        self.assertIn("WF_Migration_Assessment", added[0]["Workflow -> Session -> Mapping -> Transformations"])

    @staticmethod
    def _failure(**overrides: str) -> FailureRecord:
        """Verify failure behavior."""

        values = {
            "workflow": "WF_CUSTOMER",
            "mapping": "M_CUSTOMER",
            "transformation": "MPL_CUSTOMER",
            "object_name": "MPL_CUSTOMER",
            "failure_type": "mapplet_nesting",
            "validation_rule": "VAL-028",
            "validation_message": "Mapplet nesting detected.",
            "auto_fix_status": "Needs Migration Review",
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
        """Verify workspace tmp behavior."""

        path = Path.cwd() / ".test_tmp" / f"ai_recommendation_{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write_artifacts(output: Path) -> None:
        """Verify write artifacts behavior."""

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
        automation = output / "automation"
        AIRecommendationAssistantTests._write_csv(
            automation / "evaluation_matrix.csv",
            ["mapping", "migration_status", "readiness_after", "risk_after", "risk_category", "manual_remediation"],
            [
                {
                    "mapping": "M_CUSTOMER",
                    "migration_status": "READY",
                    "readiness_after": "96",
                    "risk_after": "5",
                    "risk_category": "LOW",
                    "manual_remediation": "1",
                }
            ],
        )
        (automation / "validation_summary.json").write_text('{"overall_readiness": 96}', encoding="utf-8")
        (automation / "consolidated_findings.json").write_text('{"total_validation_failures": 1}', encoding="utf-8")
        (automation / "ai_evaluation_summary.json").write_text(
            '{"matrix": {"ML Accuracy": 100, "Total Evaluations": 1}}',
            encoding="utf-8",
        )

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        """Verify write csv behavior."""

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        """Verify read csv behavior."""

        with path.open("r", newline="", encoding="utf-8") as csv_file:
            return list(csv.DictReader(csv_file))


if __name__ == "__main__":
    unittest.main()

