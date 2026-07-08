"""
Report and dashboard REST controllers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_migration_orchestrator
from api.schemas.migration import DashboardResponse, ReportsResponse
from business.migration.job_store import job_store
from business.migration_orchestrator import MigrationOrchestrator

router = APIRouter(prefix="/api/v1", tags=["Reports"])


@router.get("/reports/{job_id}", response_model=ReportsResponse)
def get_reports(
    job_id: str,
    orchestrator: MigrationOrchestrator = Depends(get_migration_orchestrator),
) -> dict[str, object]:
    """Return generated report artifact locations for a migration job."""

    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {"job_id": job_id, "status": job.status, "reports": orchestrator.generated_reports()}


@router.get("/dashboard/{job_id}", response_model=DashboardResponse)
def get_dashboard(
    job_id: str,
    orchestrator: MigrationOrchestrator = Depends(get_migration_orchestrator),
) -> dict[str, object]:
    """Return dashboard dataset rows for Streamlit."""

    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    dataset, source = orchestrator.dashboard_dataset()
    return {"job_id": job_id, "status": job.status, "dataset": dataset, "source": source}
