"""
Module: api/schemas/ai.py

Purpose:
    This module supports FastAPI service layer for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the FastAPI service layer area and exposes validation, recommendation, and evaluation results to UI and integration clients. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecommendationRequest(BaseModel):
    """
    Represents the RecommendationRequest component in the FastAPI service layer area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that exposes validation, recommendation, and evaluation results to UI and integration clients. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    validation_report: list[dict[str, Any]] | None = Field(default=None, alias="Validation Report")
    max_records: int | None = Field(default=None, ge=1, alias="Max Records")


class RecommendationResponse(BaseModel):
    """
    Represents the RecommendationResponse component in the FastAPI service layer area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that exposes validation, recommendation, and evaluation results to UI and integration clients. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    model_config = ConfigDict(populate_by_name=True)

    workflow_hierarchy: str = Field(alias="Workflow -> Session -> Mapping -> Transformations")
    assets: str = Field(alias="Assets")
    failures: str = Field(alias="Failures")
    root_cause: str = Field(alias="Root Cause")
    ai_recommendation: str = Field(alias="AI Recommendation")
    priority: str = Field(alias="Priority")
    ai_summary: str = Field(alias="AI Summary")


class EvaluationRequest(BaseModel):
    """
    Represents the EvaluationRequest component in the FastAPI service layer area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that exposes validation, recommendation, and evaluation results to UI and integration clients. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    refresh: bool = False


class EvaluationMatrixResponse(BaseModel):
    """
    Represents the EvaluationMatrixResponse component in the FastAPI service layer area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that exposes validation, recommendation, and evaluation results to UI and integration clients. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    model_config = ConfigDict(populate_by_name=True)

    average_confidence: int | float = Field(alias="Average Confidence")
    f1_score: int | float = Field(alias="F1 Score")
    ml_accuracy: int | float = Field(alias="ML Accuracy")
    ml_precision: int | float = Field(alias="ML Precision")
    model_success_rate: int | float = Field(alias="Model Success Rate")
    recall: int | float = Field(alias="Recall")
    total_evaluations: int | float = Field(alias="Total Evaluations")


class EvaluationResponse(BaseModel):
    """
    Represents the EvaluationResponse component in the FastAPI service layer area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that exposes validation, recommendation, and evaluation results to UI and integration clients. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    matrix: EvaluationMatrixResponse
