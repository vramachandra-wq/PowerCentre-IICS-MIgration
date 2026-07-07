"""
Support test ai api services for automated regression coverage.
Verifies migration parsing, validation, API, and AI behavior.
"""

import csv
import json
import unittest
from pathlib import Path
from uuid import uuid4

from api.ai_services import AIEvaluationAPIService, AIRecommendationAPIService, APIReportError
from automation.ai import AIRecommendationConfig
from automation.ai.llm_client import HuggingFaceQwenRecommendationClient
from automation.ai.recommendation_models import FailureRecord
from automation.evaluation_matrix import ReportRepository


class FakeRecommendationClient:
    """Wraps external service calls used by the application."""

    def recommend(self, failure: FailureRecord) -> dict[str, object]:
        """Verify recommend behavior."""

        return {
            "root_cause": "PowerCenter reusable logic requires IDMC redesign.",
            "recommendation": "Rebuild the unresolved logic with supported IDMC mapping components.",
            "priority": "High",
            "summary": "Manual migration is required for this unresolved failure.",
            "confidence": 88,
        }


class AIAPIServicesTests(unittest.TestCase):
    """Encapsulates aiapiservices tests behavior for migration workflows."""

    def test_recommendation_api_returns_only_required_columns(self) -> None:
        """Verify recommendation api returns only required columns behavior."""

        root = self._workspace_tmp()
        output = root / "output"
        reports = root / "automation"
        self._write_recommendation_artifacts(output)
        service = AIRecommendationAPIService(
            repository=ReportRepository(output, reports),
            config=AIRecommendationConfig(max_records=5),
            client=FakeRecommendationClient(),
        )

        rows = service.recommend()

        self.assertEqual(1, len(rows))
        self.assertEqual(
            [
                "Workflow -> Session -> Mapping -> Transformations",
                "Assets",
                "Failures",
                "Root Cause",
                "AI Recommendation",
                "Priority",
                "AI Summary",
            ],
            list(rows[0].keys()),
        )

    def test_recommendation_api_reports_missing_validation_report(self) -> None:
        """Verify recommendation api reports missing validation report behavior."""

        root = self._workspace_tmp()
        service = AIRecommendationAPIService(repository=ReportRepository(root / "output", root / "automation"))

        with self.assertRaises(APIReportError) as context:
            service.recommend()

        self.assertEqual(404, context.exception.status_code)

    def test_evaluation_api_returns_only_required_matrix_metrics(self) -> None:
        """Verify evaluation api returns only required matrix metrics behavior."""

        root = self._workspace_tmp()
        output = root / "output"
        reports = root / "automation"
        reports.mkdir(parents=True)
        (reports / "ai_evaluation_summary.json").write_text(
            json.dumps(
                {
                    "matrix": {
                        "Average Confidence": 92.5,
                        "F1 Score": 77.2,
                        "ML Accuracy": 91.0,
                        "ML Precision": 88.0,
                        "Model Success Rate": 96.0,
                        "Recall": 75.0,
                        "Total Evaluations": 12,
                        "Agreement Rate": 1,
                    }
                }
            ),
            encoding="utf-8",
        )

        response = AIEvaluationAPIService(ReportRepository(output, reports)).evaluation()

        self.assertEqual(
            [
                "Average Confidence",
                "F1 Score",
                "ML Accuracy",
                "ML Precision",
                "Model Success Rate",
                "Recall",
                "Total Evaluations",
            ],
            list(response["matrix"].keys()),
        )
        self.assertEqual(91, response["matrix"]["ML Accuracy"])
        self.assertNotIn("Agreement Rate", response["matrix"])

    def test_evaluation_api_prefers_summary_json_over_dataset(self) -> None:
        """Verify evaluation api prefers summary json over dataset behavior."""

        root = self._workspace_tmp()
        output = root / "output"
        reports = root / "automation"
        reports.mkdir(parents=True)
        self._write_csv(
            reports / "ai_evaluation_dataset.csv",
            ["ground_truth", "ml_decision", "confidence"],
            [
                {"ground_truth": "FAIL", "ml_decision": "FAIL", "confidence": "90"},
                {"ground_truth": "FAIL", "ml_decision": "FAIL", "confidence": "95"},
            ],
        )
        (reports / "ai_evaluation_summary.json").write_text(
            json.dumps(
                {
                    "matrix": {
                        "Average Confidence": 92.5,
                        "F1 Score": 0,
                        "Accuracy": 100,
                        "Precision": 0,
                        "Model Success Rate": 100,
                        "Recall": 0,
                        "Total Evaluations": 2,
                    }
                }
            ),
            encoding="utf-8",
        )

        response = AIEvaluationAPIService(ReportRepository(output, reports)).evaluation()

        self.assertEqual(0, response["matrix"]["F1 Score"])
        self.assertEqual(0, response["matrix"]["ML Precision"])
        self.assertEqual(0, response["matrix"]["Recall"])
        self.assertEqual(92.5, response["matrix"]["Average Confidence"])

    def test_llm_client_normalizes_qwen_instruct_alias(self) -> None:
        """Verify llm client normalizes qwen instruct alias behavior."""

        self.assertEqual(
            "Qwen/Qwen3-8B",
            HuggingFaceQwenRecommendationClient._model_name("Qwen/Qwen3-8B-Instruct"),
        )

    @staticmethod
    def _workspace_tmp() -> Path:
        """Verify workspace tmp behavior."""

        path = Path.cwd() / ".test_tmp" / f"ai_api_{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write_recommendation_artifacts(output: Path) -> None:
        """Verify write recommendation artifacts behavior."""

        metadata = output / "metadata_tables"
        metadata.mkdir(parents=True)
        AIAPIServicesTests._write_csv(
            metadata / "mappings.csv",
            ["file_name", "mapping_name"],
            [{"file_name": "customer.XML", "mapping_name": "M_CUSTOMER"}],
        )
        AIAPIServicesTests._write_csv(
            metadata / "workflows.csv",
            ["file_name", "workflow_name"],
            [{"file_name": "customer.XML", "workflow_name": "WF_CUSTOMER"}],
        )
        AIAPIServicesTests._write_csv(
            metadata / "sessions.csv",
            ["file_name", "session_name", "mapping_name"],
            [{"file_name": "customer.XML", "session_name": "S_CUSTOMER", "mapping_name": "M_CUSTOMER"}],
        )
        AIAPIServicesTests._write_csv(
            metadata / "transformations.csv",
            ["file_name", "mapping_name", "transformation_name", "transformation_type"],
            [{"file_name": "customer.XML", "mapping_name": "M_CUSTOMER", "transformation_name": "MPL_CUSTOMER", "transformation_type": "Mapplet"}],
        )
        AIAPIServicesTests._write_csv(
            output / "complexity_classification_report.csv",
            ["XML", "Mapping"],
            [{"XML": "customer.XML", "Mapping": "M_CUSTOMER"}],
        )
        AIAPIServicesTests._write_csv(
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
        AIAPIServicesTests._write_csv(
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
                }
            ],
        )

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



