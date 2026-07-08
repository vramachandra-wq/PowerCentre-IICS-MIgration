"""
Job progress REST controller.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas.migration import JobStatusResponse
from business.migration.job_store import job_store

router = APIRouter(prefix="/api/v1", tags=["Jobs"])


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str) -> dict[str, object]:
    """Return migration job progress."""

    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "percentage": job.percentage,
        "message": job.message,
        "error": job.error,
        "result": job.result,
    }
