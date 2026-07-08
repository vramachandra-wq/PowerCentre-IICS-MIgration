"""
Initialize the routes package.
Expose related migration toolkit modules for imports.
"""

from api.evaluation_routes import router as evaluation_router
from api.routes.health_controller import router as health_router
from api.routes.job_controller import router as job_router
from api.routes.migration_controller import router as migration_router
from api.routes.report_controller import router as report_router
from api.recommendation_routes import router as recommendation_router

__all__ = [
    "evaluation_router",
    "health_router",
    "job_router",
    "migration_router",
    "recommendation_router",
    "report_router",
]
