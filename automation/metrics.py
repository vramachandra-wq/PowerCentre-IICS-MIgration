from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Mapping


class MetricsCalculator:
    """Reusable calculations for automation-level validation metrics."""

    @staticmethod
    def percentage(numerator: int | float, denominator: int | float) -> float:
        if not denominator:
            return 0.0
        return round((float(numerator) / float(denominator)) * 100, 2)

    @staticmethod
    def average(values: Iterable[int | float]) -> float:
        numbers = [float(value) for value in values]
        if not numbers:
            return 0.0
        return round(sum(numbers) / len(numbers), 2)

    @staticmethod
    def pass_rate(passed: int, failed: int) -> float:
        return MetricsCalculator.percentage(passed, passed + failed)

    @staticmethod
    def failure_rate(passed: int, failed: int) -> float:
        return MetricsCalculator.percentage(failed, passed + failed)

    @staticmethod
    def readiness_improvement(readiness_before: int | float, readiness_after: int | float) -> float:
        return round(float(readiness_after) - float(readiness_before), 2)

    @staticmethod
    def risk_reduction(risk_before: int | float, risk_after: int | float) -> float:
        return round(float(risk_before) - float(risk_after), 2)

    @staticmethod
    def distribution(values: Iterable[str]) -> dict[str, int]:
        return dict(Counter(value or "UNKNOWN" for value in values))

    @staticmethod
    def validation_coverage(rules_executed: int, mapping_count: int) -> float:
        return MetricsCalculator.percentage(rules_executed, mapping_count) if mapping_count else 0.0

    @staticmethod
    def most_common(values: Iterable[str]) -> str:
        counter = Counter(value for value in values if value)
        if not counter:
            return "none"
        return counter.most_common(1)[0][0]

    @staticmethod
    def sum_field(rows: Iterable[Mapping[str, object]], field: str) -> int:
        return sum(MetricsCalculator.to_int(row.get(field, 0)) for row in rows)

    @staticmethod
    def to_int(value: object) -> int:
        try:
            return int(float(str(value or "0").strip()))
        except ValueError:
            return 0

    @staticmethod
    def to_float(value: object) -> float:
        try:
            return float(str(value or "0").strip())
        except ValueError:
            return 0.0

    @staticmethod
    def normalize_text(value: object) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
