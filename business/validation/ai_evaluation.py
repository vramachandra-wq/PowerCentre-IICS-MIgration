from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from automation.evaluation_matrix import ReportRepository
from business.validation.ai_metrics import AIMetricsCalculator
from business.validation.ai_validation_engine import AIValidationResult


@dataclass(frozen=True)
class AIEvaluationSummary:
    total_evaluations: int
    ml_accuracy: float
    ml_precision: float
    recall: float
    f1_score: float
    average_confidence: float
    model_success_rate: float


class AIEvaluationBuilder:
    """Converts model validation results into executive evaluation artifacts."""

    DATASET_FIELDNAMES = [
        "mapping_name",
        "rule_name",
        "ground_truth",
        "ml_decision",
        "confidence",
        "correct",
    ]
    MATRIX_FIELDNAMES = [
        "ML Accuracy",
        "ML Precision",
        "Recall",
        "F1 Score",
        "Average Confidence",
        "Model Success Rate",
        "Total Evaluations",
    ]
    DASHBOARD_FIELDNAMES = MATRIX_FIELDNAMES

    def __init__(self, repository: ReportRepository | None = None, high_confidence_threshold: int = 90) -> None:
        self.repository = repository or ReportRepository()
        self.high_confidence_threshold = high_confidence_threshold

    def build_dataset(self, results: Iterable[AIValidationResult]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for result in results:
            ground_truth = AIMetricsCalculator.normalize_decision(result.input.ground_truth)
            ml_decision = AIMetricsCalculator.normalize_decision(result.prediction.decision)
            rows.append(
                {
                    "mapping_name": result.input.mapping_name,
                    "rule_name": result.input.rule_name,
                    "ground_truth": ground_truth,
                    "ml_decision": ml_decision,
                    "confidence": result.prediction.confidence,
                    "correct": str(ground_truth == ml_decision),
                }
            )
        return rows

    def summarize(self, results: list[AIValidationResult], dataset: list[dict[str, Any]]) -> AIEvaluationSummary:
        valid_rows = [row for row in dataset if row["ml_decision"] in {"PASS", "FAIL"}]
        matrix = AIMetricsCalculator.confusion_counts(
            (row["ground_truth"], row["ml_decision"]) for row in valid_rows
        )
        precision = AIMetricsCalculator.precision(matrix)
        recall = AIMetricsCalculator.recall(matrix)
        return AIEvaluationSummary(
            total_evaluations=len(dataset),
            ml_accuracy=AIMetricsCalculator.accuracy(matrix),
            ml_precision=precision,
            recall=recall,
            f1_score=AIMetricsCalculator.f1_score(precision, recall),
            average_confidence=AIMetricsCalculator.average_confidence(row["confidence"] for row in dataset),
            model_success_rate=AIMetricsCalculator.agreement_rate(len(valid_rows), len(dataset)),
        )

    def write(self, dataset: list[dict[str, Any]], summary: AIEvaluationSummary) -> dict[str, Path]:
        matrix_row = self._matrix_row(summary)
        outputs = {
            "dataset": self.repository.write_csv("ai_evaluation_dataset.csv", dataset, self.DATASET_FIELDNAMES),
            "matrix": self.repository.write_csv("ai_evaluation_matrix.csv", [matrix_row], self.MATRIX_FIELDNAMES),
            "dashboard": self.repository.write_csv("ai_dashboard_dataset.csv", [matrix_row], self.DASHBOARD_FIELDNAMES),
            "json": self.repository.write_json(
                "ai_evaluation_summary.json",
                {"matrix": matrix_row, "dashboard": matrix_row},
            ),
        }
        extended_dashboard = self._extended_dashboard_rows(matrix_row)
        if extended_dashboard:
            base_fields = list(extended_dashboard[0].keys())
            outputs["extended_dashboard"] = self.repository.write_csv(
                "dashboard_dataset.csv", extended_dashboard, base_fields
            )
        return outputs

    def _extended_dashboard_rows(self, dashboard_row: dict[str, Any]) -> list[dict[str, Any]]:
        rows = self.repository.read_csv("automation/dashboard_dataset.csv")
        if not rows:
            return []
        extended: list[dict[str, Any]] = []
        for row in rows:
            merged = dict(row)
            merged.update(dashboard_row)
            extended.append(merged)
        return extended

    @staticmethod
    def _matrix_row(summary: AIEvaluationSummary) -> dict[str, Any]:
        return {
            "ML Accuracy": summary.ml_accuracy,
            "ML Precision": summary.ml_precision,
            "Recall": summary.recall,
            "F1 Score": summary.f1_score,
            "Average Confidence": summary.average_confidence,
            "Model Success Rate": summary.model_success_rate,
            "Total Evaluations": summary.total_evaluations,
        }
