"""
Module: tests/test_ai_evaluation_framework.py

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
import tempfile
import unittest
from pathlib import Path

from automation.evaluation_matrix import ReportRepository
from business.validation.ai_evaluation import AIEvaluationBuilder
from business.validation.ai_metrics import AIMetricsCalculator, BinaryConfusionMatrix
from business.validation.ai_validation_engine import (
    AIResponseParser,
    AIValidationConfig,
    AIValidationEngine,
)


class FakeAIClient:
    """
    Represents the FakeAIClient component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def validate(self, payload: dict[str, object]) -> dict[str, object]:
        """
        Executes the validate workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                payload (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        decision = "PASS" if payload["ground_truth"] == "PASS" else "FAIL"
        return {
            "decision": decision,
            "confidence": 95,
            "reason": "Matches rule engine ground truth.",
            "recommendation": payload.get("expected_recommendation", ""),
            "readiness_prediction": payload.get("expected_readiness", ""),
            "risk_prediction": payload.get("expected_risk", ""),
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }


class AIMetricsTests(unittest.TestCase):
    """
    Represents the AIMetricsTests component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def test_binary_metrics(self) -> None:
        """
        Executes the test_binary_metrics workflow for automated regression tests.
        
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

        matrix = BinaryConfusionMatrix(tp=8, tn=7, fp=2, fn=3)
        self.assertEqual(80.0, AIMetricsCalculator.precision(matrix))
        self.assertEqual(72.73, AIMetricsCalculator.recall(matrix))
        self.assertEqual(76.19, AIMetricsCalculator.f1_score(80.0, 72.73))

    def test_confidence_and_json_parsing(self) -> None:
        """
        Executes the test_confidence_and_json_parsing workflow for automated regression tests.
        
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

        self.assertEqual(90.0, AIMetricsCalculator.average_confidence([80, 90, 100]))
        parsed = AIResponseParser.parse('{"decision":"PASS","confidence":99}')
        self.assertEqual("PASS", parsed["decision"])
        with self.assertRaises(ValueError):
            AIResponseParser.parse("not json")


class AIEvaluationFrameworkTests(unittest.TestCase):
    """
    Represents the AIEvaluationFrameworkTests component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def test_ai_dataset_matrix_and_dashboard_generation(self) -> None:
        """
        Executes the test_ai_dataset_matrix_and_dashboard_generation workflow for automated regression tests.
        
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
            root = Path(tmp)
            output = root / "output"
            reports = output / "automation"
            self._write_ground_truth(output)
            repository = ReportRepository(output, reports)
            engine = AIValidationEngine(
                repository=repository,
                config=AIValidationConfig(max_records=10, high_confidence_threshold=90),
                client=FakeAIClient(),
            )
            results = engine.validate()
            builder = AIEvaluationBuilder(repository, high_confidence_threshold=90)
            dataset = builder.build_dataset(results)
            summary = builder.summarize(results, dataset)
            paths = builder.write(dataset, summary)

            self.assertEqual(2, len(dataset))
            self.assertEqual(100.0, summary.ml_accuracy)
            self.assertEqual(100.0, summary.model_success_rate)
            self.assertTrue(paths["dataset"].exists())
            self.assertTrue(paths["matrix"].exists())
            self.assertTrue(paths["dashboard"].exists())
            self.assertTrue(paths["extended_dashboard"].exists())

            matrix = self._read_csv(paths["matrix"])[0]
            self.assertEqual("2", matrix["Total Evaluations"])
            self.assertEqual("100.0", matrix["ML Accuracy"])
            dashboard = self._read_csv(paths["extended_dashboard"])[0]
            self.assertIn("ML Accuracy", dashboard)

    @staticmethod
    def _write_ground_truth(output: Path) -> None:
        """
        Executes the _write_ground_truth workflow for automated regression tests.
        
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

        reports = output / "automation"
        reports.mkdir(parents=True)
        AIEvaluationFrameworkTests._write_csv(
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
                    "Issue": "scale_mismatch",
                    "Severity": "HIGH",
                    "Recommendation": "Retain original precision and scale.",
                    "Auto Fixed": "True",
                    "Fix Applied": "copy_source_scale",
                    "Before Value": "DECIMAL(15,0)",
                    "After Value": "DECIMAL(15,2)",
                    "Status": "Resolved",
                    "Asset": "M_SAMPLE",
                    "Manual Remediation Required": "False",
                    "Approval Required": "False",
                },
                {
                    "Issue": "mapplet_nesting",
                    "Severity": "MEDIUM",
                    "Recommendation": "Manually review nested mapplets.",
                    "Auto Fixed": "False",
                    "Fix Applied": "",
                    "Before Value": "M_SAMPLE",
                    "After Value": "M_SAMPLE",
                    "Status": "Manual Remediation Required",
                    "Asset": "M_SAMPLE",
                    "Manual Remediation Required": "True",
                    "Approval Required": "False",
                },
            ],
        )
        AIEvaluationFrameworkTests._write_csv(
            output / "post_remediation_migration_readiness_report.csv",
            ["mapping_name", "readiness_category"],
            [{"mapping_name": "M_SAMPLE", "readiness_category": "LOW RISK"}],
        )
        AIEvaluationFrameworkTests._write_csv(
            output / "risk_assessment_report.csv",
            ["mapping_name", "risk_level"],
            [{"mapping_name": "M_SAMPLE", "risk_level": "LOW"}],
        )
        AIEvaluationFrameworkTests._write_csv(
            reports / "dashboard_dataset.csv",
            ["workflow", "mapping_name", "failures"],
            [{"workflow": "WF", "mapping_name": "M_SAMPLE", "failures": "1"}],
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

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        """
        Executes the _read_csv workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        with path.open("r", newline="", encoding="utf-8") as csv_file:
            return list(csv.DictReader(csv_file))


if __name__ == "__main__":
    unittest.main()


