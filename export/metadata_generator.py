"""Generate review package metadata files from existing migration outputs."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from export.package_builder import GeneratedAsset, ReviewWorkflow, write_csv


class MetadataGenerator:
    """Create project, folder, export metadata, content CSV, and SYS review metadata."""

    CONTENT_FIELDNAMES = ["Workflow", "Session", "Mapping", "Asset Type", "File Name"]

    def write_project_metadata(
        self,
        explore_dir: Path,
        repositories: list[dict[str, str]],
        workflows: list[ReviewWorkflow],
    ) -> GeneratedAsset:
        """Write Explore/Project.json."""

        payload = {
            "reviewOnly": True,
            "generatedAt": self._now(),
            "repositories": repositories,
            "workflowCount": len(workflows),
            "projectNames": sorted({row.get("name", "") for row in repositories if row.get("name")}),
        }
        path = explore_dir / "Project.json"
        self._write_json(path, payload)
        return GeneratedAsset("", "", "", "Project", "Explore/Project.json")

    def write_folder_metadata(self, explore_dir: Path, folders: list[dict[str, str]]) -> GeneratedAsset:
        """Write Explore/Folder.json."""

        path = explore_dir / "Folder.json"
        self._write_json(path, {"reviewOnly": True, "generatedAt": self._now(), "folders": folders})
        return GeneratedAsset("", "", "", "Folder", "Explore/Folder.json")

    def write_sys_metadata(
        self,
        sys_dir: Path,
        workflows: list[ReviewWorkflow],
        sources: list[dict[str, str]],
        targets: list[dict[str, str]],
    ) -> list[GeneratedAsset]:
        """Write review connection and agent group metadata under SYS."""

        connections = self._connection_metadata(sources, targets)
        agents = self._agent_metadata(workflows)
        connection_path = sys_dir / "ConnectionMetadata.json"
        agent_path = sys_dir / "AgentGroupMetadata.json"
        self._write_json(connection_path, {"reviewOnly": True, "connections": connections})
        self._write_json(agent_path, {"reviewOnly": True, "agentGroups": agents})
        return [
            GeneratedAsset("", "", "", "Connection Metadata", "SYS/ConnectionMetadata.json"),
            GeneratedAsset("", "", "", "Agent Group Metadata", "SYS/AgentGroupMetadata.json"),
        ]

    def write_export_metadata(self, package_root: Path, assets: list[GeneratedAsset]) -> GeneratedAsset:
        """Write exportMetadata.v2.json."""

        payload = {
            "reviewOnly": True,
            "packageName": "Migration_Review_Package",
            "generatedAt": self._now(),
            "assetCount": len(assets),
            "assets": [
                {
                    "workflow": asset.workflow,
                    "session": asset.session,
                    "mapping": asset.mapping,
                    "assetType": asset.asset_type,
                    "fileName": asset.file_name,
                }
                for asset in assets
            ],
        }
        path = package_root / "exportMetadata.v2.json"
        self._write_json(path, payload)
        return GeneratedAsset("", "", "", "Export Metadata", "exportMetadata.v2.json")

    def write_contents_csv(self, package_root: Path, assets: list[GeneratedAsset]) -> GeneratedAsset:
        """Write ContentsofExportPackage.csv."""

        rows = [
            {
                "Workflow": asset.workflow,
                "Session": asset.session,
                "Mapping": asset.mapping,
                "Asset Type": asset.asset_type,
                "File Name": asset.file_name,
            }
            for asset in assets
        ]
        path = package_root / "ContentsofExportPackage.csv"
        write_csv(path, rows, self.CONTENT_FIELDNAMES)
        return GeneratedAsset("", "", "", "Package Contents", "ContentsofExportPackage.csv")

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _connection_metadata(sources: list[dict[str, str]], targets: list[dict[str, str]]) -> list[dict[str, str]]:
        rows: dict[tuple[str, str, str], dict[str, str]] = {}
        for row in [*sources, *targets]:
            key = (
                row.get("repository_name", ""),
                row.get("folder_name", ""),
                row.get("database_type", ""),
            )
            if key not in rows:
                rows[key] = {
                    "repositoryName": key[0],
                    "folderName": key[1],
                    "databaseType": key[2],
                    "reviewConnectionName": "_".join(part for part in key if part) or "ReviewConnection",
                }
        return list(rows.values())

    @staticmethod
    def _agent_metadata(workflows: list[ReviewWorkflow]) -> list[dict[str, str]]:
        rows: dict[str, dict[str, str]] = {}
        for workflow in workflows:
            name = workflow.server_name or "Review_Agent_Group"
            rows.setdefault(
                name,
                {
                    "agentGroupName": name,
                    "repositoryName": workflow.repository_name,
                    "folderName": workflow.folder_name,
                },
            )
        return list(rows.values())
