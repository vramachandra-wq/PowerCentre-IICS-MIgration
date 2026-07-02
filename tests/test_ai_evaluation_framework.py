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
    def validate(self, payload: dict[str, object]) -> dict[str, object]:
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
    def test_binary_metrics(self) -> None:
        matrix = BinaryConfusionMatrix(tp=8, tn=7, fp=2, fn=3)
        self.assertEqual(75.0, AIMetricsCalculator.accuracy(matrix))
        self.assertEqual(80.0, AIMetricsCalculator.precision(matrix))
        self.assertEqual(72.73, AIMetricsCalculator.recall(matrix))
        self.assertEqual(76.19, AIMetricsCalculator.f1_score(80.0, 72.73))
        self.assertEqual(22.22, AIMetricsCalculator.false_positive_rate(matrix))
        self.assertEqual(27.27, AIMetricsCalculator.false_negative_rate(matrix))

    def test_agreement_confidence_and_json_parsing(self) -> None:
        self.assertEqual(66.67, AIMetricsCalculator.agreement_rate(2, 3))
        self.assertEqual(90.0, AIMetricsCalculator.average_confidence([80, 90, 100]))
        parsed = AIResponseParser.parse('{"decision":"PASS","confidence":99}')
        self.assertEqual("PASS", parsed["decision"])
        with self.assertRaises(ValueError):
            AIResponseParser.parse("not json")


class AIEvaluationFrameworkTests(unittest.TestCase):
    def test_ai_dataset_matrix_and_dashboard_generation(self) -> None:
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
            self.assertEqual(100.0, summary.accuracy)
            self.assertEqual(100.0, summary.agreement_rate)
            self.assertEqual(100.0, summary.recommendation_accuracy)
            self.assertEqual(100.0, summary.readiness_accuracy)
            self.assertEqual(100.0, summary.risk_accuracy)
            self.assertTrue(paths["dataset"].exists())
            self.assertTrue(paths["matrix"].exists())
            self.assertTrue(paths["dashboard"].exists())
            self.assertTrue(paths["extended_dashboard"].exists())

            matrix = self._read_csv(paths["matrix"])[0]
            self.assertEqual("2", matrix["Total Rules"])
            self.assertEqual("100.0", matrix["Accuracy"])
            dashboard = self._read_csv(paths["extended_dashboard"])[0]
            self.assertIn("AI Accuracy", dashboard)

    @staticmethod
    def _write_ground_truth(output: Path) -> None:
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
