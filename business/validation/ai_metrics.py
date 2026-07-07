"""
Support ai metrics for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from automation.metrics import MetricsCalculator


@dataclass(frozen=True)
class BinaryConfusionMatrix:
    """Encapsulates binary confusion matrix behavior for migration workflows."""

    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def total(self) -> int:
        """Handle total for the migration workflow."""

        return self.tp + self.tn + self.fp + self.fn

    @property
    def correct(self) -> int:
        """Handle correct for the migration workflow."""

        return self.tp + self.tn


class AIMetricsCalculator:
    """Encapsulates aimetrics calculator behavior for migration workflows."""

    @staticmethod
    def confusion_counts(pairs: Iterable[tuple[str, str]]) -> BinaryConfusionMatrix:
        """Handle confusion counts using the provided pairs."""

        tp = tn = fp = fn = 0
        for ground_truth, predicted_decision in pairs:
            expected = AIMetricsCalculator.normalize_decision(ground_truth)
            predicted = AIMetricsCalculator.normalize_decision(predicted_decision)
            if expected == "FAIL" and predicted == "FAIL":
                tp += 1
            elif expected == "PASS" and predicted == "PASS":
                tn += 1
            elif expected == "PASS" and predicted == "FAIL":
                fp += 1
            elif expected == "FAIL" and predicted == "PASS":
                fn += 1
        return BinaryConfusionMatrix(tp=tp, tn=tn, fp=fp, fn=fn)

    @staticmethod
    def precision(matrix: BinaryConfusionMatrix) -> float:
        """Handle precision using the provided matrix."""

        return MetricsCalculator.percentage(matrix.tp, matrix.tp + matrix.fp)

    @staticmethod
    def recall(matrix: BinaryConfusionMatrix) -> float:
        """Handle recall using the provided matrix."""

        return MetricsCalculator.percentage(matrix.tp, matrix.tp + matrix.fn)

    @staticmethod
    def f1_score(precision: float, recall: float) -> float:
        """Handle f1 score using the provided precision and recall."""

        if precision + recall == 0:
            return 0.0
        return round((2 * precision * recall) / (precision + recall), 2)

    @staticmethod
    def average_confidence(values: Iterable[int | float]) -> float:
        """Handle average confidence using the provided values."""

        return MetricsCalculator.average(values)

    @staticmethod
    def normalize_decision(value: object) -> str:
        """Normalize decision using the provided value."""

        normalized = str(value or "").strip().upper()
        if normalized in {"PASS", "PASSED", "READY", "RESOLVED", "TRUE", "YES"}:
            return "PASS"
        if normalized in {"FAIL", "FAILED", "NOT_READY", "NOT READY", "OPEN", "FALSE", "NO"}:
            return "FAIL"
        return normalized or "UNKNOWN"
