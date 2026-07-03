from __future__ import annotations

import json
from dataclasses import asdict

from automation.ai.recommendation_models import FailureRecord


class RecommendationPromptBuilder:
    """Builds strict JSON prompts for migration recommendation generation."""

    REQUIRED_KEYS = ["root_cause", "recommendation", "priority", "summary", "confidence"]

    def build(self, failure: FailureRecord) -> str:
        payload = asdict(failure)
        return (
            "Analyze this unresolved PowerCenter to Informatica Cloud migration validation failure. "
            "Return STRICT JSON only with keys: root_cause, recommendation, priority, summary, confidence. "
            "priority must be one of Critical, High, Medium, Low. confidence must be 0-100. "
            "Do not modify XML. Do not generate auto-fix code. Provide concise, actionable IDMC migration guidance.\n\n"
            f"Failure record:\n{json.dumps(payload, indent=2, sort_keys=True)}"
        )
