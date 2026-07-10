"""
Support ai evaluation for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from automation.evaluation_matrix import ReportRepository
from business.validation.ai_metrics import AIMetricsCalculator
from business.validation.ai_validation_engine import AIValidationResult
from automation.metrics import MetricsCalculator
 


@dataclass(frozen=True)
class AIEvaluationSummary:
    """Stores summarized validation and migration output."""

    total_evaluations: int
    ml_accuracy: float
    ml_precision: float
    recall: float
    f1_score: float
    average_confidence: float
    model_success_rate: float
    total_processing_time_seconds: float
    configured_max_records: int = 0


class AIEvaluationBuilder:
    """Encapsulates aievaluation builder behavior for migration workflows."""

    DATASET_FIELDNAMES = [
        "mapping_name",
        "rule_name",
        "ground_truth",
        "ml_decision",
        "confidence",
        "correct",
        "processing_time_ms",
    ]
    MATRIX_FIELDNAMES = [
        "Total Evaluations",
        "ML Accuracy",
        "ML Precision",
        "Recall",
        "F1 Score",
        "Average Confidence",
        "Model Success Rate",
        "AI Evaluation Time (sec)",
        "Configured Max Records",
    ]
    DASHBOARD_FIELDNAMES = MATRIX_FIELDNAMES

    def __init__(self, repository: ReportRepository | None = None, high_confidence_threshold: int = 90) -> None:
        """Initialize migration data using the provided repository and high_confidence_threshold."""

        self.repository = repository or ReportRepository()
        self.high_confidence_threshold = high_confidence_threshold

    def build_dataset(self, results: Iterable[AIValidationResult]) -> list[dict[str, Any]]:
        """Build dataset using the provided results."""

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
                    "processing_time_ms": result.processing_time_ms,
                }
            )
        return rows

    def summarize(
        self,
        results: list[AIValidationResult],
        dataset: list[dict[str, Any]],
        total_processing_time_ms: int = 0,
        configured_max_records: int = 0,
    ) -> AIEvaluationSummary:
        """Summarize migration data using the provided results and dataset."""

        valid_rows = [row for row in dataset if row["ml_decision"] in {"PASS", "FAIL"}]
        matrix = AIMetricsCalculator.confusion_counts(
            (row["ground_truth"], row["ml_decision"]) for row in valid_rows
        )
        total_evaluations = len(dataset)
        valid_evaluations = len(valid_rows)
        correct = sum(1 for row in valid_rows if row["correct"] == "True")
        ml_precision = AIMetricsCalculator.precision(matrix)
        recall = AIMetricsCalculator.recall(matrix)
        return AIEvaluationSummary(
            total_evaluations=total_evaluations,
            ml_accuracy=MetricsCalculator.percentage(correct, valid_evaluations),
            ml_precision=ml_precision,
            recall=recall,
            f1_score=AIMetricsCalculator.f1_score(ml_precision, recall),
            average_confidence=AIMetricsCalculator.average_confidence(row["confidence"] for row in valid_rows),
            model_success_rate=MetricsCalculator.percentage(valid_evaluations, total_evaluations),
            total_processing_time_seconds=round(total_processing_time_ms / 1000, 2),
            configured_max_records=configured_max_records,
        )

    def write(self, dataset: list[dict[str, Any]], summary: AIEvaluationSummary) -> dict[str, Path]:
        """Handle write using the provided dataset and summary."""

        matrix_row = self._summary_row(summary)
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
        """Handle extended dashboard rows using the provided dashboard_row."""

        rows = self.repository.read_csv("automation/dashboard_dataset.csv")
        if not rows:
            return []
        return [{**row, **dashboard_row} for row in rows]

    @staticmethod
    def _summary_row(summary: AIEvaluationSummary) -> dict[str, Any]:
        """Handle summary row using the provided summary."""

        return {
            "Total Evaluations": summary.total_evaluations,
            "ML Accuracy": summary.ml_accuracy,
            "ML Precision": summary.ml_precision,
            "Recall": summary.recall,
            "F1 Score": summary.f1_score,
            "Average Confidence": summary.average_confidence,
            "Model Success Rate": summary.model_success_rate,
            "AI Evaluation Time (sec)": summary.total_processing_time_seconds,
            "Configured Max Records": summary.configured_max_records,
        }
