"""
Business adapter for IICS provider interactions.
"""

from __future__ import annotations

from typing import Any

from providers.iics_provider import IICSProvider
from providers.provider_factory import IICSProviderFactory


class IICSAdapter:
    """Coordinates IICS deployment through a pluggable provider."""

    def __init__(self, provider: IICSProvider | None = None, logger=None) -> None:
        self.provider = provider or IICSProviderFactory.create()
        self.logger = logger

    def deploy(self, mapping_payload: dict[str, Any]) -> dict[str, Any]:
        """Deploy a migrated mapping through the configured provider."""

        if self.logger:
            self.logger.info("Starting IICS deployment through %s", self.provider.__class__.__name__)
        login = self.provider.login()
        upload = self.provider.upload_mapping(mapping_payload)
        task = self.provider.create_task(str(upload["mapping_id"]))
        run = self.provider.run_task(str(task["task_id"]))
        status = self.provider.check_status(str(run["run_id"]))
        return {
            "provider": self.provider.__class__.__name__,
            "login": login,
            "upload": upload,
            "task": task,
            "run": run,
            "status": status,
        }
