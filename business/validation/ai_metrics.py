from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from automation.metrics import MetricsCalculator


@dataclass(frozen=True)
class BinaryConfusionMatrix:
    """Confusion matrix for PASS/FAIL AI decisions against rule-engine ground truth."""

    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def total(self) -> int:
        return self.tp + self.tn + self.fp + self.fn

    @property
    def correct(self) -> int:
        return self.tp + self.tn

    @property
    def incorrect(self) -> int:
        return self.fp + self.fn


class AIMetricsCalculator:
    """Reusable AI evaluation metric calculations."""

    @staticmethod
    def confusion_counts(pairs: Iterable[tuple[str, str]]) -> BinaryConfusionMatrix:
        tp = tn = fp = fn = 0
        for ground_truth, ai_decision in pairs:
            expected = AIMetricsCalculator.normalize_decision(ground_truth)
            predicted = AIMetricsCalculator.normalize_decision(ai_decision)
            if expected == "PASS" and predicted == "PASS":
                tp += 1
            elif expected == "FAIL" and predicted == "FAIL":
                tn += 1
            elif expected == "FAIL" and predicted == "PASS":
                fp += 1
            elif expected == "PASS" and predicted == "FAIL":
                fn += 1
        return BinaryConfusionMatrix(tp=tp, tn=tn, fp=fp, fn=fn)

    @staticmethod
    def accuracy(matrix: BinaryConfusionMatrix) -> float:
        return MetricsCalculator.percentage(matrix.correct, matrix.total)

    @staticmethod
    def precision(matrix: BinaryConfusionMatrix) -> float:
        return MetricsCalculator.percentage(matrix.tp, matrix.tp + matrix.fp)

    @staticmethod
    def recall(matrix: BinaryConfusionMatrix) -> float:
        return MetricsCalculator.percentage(matrix.tp, matrix.tp + matrix.fn)

    @staticmethod
    def f1_score(precision: float, recall: float) -> float:
        if precision + recall == 0:
            return 0.0
        return round((2 * precision * recall) / (precision + recall), 2)

    @staticmethod
    def false_positive_rate(matrix: BinaryConfusionMatrix) -> float:
        return MetricsCalculator.percentage(matrix.fp, matrix.fp + matrix.tn)

    @staticmethod
    def false_negative_rate(matrix: BinaryConfusionMatrix) -> float:
        return MetricsCalculator.percentage(matrix.fn, matrix.fn + matrix.tp)

    @staticmethod
    def agreement_rate(matches: int, total: int) -> float:
        return MetricsCalculator.percentage(matches, total)

    @staticmethod
    def average_confidence(values: Iterable[int | float]) -> float:
        return MetricsCalculator.average(values)

    @staticmethod
    def classification_accuracy(expected_actual: Iterable[tuple[str, str]]) -> float:
        pairs = list(expected_actual)
        if not pairs:
            return 0.0
        matches = sum(
            1
            for expected, actual in pairs
            if AIMetricsCalculator.normalize_label(expected) == AIMetricsCalculator.normalize_label(actual)
        )
        return MetricsCalculator.percentage(matches, len(pairs))

    @staticmethod
    def normalize_decision(value: object) -> str:
        normalized = str(value or "").strip().upper()
        if normalized in {"PASS", "PASSED", "READY", "RESOLVED", "TRUE", "YES"}:
            return "PASS"
        if normalized in {"FAIL", "FAILED", "NOT_READY", "NOT READY", "OPEN", "FALSE", "NO"}:
            return "FAIL"
        return normalized or "UNKNOWN"

    @staticmethod
    def normalize_label(value: object) -> str:
        return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
