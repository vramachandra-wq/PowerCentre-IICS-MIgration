"""
Initialize the schemas package.
Expose related migration toolkit modules for imports.
"""

from api.schemas.ai import (
    EvaluationMatrixResponse,
    EvaluationRequest,
    EvaluationResponse,
    RecommendationRequest,
    RecommendationResponse,
)
from api.schemas.migration import (
    DashboardResponse,
    HealthResponse,
    JobStatusResponse,
    MigrationRequest,
    MigrationResponse,
    ReportsResponse,
    ValidationSummary,
)

__all__ = [
    "DashboardResponse",
    "EvaluationMatrixResponse",
    "EvaluationRequest",
    "EvaluationResponse",
    "HealthResponse",
    "JobStatusResponse",
    "MigrationRequest",
    "MigrationResponse",
    "RecommendationRequest",
    "RecommendationResponse",
    "ReportsResponse",
    "ValidationSummary",
]
