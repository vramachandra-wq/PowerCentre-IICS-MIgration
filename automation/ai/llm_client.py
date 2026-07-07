"""
Support llm client for automation data and validation workflows.
Prepares metrics, findings, and AI assistance outputs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol

from automation.ai.prompt_builder import RecommendationPromptBuilder
from automation.ai.recommendation_models import AIRecommendationConfig, FailureRecord
from automation.ai.response_parser import RecommendationResponseParser


class RecommendationModelClient(Protocol):
    """Wraps external service calls used by the application."""

    def recommend(self, failure: FailureRecord) -> dict[str, Any]:
        """Recommend migration data using the provided failure."""

        ...


class HuggingFaceQwenRecommendationClient:
    """Wraps external service calls used by the application."""

    MODEL_ALIASES = {
        "Qwen/Qwen3-8B-Instruct": "Qwen/Qwen3-8B",
        "Qwen3-8B-Instruct": "Qwen/Qwen3-8B",
        "Qwen3-8B": "Qwen/Qwen3-8B",
    }

    def __init__(self, config: AIRecommendationConfig) -> None:
        """Initialize migration data using the provided config."""

        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            self._load_env_file(Path(".env"))
        token = os.getenv(config.hf_token_env)
        if not token:
            raise ValueError(f"Missing Hugging Face token in environment variable {config.hf_token_env}")
        self.config = config
        self.token = token
        self.prompt_builder = RecommendationPromptBuilder()

    def recommend(self, failure: FailureRecord) -> dict[str, Any]:
        """Recommend migration data using the provided failure."""

        try:
            import truststore

            truststore.inject_into_ssl()
        except ImportError:
            pass
        from huggingface_hub import InferenceClient

        provider = None if self.config.provider == "auto" else self.config.provider
        client = InferenceClient(
            model=self._model_name(self.config.model_name),
            provider=provider,
            token=self.token,
            timeout=self.config.timeout_seconds,
        )
        response = client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an Informatica PowerCenter to IDMC migration recommendation assistant. "
                        "Return JSON only. /no_think"
                    ),
                },
                {"role": "user", "content": self.prompt_builder.build(failure)},
            ],
            max_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature,
        )
        content = response.choices[0].message.content or "{}"
        recommendation = RecommendationResponseParser.parse(content)
        return {
            "root_cause": recommendation.root_cause,
            "recommendation": recommendation.recommendation,
            "priority": recommendation.priority,
            "summary": recommendation.summary,
            "confidence": recommendation.confidence,
        }

    @staticmethod
    def _load_env_file(path: Path) -> None:
        """Load env file using the provided path."""

        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")

    @classmethod
    def _model_name(cls, model_name: str) -> str:
        """Handle model name using the provided model_name."""

        return cls.MODEL_ALIASES.get(model_name, model_name)
