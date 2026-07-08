"""
Migration REST controller.
"""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_logger, get_migration_orchestrator
from api.schemas.migration import MigrationRequest, MigrationResponse
from business.migration.job_store import job_store
from business.migration_orchestrator import MigrationOrchestrator

router = APIRouter(prefix="/api/v1", tags=["Migration"])


@router.post("/migrate", response_model=MigrationResponse)
def migrate(
    request_body: MigrationRequest,
    orchestrator: MigrationOrchestrator = Depends(get_migration_orchestrator),
    logger=Depends(get_logger),
) -> dict[str, object]:
    """Start and execute the complete migration workflow."""

    job_id = uuid4().hex
    job_store.create(job_id)
    if not request_body.use_input_folder and not request_body.uploaded_xml_content:
        job_store.update(
            job_id,
            status="Failed",
            percentage=100,
            error="uploaded_xml_content is required when use_input_folder is false.",
            message="Migration failed.",
        )
        raise HTTPException(status_code=422, detail="uploaded_xml_content is required when use_input_folder is false.")

    def update_progress(percentage: int, message: str) -> None:
        job_store.update(job_id, status="Running", percentage=percentage, message=message)

    logger.info("API request started: POST /api/v1/migrate job_id=%s", job_id)
    try:
        result = orchestrator.run(
            job_id=job_id,
            uploaded_xml_name=request_body.uploaded_xml_name,
            uploaded_xml_content=request_body.uploaded_xml_content,
            persist_to_mysql=request_body.persist_to_mysql,
            progress=update_progress,
        )
    except (FileNotFoundError, ValueError) as exc:
        job_store.update(job_id, status="Failed", percentage=100, error=str(exc), message="Migration failed.")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Migration job failed: %s", job_id)
        job_store.update(job_id, status="Failed", percentage=100, error=str(exc), message="Migration failed.")
        raise HTTPException(status_code=500, detail="Migration job failed. See logs for details.") from exc

    job_store.update(job_id, status="Completed", percentage=100, result=result, message="Migration completed.")
    logger.info("API request completed: POST /api/v1/migrate job_id=%s", job_id)
    return result
