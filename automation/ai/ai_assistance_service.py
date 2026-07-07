"""
Module: automation/ai/ai_assistance_service.py

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

import logging
from pathlib import Path
from typing import Any

from automation.evaluation_matrix import ReportRepository
from automation.ai.llm_client import RecommendationModelClient
from automation.ai.recommendation_engine import RecommendationEngine
from automation.ai.recommendation_models import AIRecommendationConfig, RecommendationResult


class AIRecommendationService:
    """Coordinates recommendation generation and writes the final report table."""

    FIELDNAMES = [
        "Workflow -> Session -> Mapping -> Transformations",
        "Assets",
        "Failures",
        "Root Cause",
        "AI Recommendation",
        "Priority",
        "AI Summary",
        "Severity",
        "Validation Rule",
        "Confidence",
        "Processing Time",
        "Auto Fix Status",
        "Error",
    ]

    def __init__(
        self,
        repository: ReportRepository | None = None,
        config: AIRecommendationConfig | None = None,
        client: RecommendationModelClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        """
        Executes the __init__ workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                repository (object): Value supplied by the caller and used by the workflow.
                config (object): Value supplied by the caller and used by the workflow.
                client (object): Value supplied by the caller and used by the workflow.
                logger (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.repository = repository or ReportRepository()
        self.config = config or AIRecommendationConfig()
        self.engine = RecommendationEngine(self.repository, self.config, client, logger)

    def run(self) -> tuple[list[RecommendationResult], Path]:
        """
        Executes the run workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        results = self.engine.recommend() if self.config.enabled else []
        return results, self.write(results)

    def write(self, results: list[RecommendationResult]) -> Path:
        # Keep the CSV column order aligned with the Streamlit and API table order.
        """
        Executes the write workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                results (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return self.repository.write_csv(
            "ai_recommendation_report.csv",
            [self._row(result) for result in results],
            self.FIELDNAMES,
        )

    @staticmethod
    def _row(result: RecommendationResult) -> dict[str, Any]:
        """
        Executes the _row workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                result (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        failure = result.failure
        recommendation = result.recommendation
        # The hierarchy column intentionally combines the workflow path into one field.
        return {
            "Workflow -> Session -> Mapping -> Transformations": AIRecommendationService.hierarchy(failure),
            "Assets": failure.object_name,
            "Failures": failure.failure_type,
            "Root Cause": recommendation.root_cause,
            "AI Recommendation": recommendation.recommendation,
            "Priority": recommendation.priority,
            "AI Summary": recommendation.summary,
            "Severity": failure.severity,
            "Validation Rule": failure.validation_rule,
            "Confidence": recommendation.confidence,
            "Processing Time": result.processing_time_ms,
            "Auto Fix Status": failure.auto_fix_status,
            "Error": result.error,
        }

    @staticmethod
    def hierarchy(failure: RecommendationResult | Any) -> str:
        """Formats the report hierarchy in the exact order requested by stakeholders."""
        record = failure.failure if isinstance(failure, RecommendationResult) else failure
        parts = [
            record.workflow,
            getattr(record, "session", ""),
            record.mapping,
            record.transformation,
        ]
        return " -> ".join(str(part) for part in parts if part)
