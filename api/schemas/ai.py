from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecommendationRequest(BaseModel):
    validation_report: list[dict[str, Any]] | None = Field(default=None, alias="Validation Report")
    max_records: int | None = Field(default=None, ge=1, alias="Max Records")


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workflow: str = Field(alias="Workflow")
    failures: str = Field(alias="Failures")
    root_cause: str = Field(alias="Root Cause")
    ai_recommendation: str = Field(alias="AI Recommendation")
    priority: str = Field(alias="Priority")
    ai_summary: str = Field(alias="AI Summary")


class EvaluationRequest(BaseModel):
    refresh: bool = False


class EvaluationMatrixResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    average_confidence: int | float = Field(alias="Average Confidence")
    f1_score: int | float = Field(alias="F1 Score")
    ml_accuracy: int | float = Field(alias="ML Accuracy")
    ml_precision: int | float = Field(alias="ML Precision")
    model_success_rate: int | float = Field(alias="Model Success Rate")
    recall: int | float = Field(alias="Recall")
    total_evaluations: int | float = Field(alias="Total Evaluations")


class EvaluationResponse(BaseModel):
    matrix: EvaluationMatrixResponse
