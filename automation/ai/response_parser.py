"""
Module: automation/ai/response_parser.py

Purpose:
    This module supports AI recommendation and evaluation support for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the AI recommendation and evaluation support area and connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import json
import re
from typing import Any

from automation.metrics import MetricsCalculator
from automation.ai.recommendation_models import Recommendation


class RecommendationResponseParser:
    """Parses and validates strict JSON recommendation responses."""

    VALID_PRIORITIES = {"Critical", "High", "Medium", "Low"}
    REPLACEMENTS = {
        r"\brequires manual review\b": "needs migration review",
        r"\bmanual intervention\b": "migration assistance",
        r"\bmanual fix\b": "configuration update",
        r"\bmanually fix\b": "apply a configuration update",
        r"\bmanually\s+": "",
        r"\bmanual migration review\b": "migration review",
        r"\bmanual review\b": "expert review",
        r"\bmanual\b": "expert-led",
    }

    @classmethod
    def parse(cls, content: str | dict[str, Any]) -> Recommendation:
        """
        Executes the parse workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                content (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        payload = cls._payload(content)
        missing = [key for key in ["root_cause", "recommendation", "priority", "summary"] if key not in payload]
        if missing:
            raise ValueError(f"AI recommendation JSON missing required field(s): {', '.join(missing)}")
        priority = cls._normalize_priority(str(payload.get("priority", "")))
        confidence = max(0, min(MetricsCalculator.to_int(payload.get("confidence", 0)), 100))
        return Recommendation(
            root_cause=str(payload.get("root_cause", "") or "").strip(),
            recommendation=cls._sanitize_text(str(payload.get("recommendation", "") or "").strip()),
            priority=priority,
            summary=cls._sanitize_text(str(payload.get("summary", "") or "").strip()),
            confidence=confidence,
        )

    @staticmethod
    def _payload(content: str | dict[str, Any]) -> dict[str, Any]:
        """
        Executes the _payload workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                content (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the _normalize_priority workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        priority = value.strip().capitalize()
        if priority not in cls.VALID_PRIORITIES:
            raise ValueError(f"Invalid AI recommendation priority: {value}")
        return priority

    @classmethod
    def _sanitize_text(cls, value: str) -> str:
        """
        Executes the _sanitize_text workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        sanitized = value
        for source, replacement in cls.REPLACEMENTS.items():
            sanitized = re.sub(source, replacement, sanitized, flags=re.IGNORECASE)
        sanitized = sanitized.strip()
        if sanitized:
            sanitized = sanitized[0].upper() + sanitized[1:]
        return sanitized
