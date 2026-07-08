"""
In-memory job registry for REST migration requests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any


@dataclass
class MigrationJob:
    """Tracks migration job state for API progress responses."""

    job_id: str
    status: str = "Pending"
    percentage: int = 0
    message: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class JobStore:
    """Thread-safe in-memory job store."""

    def __init__(self) -> None:
        self._jobs: dict[str, MigrationJob] = {}
        self._lock = Lock()

    def create(self, job_id: str) -> MigrationJob:
        """Create a new job record."""

        job = MigrationJob(job_id=job_id)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> MigrationJob | None:
        """Return a job by identifier."""

        with self._lock:
            return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        percentage: int | None = None,
        message: str | None = None,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> MigrationJob:
        """Update a job and return the latest state."""

        with self._lock:
            job = self._jobs[job_id]
            if status is not None:
                job.status = status
            if percentage is not None:
                job.percentage = max(0, min(100, percentage))
            if message is not None:
                job.message = message
            if error is not None:
                job.error = error
            if result is not None:
                job.result = result
            job.updated_at = datetime.now(UTC).isoformat()
            return job


job_store = JobStore()
