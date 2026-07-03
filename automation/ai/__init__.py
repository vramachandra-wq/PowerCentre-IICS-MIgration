"""AI recommendation assistant for post-validation migration findings."""

from automation.ai.ai_assistance_service import AIRecommendationService
from automation.ai.recommendation_engine import RecommendationEngine
from automation.ai.recommendation_models import (
    AIRecommendationConfig,
    FailureRecord,
    Recommendation,
    RecommendationResult,
)

__all__ = [
    "AIRecommendationConfig",
    "AIRecommendationService",
    "FailureRecord",
    "Recommendation",
    "RecommendationEngine",
    "RecommendationResult",
]
