"""
Support recommendation models for automation data and validation workflows.
Prepares metrics, findings, and AI assistance outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AIRecommendationConfig:
    """Stores configuration values used by the application."""

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
    """Encapsulates failure record behavior for migration workflows."""

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
    """Encapsulates recommendation behavior for migration workflows."""

    root_cause: str
    recommendation: str
    priority: str
    summary: str
    confidence: int = 0


@dataclass(frozen=True)
class RecommendationResult:
    """Stores computed output from a migration workflow."""

    failure: FailureRecord
    recommendation: Recommendation
    processing_time_ms: int
    error: str = ""
