"""
Health REST controller.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas.migration import HealthResponse

router = APIRouter(prefix="/api/v1", tags=["Health"])


@router.get("/health", response_model=HealthResponse)
def health() -> dict[str, str]:
    """Return API health."""

    return {
        "status": "UP",
        "service": "PowerCenter to IDMC Migration Accelerator API",
        "version": "1.0.0",
    }
