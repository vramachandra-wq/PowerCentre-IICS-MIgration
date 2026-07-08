"""
Build consolidated IICS exportMetadata.v2.json from remediated PowerCenter XML files.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from business.parser.xml_parser import XMLParser
from common.config.config import AppConfig, ConfigLoader
from common.logger.logger import LoggerFactory


@dataclass(frozen=True)
class MappingExportRecord:
    """Mapping/session/workflow context used to build export objects."""

    repository_name: str
    project_name: str
    folder_name: str
    mapping_name: str
    session_name: str
    workflow_name: str
    source_file: str


class ExportMetadataBuilder:
    """Build one consolidated exportMetadata.v2.json from remediated XML files."""

    DEFAULT_CONFIG_PATH = Path("common/config/export_metadata_config.json")

    def __init__(
        self,
        output_folder: str | Path = "output",
        app_config: AppConfig | None = None,
        logger: logging.Logger | None = None,
        export_config_path: str | Path | None = None,
    ) -> None:
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(output_folder)
        self.remediated_folder = self.output_folder / "remediated_xml"
        self.app_config = app_config or ConfigLoader(self.project_root / "common/config/config.json").load()
        self.logger = logger or LoggerFactory.create_logger(
            self.app_config.logging,
            self.app_config.paths.log_folder,
        )
        self.export_config = self._load_export_config(export_config_path or self.DEFAULT_CONFIG_PATH)
        self.xml_parser = XMLParser(config=self.app_config, logger=self.logger)

    def build_and_write(self) -> dict[str, Any]:
        """Parse all remediated XML files and write one consolidated export JSON file."""

        xml_files = self._discover_remediated_xml_files()
        if not xml_files:
            message = f"No remediated XML files found in {self.remediated_folder}"
            self.logger.warning(message)
            return {"xml_files": 0, "exported_objects": 0, "output_file": "", "error": message}

        records: list[MappingExportRecord] = []
        errors: list[dict[str, str]] = []
        for xml_file in xml_files:
            try:
                parsed = self.xml_parser.parse_file(xml_file)
                records.extend(self._records_from_parsed(parsed.file_name, parsed))
                self.logger.info("Export metadata parsed remediated XML: %s", xml_file.name)
            except Exception as exc:
                self.logger.exception("Failed to parse remediated XML for export metadata: %s", xml_file.name)
                errors.append({"file_name": xml_file.name, "error": str(exc)})

        if not records:
            message = "No mapping records were extracted from remediated XML files."
            self.logger.warning(message)
            return {
                "xml_files": len(xml_files),
                "exported_objects": 0,
                "output_file": "",
                "errors": errors,
                "error": message,
            }

        payload = self._build_export_payload(records)
        output_path = self.output_folder / str(self.export_config.get("output_file", "exportMetadata.v2.json"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as json_file:
            json.dump(payload, json_file, indent=2, ensure_ascii=False)
            json_file.write("\n")

        summary = {
            "xml_files": len(xml_files),
            "mapping_records": len(records),
            "exported_objects": len(payload.get("exportedObjects", [])),
            "output_file": str(output_path),
            "errors": errors,
        }
        self.logger.info(
            "Consolidated export metadata written to %s. xml_files=%s exported_objects=%s",
            output_path,
            summary["xml_files"],
            summary["exported_objects"],
        )
        return summary

    def _discover_remediated_xml_files(self) -> list[Path]:
        """Return all remediated XML files in stable sorted order."""

        patterns = ("*.xml", "*.XML")
        files: list[Path] = []
        for pattern in patterns:
            files.extend(self.remediated_folder.glob(pattern))
        return sorted({path.resolve() for path in files}, key=lambda item: item.name.lower())

    def _records_from_parsed(self, file_name: str, parsed) -> list[MappingExportRecord]:
        """Convert parsed PowerCenter metadata into export mapping records."""

        records: list[MappingExportRecord] = []
        repository_name = parsed.repository.get("name", "")
        project_name = self._project_name(repository_name)
        for folder in parsed.folders:
            sessions_by_mapping = {session.mapping_name: session for session in folder.sessions}
            workflows_by_name = {workflow.workflow_name: workflow for workflow in folder.workflows}
            for mapping in folder.mappings:
                session = sessions_by_mapping.get(mapping.mapping_name)
                session_name = session.session_name if session else mapping.mapping_name
                workflow_name = self._workflow_name(
                    mapping.mapping_name,
                    session_name,
                    folder.workflows,
                    workflows_by_name,
                )
                records.append(
                    MappingExportRecord(
                        repository_name=repository_name,
                        project_name=project_name,
                        folder_name=folder.folder_name,
                        mapping_name=mapping.mapping_name,
                        session_name=session_name,
                        workflow_name=workflow_name,
                        source_file=file_name,
                    )
                )
        return records

    def _build_export_payload(self, records: list[MappingExportRecord]) -> dict[str, Any]:
        """Merge mapping records into one exportMetadata payload."""

        deduped_records = self._dedupe_records(records)
        project_name = deduped_records[0].project_name if deduped_records else str(self.export_config.get("project_name", "BIAINFADEV2_FLEX"))
        connection_name = str(self.export_config.get("connection_name", "DBConnection_OLAP_Oracle"))
        agent_group_name = str(self.export_config.get("agent_group_name", "PC Secure Agent Group"))

        project_guid = self._object_guid("Project", project_name)
        connection_guid = self._object_guid("Connection", connection_name)
        agent_group_guid = self._object_guid("AgentGroup", agent_group_name)

        exported_objects: list[dict[str, Any]] = [
            self._project_object(project_name, project_guid),
            self._connection_object(connection_name, connection_guid, agent_group_guid),
        ]

        mapping_objects: list[dict[str, Any]] = []
        folder_names: set[str] = set()
        for record in deduped_records:
            folder_names.add(record.folder_name)
            folder_path = f"/Explore/{record.project_name}/{record.folder_name}"
            dtemplate_guid = self._object_guid("DTEMPLATE", record.project_name, record.folder_name, record.mapping_name)
            mtt_guid = self._object_guid("MTT", record.project_name, record.folder_name, record.session_name)
            taskflow_guid = self._object_guid("TASKFLOW", record.project_name, record.folder_name, record.workflow_name)
            tags = self._folder_tags(record.folder_name)

            mapping_objects.append(
                self._mtt_object(
                    record.session_name,
                    folder_path,
                    mtt_guid,
                    [dtemplate_guid, connection_guid, agent_group_guid],
                    tags,
                )
            )
            mapping_objects.append(
                self._dtemplate_object(
                    record.mapping_name,
                    folder_path,
                    dtemplate_guid,
                    tags,
                )
            )
            mapping_objects.append(
                self._taskflow_object(
                    record.workflow_name,
                    folder_path,
                    taskflow_guid,
                    [mtt_guid],
                    tags,
                )
            )

        exported_objects.extend(mapping_objects)
        for folder_name in sorted(folder_names):
            exported_objects.append(
                self._folder_object(
                    folder_name,
                    f"/Explore/{project_name}",
                    self._object_guid("Folder", project_name, folder_name),
                )
            )
        exported_objects.append(self._agent_group_object(agent_group_name, agent_group_guid))

        return {
            "name": f"{self.export_config.get('job_name_prefix', 'job')}-{int(time.time() * 1000)}",
            "sourceOrgId": str(self.export_config.get("source_org_id", "")),
            "sourceOrgName": str(self.export_config.get("source_org_name", "")),
            "exportedObjects": exported_objects,
        }

    @staticmethod
    def _dedupe_records(records: list[MappingExportRecord]) -> list[MappingExportRecord]:
        """Keep one mapping record per project/folder/mapping combination."""

        deduped: dict[tuple[str, str, str], MappingExportRecord] = {}
        for record in sorted(records, key=lambda item: (item.folder_name.lower(), item.mapping_name.lower(), item.source_file.lower())):
            deduped[(record.project_name, record.folder_name, record.mapping_name)] = record
        return list(deduped.values())

    def _project_name(self, repository_name: str) -> str:
        mapping = self.export_config.get("repository_name_map", {})
        if isinstance(mapping, dict) and repository_name in mapping:
            return str(mapping[repository_name])
        configured = self.export_config.get("project_name")
        if configured:
            return str(configured)
        return repository_name or "BIAINFADEV2_FLEX"

    @staticmethod
    def _workflow_name(
        mapping_name: str,
        session_name: str,
        workflows: list[Any],
        workflows_by_name: dict[str, Any],
    ) -> str:
        if mapping_name in workflows_by_name:
            return mapping_name
        if session_name in workflows_by_name:
            return session_name
        for workflow in workflows:
            for task in workflow.task_instances:
                task_name = task.get("TASKNAME", "")
                if task_name in {mapping_name, session_name}:
                    return workflow.workflow_name
        if workflows:
            return workflows[0].workflow_name
        return mapping_name

    def _folder_tags(self, folder_name: str) -> list[dict[str, Any]] | None:
        folder_tags = self.export_config.get("folder_tags", {})
        if not isinstance(folder_tags, dict):
            return None
        tags = folder_tags.get(folder_name)
        return tags if isinstance(tags, list) and tags else None

    def _project_object(self, project_name: str, object_guid: str) -> dict[str, Any]:
        return {
            "objectGuid": object_guid,
            "objectName": project_name,
            "objectType": "Project",
            "path": "/Explore",
            "providerName": None,
            "metadata": {
                "modelVersion": {"major": 0, "minor": 0},
                "repoInfo": None,
                "objectRefs": [],
                "contextAttributes": [],
                "additionalInfo": {
                    "description": "Migrated project",
                    "contentType": "Binary",
                    "documentState": "COMPLETE",
                },
            },
        }

    def _connection_object(
        self,
        connection_name: str,
        object_guid: str,
        agent_group_guid: str,
    ) -> dict[str, Any]:
        return {
            "objectGuid": object_guid,
            "objectName": connection_name,
            "objectType": "Connection",
            "path": "/SYS",
            "providerName": None,
            "metadata": {
                "modelVersion": {"major": 0, "minor": 0},
                "repoInfo": {"repoHandle": self._repo_handle("Connection", connection_name)},
                "objectRefs": [agent_group_guid],
                "contextAttributes": [{"name": "id", "value": "@1"}],
                "additionalInfo": {
                    "description": None,
                    "contentType": "JSON",
                    "documentState": "COMPLETE",
                },
            },
        }

    def _mtt_object(
        self,
        session_name: str,
        folder_path: str,
        object_guid: str,
        object_refs: list[str],
        tags: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        metadata = {
            "modelVersion": {"major": 0, "minor": 0},
            "repoInfo": {"repoHandle": self._repo_handle("MTT", session_name)},
            "objectRefs": object_refs,
            "contextAttributes": [{"name": "id", "value": "@1"}],
            "additionalInfo": {
                "description": f"Session pushed from PC to ICS : {session_name}",
                "contentType": "JSON",
                "documentState": "VALID",
            },
        }
        if tags:
            metadata["tags"] = tags
        return {
            "objectGuid": object_guid,
            "objectName": session_name,
            "objectType": "MTT",
            "path": folder_path,
            "providerName": None,
            "metadata": metadata,
        }

    def _dtemplate_object(
        self,
        mapping_name: str,
        folder_path: str,
        object_guid: str,
        tags: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        metadata = {
            "modelVersion": {"major": 0, "minor": 0},
            "repoInfo": {"repoHandle": self._repo_handle("DTEMPLATE", mapping_name)},
            "objectRefs": [],
            "contextAttributes": [{"name": "id", "value": "@1"}],
            "additionalInfo": {
                "description": f"Mapping pushed from PC to ICS : {mapping_name}",
                "contentType": "JSON",
                "documentState": "VALID",
            },
        }
        if tags:
            metadata["tags"] = tags
        return {
            "objectGuid": object_guid,
            "objectName": mapping_name,
            "objectType": "DTEMPLATE",
            "path": folder_path,
            "providerName": None,
            "metadata": metadata,
        }

    def _taskflow_object(
        self,
        workflow_name: str,
        folder_path: str,
        object_guid: str,
        object_refs: list[str],
        tags: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        metadata = {
            "modelVersion": {"major": 1, "minor": 0},
            "repoInfo": {"repoHandle": self._repo_handle("TASKFLOW", workflow_name)},
            "objectRefs": object_refs,
            "contextAttributes": None,
            "additionalInfo": {
                "description": "These workflows are created from the Workflow Generation Wizard.",
                "contentType": "application/json; charset=utf-8",
                "documentState": "VALID",
            },
        }
        if tags:
            metadata["tags"] = tags
        return {
            "objectGuid": object_guid,
            "objectName": workflow_name,
            "objectType": "TASKFLOW",
            "path": folder_path,
            "providerName": None,
            "metadata": metadata,
        }

    def _folder_object(self, folder_name: str, project_path: str, object_guid: str) -> dict[str, Any]:
        return {
            "objectGuid": object_guid,
            "objectName": folder_name,
            "objectType": "Folder",
            "path": project_path,
            "providerName": None,
            "metadata": {
                "modelVersion": {"major": 0, "minor": 0},
                "repoInfo": None,
                "objectRefs": [],
                "contextAttributes": [],
                "additionalInfo": {
                    "description": "",
                    "contentType": "Binary",
                    "documentState": "COMPLETE",
                },
            },
        }

    def _agent_group_object(self, agent_group_name: str, object_guid: str) -> dict[str, Any]:
        return {
            "objectGuid": object_guid,
            "objectName": agent_group_name,
            "objectType": "AgentGroup",
            "path": "/SYS",
            "providerName": None,
            "metadata": {
                "modelVersion": {"major": 0, "minor": 0},
                "repoInfo": {"repoHandle": self._repo_handle("AgentGroup", agent_group_name)},
                "objectRefs": [],
                "contextAttributes": [{"name": "id", "value": "@1"}],
                "additionalInfo": {
                    "description": None,
                    "contentType": "JSON",
                    "documentState": "VALID",
                },
            },
        }

    @staticmethod
    def _object_guid(*parts: str) -> str:
        digest = hashlib.sha256("||".join(parts).encode("utf-8")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")[:22]

    @staticmethod
    def _repo_handle(*parts: str) -> str:
        digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest().upper()
        return f"010CW717{digest[:10]}"

    def _load_export_config(self, config_path: str | Path) -> dict[str, Any]:
        path = self._resolve_path(config_path)
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8-sig") as config_file:
            payload = json.load(config_file)
        return payload if isinstance(payload, dict) else {}

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def build_export_metadata(output_folder: str | Path = "output") -> dict[str, Any]:
    """Build consolidated export metadata JSON from remediated XML files."""

    return ExportMetadataBuilder(output_folder=output_folder).build_and_write()
