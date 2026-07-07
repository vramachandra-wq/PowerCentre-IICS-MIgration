"""
Support metrics for automation data and validation workflows.
Prepares metrics, findings, and AI assistance outputs.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Mapping


class MetricsCalculator:
    """Encapsulates metrics calculator behavior for migration workflows."""

    @staticmethod
    def percentage(numerator: int | float, denominator: int | float) -> float:
        """Handle percentage using the provided numerator and denominator."""

        if not denominator:
            return 0.0
        value = (float(numerator) / float(denominator)) * 100
        return round(max(0.0, min(value, 100.0)), 2)

    @staticmethod
    def average(values: Iterable[int | float]) -> float:
        """Handle average using the provided values."""

        numbers = [float(value) for value in values]
        if not numbers:
            return 0.0
        return round(sum(numbers) / len(numbers), 2)

    @staticmethod
    def pass_rate(passed: int, failed: int) -> float:
        """Handle pass rate using the provided passed and failed."""

        return MetricsCalculator.percentage(passed, passed + failed)

    @staticmethod
    def failure_rate(passed: int, failed: int) -> float:
        """Handle failure rate using the provided passed and failed."""

        return MetricsCalculator.percentage(failed, passed + failed)

    @staticmethod
    def readiness_improvement(readiness_before: int | float, readiness_after: int | float) -> float:
        """Handle readiness improvement using the provided readiness_before and readiness_after."""

        return round(float(readiness_after) - float(readiness_before), 2)

    @staticmethod
    def risk_reduction(risk_before: int | float, risk_after: int | float) -> float:
        """Handle risk reduction using the provided risk_before and risk_after."""

        return round(float(risk_before) - float(risk_after), 2)

    @staticmethod
    def distribution(values: Iterable[str]) -> dict[str, int]:
        """Handle distribution using the provided values."""

        return dict(Counter(value or "UNKNOWN" for value in values))

    @staticmethod
    def validation_coverage(rules_executed: int, mapping_count: int) -> float:
        """Handle validation coverage using the provided rules_executed and mapping_count."""

        return MetricsCalculator.percentage(rules_executed, mapping_count) if mapping_count else 0.0

    @staticmethod
    def most_common(values: Iterable[str]) -> str:
        """Handle most common using the provided values."""

        counter = Counter(value for value in values if value)
        if not counter:
            return "none"
        return counter.most_common(1)[0][0]

    @staticmethod
    def sum_field(rows: Iterable[Mapping[str, object]], field: str) -> int:
        """Handle sum field using the provided rows and field."""

        return sum(MetricsCalculator.to_int(row.get(field, 0)) for row in rows)

    @staticmethod
    def to_int(value: object) -> int:
        """Handle to int using the provided value."""

        try:
            return int(float(str(value or "0").strip()))
        except ValueError:
            return 0

    @staticmethod
    def to_float(value: object) -> float:
        """Handle to float using the provided value."""

        try:
            return float(str(value or "0").strip())
        except ValueError:
            return 0.0

    @staticmethod
    def normalize_text(value: object) -> str:
        """Normalize text using the provided value."""

        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
