"""
Provider contract for Informatica Cloud integration.
"""

from __future__ import annotations

from typing import Any, Protocol


class IICSProvider(Protocol):
    """Defines the operations required by the IICS adapter."""

    def login(self) -> dict[str, Any]:
        """Authenticate with the provider."""

    def upload_mapping(self, mapping_payload: dict[str, Any]) -> dict[str, Any]:
        """Upload a mapping payload."""

    def create_task(self, mapping_id: str) -> dict[str, Any]:
        """Create a task for an uploaded mapping."""

    def run_task(self, task_id: str) -> dict[str, Any]:
        """Run a task."""

    def check_status(self, run_id: str) -> dict[str, Any]:
        """Return task run status."""
