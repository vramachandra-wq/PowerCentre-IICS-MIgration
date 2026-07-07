"""
Module: tests/test_ai_api_services.py

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
    """
    Represents the FakeRecommendationClient component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def recommend(self, failure: FailureRecord) -> dict[str, object]:
        """
        Executes the recommend workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                failure (object): Value supplied by the caller and used by the workflow.
        
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
            "root_cause": "PowerCenter reusable logic requires IDMC redesign.",
            "recommendation": "Rebuild the unresolved logic with supported IDMC mapping components.",
            "priority": "High",
            "summary": "Manual migration is required for this unresolved failure.",
            "confidence": 88,
        }


class AIAPIServicesTests(unittest.TestCase):
    """
    Represents the AIAPIServicesTests component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def test_recommendation_api_returns_only_required_columns(self) -> None:
        """
        Executes the test_recommendation_api_returns_only_required_columns workflow for automated regression tests.
        
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
        """
        Executes the test_recommendation_api_reports_missing_validation_report workflow for automated regression tests.
        
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

        root = self._workspace_tmp()
        service = AIRecommendationAPIService(repository=ReportRepository(root / "output", root / "automation"))

        with self.assertRaises(APIReportError) as context:
            service.recommend()

        self.assertEqual(404, context.exception.status_code)

    def test_evaluation_api_returns_only_required_matrix_metrics(self) -> None:
        """
        Executes the test_evaluation_api_returns_only_required_matrix_metrics workflow for automated regression tests.
        
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

    def test_evaluation_api_uses_dataset_with_fail_as_positive_class(self) -> None:
        """
        Executes the test_evaluation_api_uses_dataset_with_fail_as_positive_class workflow for automated regression tests.
        
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

        self.assertEqual(100, response["matrix"]["F1 Score"])
        self.assertEqual(100, response["matrix"]["ML Precision"])
        self.assertEqual(100, response["matrix"]["Recall"])
        self.assertEqual(92.5, response["matrix"]["Average Confidence"])

    def test_llm_client_normalizes_qwen_instruct_alias(self) -> None:
        """
        Executes the test_llm_client_normalizes_qwen_instruct_alias workflow for automated regression tests.
        
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

        self.assertEqual(
            "Qwen/Qwen3-8B",
            HuggingFaceQwenRecommendationClient._model_name("Qwen/Qwen3-8B-Instruct"),
        )

    @staticmethod
    def _workspace_tmp() -> Path:
        """
        Executes the _workspace_tmp workflow for automated regression tests.
        
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

        path = Path.cwd() / ".test_tmp" / f"ai_api_{uuid4().hex}"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _write_recommendation_artifacts(output: Path) -> None:
        """
        Executes the _write_recommendation_artifacts workflow for automated regression tests.
        
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


