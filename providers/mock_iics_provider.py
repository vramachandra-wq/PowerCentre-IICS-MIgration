"""
Mock IICS provider used until tenant credentials are available.
"""

from __future__ import annotations

from typing import Any


class MockIICSProvider:
    """Simulates successful IICS deployment without external calls."""

    def login(self) -> dict[str, Any]:
        """Return a mock login response."""

        return {"status": "SUCCESS", "session_id": "mock-session"}

    def upload_mapping(self, mapping_payload: dict[str, Any]) -> dict[str, Any]:
        """Return a mock mapping upload response."""

        mapping_name = str(mapping_payload.get("name") or "migration_mapping")
        return {"status": "SUCCESS", "mapping_id": f"mock-mapping-{mapping_name}"}

    def create_task(self, mapping_id: str) -> dict[str, Any]:
        """Return a mock task creation response."""

        return {"status": "SUCCESS", "task_id": f"mock-task-{mapping_id}"}

    def run_task(self, task_id: str) -> dict[str, Any]:
        """Return a mock task run response."""

        return {"status": "SUCCESS", "run_id": f"mock-run-{task_id}"}

    def check_status(self, run_id: str) -> dict[str, Any]:
        """Return a mock completed run status."""

        return {"status": "SUCCESS", "run_id": run_id, "state": "COMPLETED"}
