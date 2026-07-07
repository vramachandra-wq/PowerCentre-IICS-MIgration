"""
Module: automation/ai/llm_client.py

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

import os
from pathlib import Path
from typing import Any, Protocol

from automation.ai.prompt_builder import RecommendationPromptBuilder
from automation.ai.recommendation_models import AIRecommendationConfig, FailureRecord
from automation.ai.response_parser import RecommendationResponseParser


class RecommendationModelClient(Protocol):
    """Swappable model client for recommendation generation."""

    def recommend(self, failure: FailureRecord) -> dict[str, Any]:
        """
        Executes the recommend workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                failure (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        ...


class HuggingFaceQwenRecommendationClient:
    """Qwen recommendation client backed by Hugging Face chat completion."""

    MODEL_ALIASES = {
        "Qwen/Qwen3-8B-Instruct": "Qwen/Qwen3-8B",
        "Qwen3-8B-Instruct": "Qwen/Qwen3-8B",
        "Qwen3-8B": "Qwen/Qwen3-8B",
    }

    def __init__(self, config: AIRecommendationConfig) -> None:
        """
        Executes the __init__ workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                config (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the recommend workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                failure (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the _load_env_file workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the _model_name workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                model_name (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return cls.MODEL_ALIASES.get(model_name, model_name)
