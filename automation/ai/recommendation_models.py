from __future__ import annotations

from dataclasses import dataclass


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
