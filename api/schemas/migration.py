"""
Schemas for migration REST APIs.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MigrationRequest(BaseModel):
    """Request body for starting a migration job."""

    use_input_folder: bool = True
    uploaded_xml_name: str | None = Field(default=None, min_length=1)
    uploaded_xml_content: str | None = Field(
        default=None,
        description="Raw XML text or base64-encoded XML content.",
    )
    persist_to_mysql: bool = False


class ValidationSummary(BaseModel):
    """Validation issue summary returned by migration APIs."""

    total_issues: int = 0
    open_issues: int = 0
    resolved_issues: int = 0
    severity_counts: dict[str, int] = Field(default_factory=dict)


class MigrationResponse(BaseModel):
    """Response returned after a migration job is submitted and executed."""

    job_id: str
    status: str
    readiness_score: float | None = None
    validation_summary: ValidationSummary = Field(default_factory=ValidationSummary)
    auto_fix_accuracy: float | None = None
    generated_report_locations: dict[str, str] = Field(default_factory=dict)
    iics_deployment: dict[str, Any] = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    """Response returned by job progress endpoint."""

    job_id: str
    status: str
    percentage: int = 0
    message: str | None = None
    error: str | None = None
    result: MigrationResponse | None = None


class ReportsResponse(BaseModel):
    """Response returned by report listing endpoint."""

    job_id: str
    status: str
    reports: dict[str, str] = Field(default_factory=dict)


class DashboardResponse(BaseModel):
    """Response returned by dashboard dataset endpoint."""

    job_id: str
    status: str
    dataset: list[dict[str, Any]] = Field(default_factory=list)
    source: str | None = None


class HealthResponse(BaseModel):
    """Application health response."""

    status: str
    service: str
    version: str
