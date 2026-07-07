"""
Module: automation/ai/recommendation_models.py

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

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AIRecommendationConfig:
    """Runtime settings for the AI recommendation assistant."""

    model_name: str = "Qwen/Qwen3-8B"
    hf_token_env: str = "HF_TOKEN"
    max_records: int = 200
    max_new_tokens: int = 512
    temperature: float = 0.0
    timeout_seconds: int = 60
    provider: str = "auto"
    enabled: bool = True
    issue_definitions_path: str = ""


@dataclass(frozen=True)
class FailureRecord:
    """Normalized unresolved validation failure sent to the recommendation layer."""

    workflow: str
    mapping: str
    transformation: str
    object_name: str
    failure_type: str
    validation_rule: str
    validation_message: str
    auto_fix_status: str
    severity: str
    error_details: str
    root_cause: str = ""
    rule_based_recommendation: str = ""
    source_file: str = ""
    migration_context: dict[str, object] = field(default_factory=dict)
    session: str = ""


@dataclass(frozen=True)
class Recommendation:
    """Validated recommendation returned by the model or a graceful fallback."""

    root_cause: str
    recommendation: str
    priority: str
    summary: str
    confidence: int = 0


@dataclass(frozen=True)
class RecommendationResult:
    """Recommendation plus execution metadata for report generation."""

    failure: FailureRecord
    recommendation: Recommendation
    processing_time_ms: int
    error: str = ""
