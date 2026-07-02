from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from automation.evaluation_matrix import ReportRepository
from automation.metrics import MetricsCalculator
from business.validation.ai_metrics import AIMetricsCalculator
from business.validation.ai_validation_engine import AIValidationResult


@dataclass(frozen=True)
class AIEvaluationSummary:
    total_rules: int
    correct: int
    incorrect: int
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    false_positive_rate: float
    false_negative_rate: float
    agreement_rate: float
    average_confidence: float
    recommendation_accuracy: float
    readiness_accuracy: float
    risk_accuracy: float
    average_processing_time_ms: float
    min_processing_time_ms: int
    max_processing_time_ms: int
    total_processing_time_ms: int
    valid_predictions: int
    model_errors: int
    model_call_success_rate: float
    valid_prediction_accuracy: float
    high_confidence_errors: int
    false_positives: int
    false_negatives: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AIEvaluationBuilder:
    """Converts AI validation results into dataset, matrix, and dashboard artifacts."""

    DATASET_FIELDNAMES = [
        "mapping_name",
        "rule_name",
        "ground_truth",
        "ai_decision",
        "confidence",
        "correct",
        "tp",
        "tn",
        "fp",
        "fn",
        "recommendation",
        "processing_time_ms",
        "risk_prediction",
        "readiness_prediction",
        "reason",
        "error",
    ]
    MATRIX_FIELDNAMES = [
        "Total Rules",
        "Correct",
        "Incorrect",
        "Accuracy",
        "Precision",
        "Recall",
        "F1 Score",
        "False Positive Rate",
        "False Negative Rate",
        "Agreement Rate",
        "Average Confidence",
        "Recommendation Accuracy",
        "Readiness Accuracy",
        "Risk Accuracy",
        "Average Processing Time",
        "Minimum Processing Time",
        "Maximum Processing Time",
        "Total Processing Time",
        "Prompt Tokens",
        "Completion Tokens",
        "Total Tokens",
        "Valid Predictions",
        "Model Errors",
        "Model Call Success Rate",
        "Valid Prediction Accuracy",
    ]
    DASHBOARD_FIELDNAMES = [
        "AI Accuracy",
        "AI Precision",
        "AI Recall",
        "AI F1",
        "Agreement Rate",
        "Average Confidence",
        "Average Processing Time",
        "High Confidence Errors",
        "False Positives",
        "False Negatives",
        "Model Errors",
        "Model Call Success Rate",
        "Valid Prediction Accuracy",
    ]

    def __init__(self, repository: ReportRepository | None = None, high_confidence_threshold: int = 90) -> None:
        self.repository = repository or ReportRepository()
        self.high_confidence_threshold = high_confidence_threshold

    def build_dataset(self, results: Iterable[AIValidationResult]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for result in results:
            ground_truth = AIMetricsCalculator.normalize_decision(result.input.ground_truth)
            ai_decision = AIMetricsCalculator.normalize_decision(result.prediction.decision)
            tp = int(ground_truth == "PASS" and ai_decision == "PASS")
            tn = int(ground_truth == "FAIL" and ai_decision == "FAIL")
            fp = int(ground_truth == "FAIL" and ai_decision == "PASS")
            fn = int(ground_truth == "PASS" and ai_decision == "FAIL")
            rows.append(
                {
                    "mapping_name": result.input.mapping_name,
                    "rule_name": result.input.rule_name,
                    "ground_truth": ground_truth,
                    "ai_decision": ai_decision,
                    "confidence": result.prediction.confidence,
                    "correct": str(ground_truth == ai_decision),
                    "tp": tp,
                    "tn": tn,
                    "fp": fp,
                    "fn": fn,
                    "recommendation": result.prediction.recommendation,
                    "processing_time_ms": result.processing_time_ms,
                    "risk_prediction": result.prediction.risk_prediction,
                    "readiness_prediction": result.prediction.readiness_prediction,
                    "reason": result.prediction.reason,
                    "error": result.prediction.error,
                }
            )
        return rows

    def summarize(self, results: list[AIValidationResult], dataset: list[dict[str, Any]]) -> AIEvaluationSummary:
        valid_rows = [row for row in dataset if row["ai_decision"] in {"PASS", "FAIL"}]
        model_errors = len(dataset) - len(valid_rows)
        matrix = AIMetricsCalculator.confusion_counts(
            (row["ground_truth"], row["ai_decision"]) for row in valid_rows
        )
        precision = AIMetricsCalculator.precision(matrix)
        recall = AIMetricsCalculator.recall(matrix)
        processing_times = [result.processing_time_ms for result in results]
        correct_recommendations = sum(
            1
            for result in results
            if result.input.expected_recommendation
            and self._recommendation_matches(result.input.expected_recommendation, result.prediction.recommendation)
        )
        recommendation_denominator = sum(1 for result in results if result.input.expected_recommendation)
        readiness_pairs = [
            (result.input.expected_readiness, result.prediction.readiness_prediction)
            for result in results
            if result.input.expected_readiness and result.prediction.readiness_prediction
        ]
        risk_pairs = [
            (result.input.expected_risk, result.prediction.risk_prediction)
            for result in results
            if result.input.expected_risk and result.prediction.risk_prediction
        ]
        high_confidence_errors = sum(
            1
            for row in dataset
            if row["correct"] == "False" and MetricsCalculator.to_int(row["confidence"]) >= self.high_confidence_threshold
        )
        total_rules = len(dataset)
        correct = sum(1 for row in dataset if row["correct"] == "True")
        incorrect = total_rules - correct
        return AIEvaluationSummary(
            total_rules=total_rules,
            correct=correct,
            incorrect=incorrect,
            accuracy=MetricsCalculator.percentage(correct, total_rules),
            precision=precision,
            recall=recall,
            f1_score=AIMetricsCalculator.f1_score(precision, recall),
            false_positive_rate=AIMetricsCalculator.false_positive_rate(matrix),
            false_negative_rate=AIMetricsCalculator.false_negative_rate(matrix),
            agreement_rate=AIMetricsCalculator.agreement_rate(matrix.correct, matrix.total),
            average_confidence=AIMetricsCalculator.average_confidence(row["confidence"] for row in dataset),
            recommendation_accuracy=MetricsCalculator.percentage(correct_recommendations, recommendation_denominator),
            readiness_accuracy=AIMetricsCalculator.classification_accuracy(readiness_pairs),
            risk_accuracy=AIMetricsCalculator.classification_accuracy(risk_pairs),
            average_processing_time_ms=MetricsCalculator.average(processing_times),
            min_processing_time_ms=min(processing_times) if processing_times else 0,
            max_processing_time_ms=max(processing_times) if processing_times else 0,
            total_processing_time_ms=sum(processing_times),
            valid_predictions=len(valid_rows),
            model_errors=model_errors,
            model_call_success_rate=MetricsCalculator.percentage(len(valid_rows), total_rules),
            valid_prediction_accuracy=AIMetricsCalculator.accuracy(matrix),
            high_confidence_errors=high_confidence_errors,
            false_positives=matrix.fp,
            false_negatives=matrix.fn,
            prompt_tokens=sum(result.prediction.prompt_tokens for result in results),
            completion_tokens=sum(result.prediction.completion_tokens for result in results),
            total_tokens=sum(result.prediction.total_tokens for result in results),
        )

    def write(self, dataset: list[dict[str, Any]], summary: AIEvaluationSummary) -> dict[str, Path]:
        matrix_row = self._matrix_row(summary)
        dashboard_row = self._dashboard_row(summary)
        outputs = {
            "dataset": self.repository.write_csv("ai_evaluation_dataset.csv", dataset, self.DATASET_FIELDNAMES),
            "matrix": self.repository.write_csv("ai_evaluation_matrix.csv", [matrix_row], self.MATRIX_FIELDNAMES),
            "dashboard": self.repository.write_csv("ai_dashboard_dataset.csv", [dashboard_row], self.DASHBOARD_FIELDNAMES),
            "json": self.repository.write_json(
                "ai_evaluation_summary.json",
                {"matrix": matrix_row, "dashboard": dashboard_row},
            ),
        }
        extended_dashboard = self._extended_dashboard_rows(dashboard_row)
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
    def _recommendation_matches(expected: str, actual: str) -> bool:
        expected_tokens = set(AIMetricsCalculator.normalize_label(expected).split("_"))
        actual_tokens = set(AIMetricsCalculator.normalize_label(actual).split("_"))
        if not expected_tokens or not actual_tokens:
            return False
        return bool(expected_tokens & actual_tokens)

    @staticmethod
    def _matrix_row(summary: AIEvaluationSummary) -> dict[str, Any]:
        return {
            "Total Rules": summary.total_rules,
            "Correct": summary.correct,
            "Incorrect": summary.incorrect,
            "Accuracy": summary.accuracy,
            "Precision": summary.precision,
            "Recall": summary.recall,
            "F1 Score": summary.f1_score,
            "False Positive Rate": summary.false_positive_rate,
            "False Negative Rate": summary.false_negative_rate,
            "Agreement Rate": summary.agreement_rate,
            "Average Confidence": summary.average_confidence,
            "Recommendation Accuracy": summary.recommendation_accuracy,
            "Readiness Accuracy": summary.readiness_accuracy,
            "Risk Accuracy": summary.risk_accuracy,
            "Average Processing Time": summary.average_processing_time_ms,
            "Minimum Processing Time": summary.min_processing_time_ms,
            "Maximum Processing Time": summary.max_processing_time_ms,
            "Total Processing Time": summary.total_processing_time_ms,
            "Prompt Tokens": summary.prompt_tokens,
            "Completion Tokens": summary.completion_tokens,
            "Total Tokens": summary.total_tokens,
            "Valid Predictions": summary.valid_predictions,
            "Model Errors": summary.model_errors,
            "Model Call Success Rate": summary.model_call_success_rate,
            "Valid Prediction Accuracy": summary.valid_prediction_accuracy,
        }

    @staticmethod
    def _dashboard_row(summary: AIEvaluationSummary) -> dict[str, Any]:
        return {
            "AI Accuracy": summary.accuracy,
            "AI Precision": summary.precision,
            "AI Recall": summary.recall,
            "AI F1": summary.f1_score,
            "Agreement Rate": summary.agreement_rate,
            "Average Confidence": summary.average_confidence,
            "Average Processing Time": summary.average_processing_time_ms,
            "High Confidence Errors": summary.high_confidence_errors,
            "False Positives": summary.false_positives,
            "False Negatives": summary.false_negatives,
            "Model Errors": summary.model_errors,
            "Model Call Success Rate": summary.model_call_success_rate,
            "Valid Prediction Accuracy": summary.valid_prediction_accuracy,
        }
