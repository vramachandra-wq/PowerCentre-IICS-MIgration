"""Generate review-only mapping packages from existing metadata tables."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from export.package_builder import GeneratedAsset, ReviewSession, ReviewWorkflow, safe_name


class MappingPackageGenerator:
    """Create one MTT zip for each workflow/session/mapping relationship."""

    def __init__(
        self,
        mappings: dict[str, dict[str, str]],
        transformations: dict[str, list[dict[str, str]]],
        ports: dict[str, list[dict[str, str]]],
        instances: dict[str, list[dict[str, str]]],
        connectors: dict[str, list[dict[str, str]]],
        sources_by_file: dict[str, list[dict[str, str]]],
        targets_by_file: dict[str, list[dict[str, str]]],
    ) -> None:
        self.mappings = mappings
        self.transformations = transformations
        self.ports = ports
        self.instances = instances
        self.connectors = connectors
        self.sources_by_file = sources_by_file
        self.targets_by_file = targets_by_file

    def generate(self, workflow: ReviewWorkflow, session: ReviewSession, output_root: Path) -> GeneratedAsset:
        """Generate a mapping package zip for the provided session relationship."""

        package_dir = (
            output_root
            / safe_name(workflow.workflow_name, max_length=36)
            / safe_name(session.session_name, max_length=36)
        )
        package_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{safe_name(session.mapping_name, max_length=36)}.MTT.zip"
        path = package_dir / file_name
        payload = self._payload(workflow, session)

        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("mapping.json", json.dumps(payload, indent=2, sort_keys=True))
            archive.writestr("manifest.json", json.dumps(self._manifest(workflow, session), indent=2, sort_keys=True))

        relative = (
            f"Explore/MappingPackages/{safe_name(workflow.workflow_name, max_length=36)}/"
            f"{safe_name(session.session_name, max_length=36)}/{file_name}"
        )
        return GeneratedAsset(workflow.workflow_name, session.session_name, session.mapping_name, "Mapping", relative)

    def _payload(self, workflow: ReviewWorkflow, session: ReviewSession) -> dict[str, Any]:
        mapping_row = self.mappings.get(session.mapping_name, {})
        return {
            "reviewOnly": True,
            "workflow": {
                "name": workflow.workflow_name,
                "repository": workflow.repository_name,
                "folder": workflow.folder_name,
                "sourceFile": workflow.file_name,
            },
            "session": {
                "name": session.session_name,
                "mapping": session.mapping_name,
                "repository": session.repository_name,
                "folder": session.folder_name,
            },
            "mapping": mapping_row,
            "sources": self.sources_by_file.get(session.file_name, []),
            "targets": self.targets_by_file.get(session.file_name, []),
            "instances": self.instances.get(session.mapping_name, []),
            "transformations": self.transformations.get(session.mapping_name, []),
            "ports": self.ports.get(session.mapping_name, []),
            "connectors": self.connectors.get(session.mapping_name, []),
        }

    @staticmethod
    def _manifest(workflow: ReviewWorkflow, session: ReviewSession) -> dict[str, str]:
        return {
            "assetType": "MTT",
            "reviewPackageType": "Mapping",
            "workflowName": workflow.workflow_name,
            "sessionName": session.session_name,
            "mappingName": session.mapping_name,
            "sourceFile": session.file_name,
        }
