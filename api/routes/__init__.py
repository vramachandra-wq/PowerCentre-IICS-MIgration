"""
Initialize the routes package.
Expose related migration toolkit modules for imports.
"""

from api.evaluation_routes import router as evaluation_router
from api.recommendation_routes import router as recommendation_router

__all__ = ["evaluation_router", "recommendation_router"]
