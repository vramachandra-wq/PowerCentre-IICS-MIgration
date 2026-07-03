from __future__ import annotations

import json
import re
from typing import Any

from automation.metrics import MetricsCalculator
from automation.ai.recommendation_models import Recommendation


class RecommendationResponseParser:
    """Parses and validates strict JSON recommendation responses."""

    VALID_PRIORITIES = {"Critical", "High", "Medium", "Low"}

    @classmethod
    def parse(cls, content: str | dict[str, Any]) -> Recommendation:
        payload = cls._payload(content)
        missing = [key for key in ["root_cause", "recommendation", "priority", "summary"] if key not in payload]
        if missing:
            raise ValueError(f"AI recommendation JSON missing required field(s): {', '.join(missing)}")
        priority = cls._normalize_priority(str(payload.get("priority", "")))
        confidence = max(0, min(MetricsCalculator.to_int(payload.get("confidence", 0)), 100))
        return Recommendation(
            root_cause=str(payload.get("root_cause", "") or "").strip(),
            recommendation=str(payload.get("recommendation", "") or "").strip(),
            priority=priority,
            summary=str(payload.get("summary", "") or "").strip(),
            confidence=confidence,
        )

    @staticmethod
    def _payload(content: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(content, dict):
            return content
        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content or "", flags=re.IGNORECASE).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if not match:
                raise ValueError(f"Invalid AI recommendation JSON response: {cleaned[:300]}")
            payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("AI recommendation response must be a JSON object")
        return payload

    @classmethod
    def _normalize_priority(cls, value: str) -> str:
        priority = value.strip().capitalize()
        if priority not in cls.VALID_PRIORITIES:
            raise ValueError(f"Invalid AI recommendation priority: {value}")
        return priority
