"""
Real IICS provider placeholder.
"""

from __future__ import annotations

from typing import Any


class RealIICSProvider:
    """Placeholder for future Informatica Cloud implementation."""

    def login(self) -> dict[str, Any]:
        """Authenticate with IICS."""

        # TODO: Implement real IICS login when tenant credentials are available.
        raise NotImplementedError("Real IICS login is not implemented.")

    def upload_mapping(self, mapping_payload: dict[str, Any]) -> dict[str, Any]:
        """Upload a mapping to IICS."""

        # TODO: Implement real IICS mapping upload.
        raise NotImplementedError("Real IICS mapping upload is not implemented.")

    def create_task(self, mapping_id: str) -> dict[str, Any]:
        """Create an IICS task."""

        # TODO: Implement real IICS task creation.
        raise NotImplementedError("Real IICS task creation is not implemented.")

    def run_task(self, task_id: str) -> dict[str, Any]:
        """Run an IICS task."""

        # TODO: Implement real IICS task execution.
        raise NotImplementedError("Real IICS task execution is not implemented.")

    def check_status(self, run_id: str) -> dict[str, Any]:
        """Check an IICS task run status."""

        # TODO: Implement real IICS status polling.
        raise NotImplementedError("Real IICS status polling is not implemented.")
