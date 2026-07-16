"""
Generate IDMC export packages from remediated PowerCenter XML metadata.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from business.iics.iics_success_benchmark import IICSSuccessBenchmark
from business.parser.xml_parser import XMLParser
from common.config.config import AppConfig
from data.models.mapping_model import MappingMetadata, ParsedXmlMetadata, SessionMetadata, TargetMetadata, to_plain_dict


@dataclass(frozen=True)
class IdmcExportSummary:
    """Summarizes a generated IDMC export package."""

    input_xml_count: int
    mapping_count: int
    artifact_count: int
    package_path: str
    staging_folder: str


@dataclass(frozen=True)
class _AssetIds:
    project: str
    folder: str
    connection: str
    agent_group: str
    dtemplate: str
    mtt: str
    taskflow: str


class IdmcExportPackageGenerator:
    """Builds one combined IDMC-style export package from remediated XML files."""

    PROJECT_NAME = "BIAINFADEV2_FLEX"
    FOLDER_NAME = "Custom_Project_Export"
    CONNECTION_NAME = "DataWarehouse_PA"
    AGENT_GROUP_NAME = "PC Secure Agent Group"

    def __init__(
        self,
        config: AppConfig,
        logger,
        remediated_folder: str | Path | None = None,
        output_folder: str | Path | None = None,
        package_name: str = "Custom_Project_Export.zip",
        execution_strategy: str = "POWERCENTER_XML_TASK",
        reference_package: str | Path | None = None,
    ) -> None:
        """Initialize the package generator using existing app configuration."""

        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(output_folder or config.paths.output_folder)
        self.remediated_folder = self._resolve_path(remediated_folder or self.output_folder / "remediated_xml")
        self.package_name = package_name
        self.execution_strategy = execution_strategy
        self.reference_package = self._default_reference_package(reference_package)
        self.folder_name = self.FOLDER_NAME
        self.package_path = self.output_folder / package_name
        self.staging_folder = self.output_folder / "idmc_export_package"
        self.parser = XMLParser(config=config, logger=logger)

    def generate(self) -> IdmcExportSummary:
        """Generate one combined ZIP package from all XML files in remediated_xml."""

        xml_files = self._xml_files()
        if not xml_files:
            raise FileNotFoundError(f"No XML files found in {self.remediated_folder}")

        now = datetime.now(timezone.utc)
        self._prepare_staging_folder(now)

        parsed_files = self._parse_xml_files(xml_files)
        mapping_assets = self._mapping_assets(parsed_files)
        mapping_assets = self._publishable_mapping_assets(mapping_assets)
        if not mapping_assets:
            raise ValueError(f"No mappings found in XML files under {self.remediated_folder}")

        ids = self._base_ids()
        sample_templates: list[dict[str, Any]] = []
        self._write_container_artifacts(ids, now, len(mapping_assets))

        exported_objects = [
            self._exported_object(ids.project, self.PROJECT_NAME, "Project", "/Explore", "Binary", "COMPLETE", "Migrated project"),
        ]
        contents_rows = [
            {"objectPath": "/Explore", "objectName": self.PROJECT_NAME, "objectType": "Project", "id": ids.project},
        ]

        if self.execution_strategy == "POWERCENTER_XML_TASK":
            sample_templates = self._sample_asset_templates()
            if sample_templates:
                dependencies = self._reference_dependencies(sample_templates)
                for dependency in dependencies:
                    self._write_reference_dependency_artifact(dependency)
                    exported_objects.append(dependency["exported_object"])
                    contents_rows.append(
                        {
                            "objectPath": dependency["path"],
                            "objectName": dependency["name"],
                            "objectType": dependency["type"],
                            "id": dependency["id"],
                        }
                    )
                taskflow_groups: dict[str, dict[str, Any]] = {}
                for index, asset in enumerate(mapping_assets):
                    asset_ids = self._asset_ids(asset["name"])
                    asset["ids"] = asset_ids
                    template = self._template_for_asset(sample_templates, asset["name"], index)
                    dependency_refs = self._dependency_refs_for_template(template)
                    self._write_sample_backed_mapping_artifacts(
                        asset,
                        asset_ids,
                        template,
                        ids,
                        now,
                    )
                    object_path = f"/Explore/{self.PROJECT_NAME}/{self.folder_name}"
                    exported_objects.extend(
                        [
                            self._exported_object(
                                asset_ids.dtemplate,
                                asset["name"],
                                "DTEMPLATE",
                                object_path,
                                "JSON",
                                "VALID",
                                f"Sample-backed CDI conversion placeholder for remediated XML : {asset['name']}",
                            ),
                            self._exported_object(
                                asset_ids.mtt,
                                asset["name"],
                                "MTT",
                                object_path,
                                "JSON",
                                "VALID",
                                f"Sample-backed mapping task wrapper for remediated XML : {asset['name']}",
                                [asset_ids.dtemplate, *dependency_refs],
                            ),
                        ]
                    )
                    contents_rows.extend(
                        [
                            {"objectPath": object_path, "objectName": asset["name"], "objectType": "DTEMPLATE", "id": asset_ids.dtemplate},
                            {"objectPath": object_path, "objectName": asset["name"], "objectType": "MTT", "id": asset_ids.mtt},
                        ]
                    )
                    group_key = asset.get("workflow_key") or asset["name"]
                    group = taskflow_groups.setdefault(
                        group_key,
                        {
                            "name": asset.get("workflow_name") or asset["name"],
                            "assets": [],
                            "links": asset.get("workflow_links", []),
                        },
                    )
                    group["assets"].append(asset)

                for group in taskflow_groups.values():
                    taskflow_name = self._asset_name(group["name"])
                    taskflow_id = self._guid("taskflow", taskflow_name)
                    workflow_templates = self._success_workflow_templates(len(group["assets"]))
                    taskflow_text = self._workflow_taskflow_xml(
                        taskflow_name,
                        taskflow_id,
                        group["assets"],
                        sample_templates,
                        now,
                        workflow_templates=workflow_templates,
                    )
                    entry_id = self._taskflow_entry_id_from_text(taskflow_text) or f"{taskflow_id}-gt-{self._epoch_millis(now)}::tf.xml"
                    taskflow_refs = self._ordered_unique(
                        [
                            *[asset["ids"].mtt for asset in group["assets"]],
                            *self._taskflow_mtt_refs(taskflow_text),
                        ]
                    )
                    mapping_folder = self.staging_folder / "Explore" / self.PROJECT_NAME / self.folder_name
                    (mapping_folder / f"{taskflow_name}.TASKFLOW.xml").write_text(taskflow_text, encoding="utf-8")
                    object_path = f"/Explore/{self.PROJECT_NAME}/{self.folder_name}"
                    exported_objects.append(
                        self._exported_object(
                            taskflow_id,
                            taskflow_name,
                            "TASKFLOW",
                            object_path,
                            "application/json; charset=utf-8",
                            "VALID",
                            "These workflows are created from the Workflow Generation Wizard.",
                            taskflow_refs,
                            model_version={"major": 1, "minor": 0},
                            repo_handle=entry_id,
                            context_attributes=None,
                        )
                    )
                    contents_rows.append(
                        {"objectPath": object_path, "objectName": taskflow_name, "objectType": "TASKFLOW", "id": taskflow_id}
                    )
            else:
                self.logger.warning(
                    "No reference IDMC export package was found. Falling back to generated placeholder DTEMPLATE/MTT/TASKFLOW artifacts."
                )
                self._write_system_artifacts(ids, now)
                exported_objects.append(
                    self._exported_object(ids.connection, self.CONNECTION_NAME, "Connection", "/SYS", "JSON", "COMPLETE", None, [ids.agent_group])
                )
                contents_rows.append(
                    {"objectPath": "/SYS", "objectName": self.CONNECTION_NAME, "objectType": "Connection", "id": ids.connection}
                )
                self._write_pcxml_source_bundle(xml_files, mapping_assets, now)
                for asset in mapping_assets:
                    asset_ids = self._asset_ids(asset["name"])
                    self._write_mapping_artifacts(asset, asset_ids, now)
                    object_path = f"/Explore/{self.PROJECT_NAME}/{self.folder_name}"
                    exported_objects.extend(
                        [
                            self._exported_object(
                                asset_ids.dtemplate,
                                asset["name"],
                                "DTEMPLATE",
                                object_path,
                                "JSON",
                                "VALID",
                                f"Generated CDI conversion placeholder for remediated XML : {asset['name']}",
                            ),
                            self._exported_object(
                                asset_ids.mtt,
                                asset["name"],
                                "MTT",
                                object_path,
                                "JSON",
                                "VALID",
                                f"Generated mapping task wrapper for remediated XML : {asset['name']}",
                                [asset_ids.dtemplate, ids.connection, ids.agent_group],
                            ),
                            self._exported_object(
                                asset_ids.taskflow,
                                asset["name"],
                                "TASKFLOW",
                                object_path,
                                "application/json; charset=utf-8",
                                "VALID",
                                "Generated PowerCenter XML taskflow wrapper.",
                                [asset_ids.mtt],
                                model_version={"major": 1, "minor": 0},
                            ),
                        ]
                    )
                    contents_rows.extend(
                        [
                            {"objectPath": object_path, "objectName": asset["name"], "objectType": "DTEMPLATE", "id": asset_ids.dtemplate},
                            {"objectPath": object_path, "objectName": asset["name"], "objectType": "MTT", "id": asset_ids.mtt},
                            {"objectPath": object_path, "objectName": asset["name"], "objectType": "TASKFLOW", "id": asset_ids.taskflow},
                        ]
                    )
        else:
            self._write_system_artifacts(ids, now)
            exported_objects.append(
                self._exported_object(ids.connection, self.CONNECTION_NAME, "Connection", "/SYS", "JSON", "COMPLETE", None, [ids.agent_group])
            )
            contents_rows.append(
                {"objectPath": "/SYS", "objectName": self.CONNECTION_NAME, "objectType": "Connection", "id": ids.connection}
            )
            for asset in mapping_assets:
                asset_ids = self._asset_ids(asset["name"])
                self._write_mapping_artifacts(asset, asset_ids, now)
                object_path = f"/Explore/{self.PROJECT_NAME}/{self.folder_name}"
                exported_objects.extend(
                    [
                        self._exported_object(
                            asset_ids.mtt,
                            asset["name"],
                            "MTT",
                            object_path,
                            "JSON",
                            "VALID",
                            f"PowerCenter XML task package for remediated XML : {asset['name']}",
                            [asset_ids.dtemplate, ids.connection, ids.agent_group],
                        ),
                        self._exported_object(
                            asset_ids.dtemplate,
                            asset["name"],
                            "DTEMPLATE",
                            object_path,
                            "JSON",
                            "VALID",
                            f"Remediated PowerCenter XML conversion source : {asset['name']}",
                        ),
                        self._exported_object(
                            asset_ids.taskflow,
                            asset["name"],
                            "TASKFLOW",
                            object_path,
                            "application/json; charset=utf-8",
                            "VALID",
                            "These workflows are created from the Workflow Generation Wizard.",
                            [asset_ids.mtt],
                            model_version={"major": 1, "minor": 0},
                        ),
                    ]
                )
                contents_rows.extend(
                    [
                        {"objectPath": object_path, "objectName": asset["name"], "objectType": "MTT", "id": asset_ids.mtt},
                        {"objectPath": object_path, "objectName": asset["name"], "objectType": "DTEMPLATE", "id": asset_ids.dtemplate},
                        {"objectPath": object_path, "objectName": asset["name"], "objectType": "TASKFLOW", "id": asset_ids.taskflow},
                    ]
                )

        exported_objects.append(
            self._exported_object(ids.folder, self.folder_name, "Folder", f"/Explore/{self.PROJECT_NAME}", "Binary", "COMPLETE", "")
        )
        contents_rows.append(
            {"objectPath": f"/Explore/{self.PROJECT_NAME}", "objectName": self.folder_name, "objectType": "Folder", "id": ids.folder}
        )
        if not sample_templates:
            exported_objects.append(
                self._exported_object(ids.agent_group, self.AGENT_GROUP_NAME, "AgentGroup", "/SYS", "JSON", "VALID", None)
            )
            contents_rows.append(
                {"objectPath": "/SYS", "objectName": self.AGENT_GROUP_NAME, "objectType": "AgentGroup", "id": ids.agent_group}
            )

        self._write_export_metadata(exported_objects, now)
        self._write_contents_csv(contents_rows, now)
        self._assert_staging_dtemplate_integrity()
        self._write_checksum()
        self._zip_staging_folder()
        self.logger.info(
            "Generated combined IDMC export package. xml_files=%s mappings=%s package=%s",
            len(xml_files),
            len(mapping_assets),
            self.package_path,
        )
        return IdmcExportSummary(
            input_xml_count=len(xml_files),
            mapping_count=len(mapping_assets),
            artifact_count=len(contents_rows),
            package_path=str(self.package_path),
            staging_folder=str(self.staging_folder),
        )

    def _prepare_staging_folder(self, now: datetime) -> None:
        if self.staging_folder.exists():
            try:
                shutil.rmtree(self.staging_folder)
            except PermissionError:
                fallback = self.output_folder / f"idmc_export_package_{self._epoch_millis(now)}"
                self.logger.warning(
                    "Existing IDMC export staging folder is locked. Using fallback staging folder: %s",
                    fallback,
                )
                self.staging_folder = fallback
        self.staging_folder.mkdir(parents=True, exist_ok=True)

    def _parse_xml_files(self, xml_files: list[Path]) -> list[ParsedXmlMetadata]:
        parsed_files: list[ParsedXmlMetadata] = []
        for xml_file in xml_files:
            parsed_files.append(self.parser.parse_file(xml_file))
            self.logger.info("Parsed remediated XML for IDMC export: %s", xml_file.name)
        return parsed_files

    def _mapping_assets(self, parsed_files: list[ParsedXmlMetadata]) -> list[dict[str, Any]]:
        assets: list[dict[str, Any]] = []
        seen: set[str] = set()
        for parsed in parsed_files:
            for folder in parsed.folders:
                sessions = {session.mapping_name: session for session in folder.sessions if session.mapping_name}
                workflow_by_session = self._workflow_by_session(folder.workflows)
                for mapping in folder.mappings:
                    session = sessions.get(mapping.mapping_name)
                    workflow = workflow_by_session.get(session.session_name if session else "")
                    name = self._asset_name(
                        session.session_name if workflow and session and session.session_name else mapping.mapping_name
                    )
                    unique_name = self._unique_name(name, seen)
                    seen.add(unique_name)
                    assets.append(
                        {
                            "name": unique_name,
                            "source_xml": parsed.file_name,
                            "source_xml_path": self.remediated_folder / parsed.file_name,
                            "repository": parsed.repository,
                            "folder": folder.folder_name,
                            "mapping": mapping,
                            "session": session,
                            "workflow_name": workflow.workflow_name if workflow else unique_name,
                            "workflow_key": f"{parsed.file_name}:{folder.folder_name}:{workflow.workflow_name if workflow else unique_name}",
                            "workflow_links": workflow.workflow_links if workflow else [],
                            "sources": folder.sources,
                            "targets": folder.targets,
                        }
                    )
        return assets

    @staticmethod
    def _workflow_by_session(workflows) -> dict[str, Any]:
        by_session: dict[str, Any] = {}
        for workflow in workflows:
            for task in workflow.task_instances:
                if task.get("TASKTYPE", "").lower() != "session":
                    continue
                for key in ("TASKNAME", "NAME"):
                    session_name = task.get(key, "")
                    if session_name:
                        by_session[session_name] = workflow
        return by_session

    def _publishable_mapping_assets(self, assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for asset in assets:
            grouped.setdefault(asset.get("workflow_key") or asset["name"], []).append(asset)

        publishable: list[dict[str, Any]] = []
        for group_assets in grouped.values():
            if len(group_assets) == 1:
                publishable.extend(group_assets)
                continue
            workflow_name = self._asset_name(group_assets[0].get("workflow_name") or "")
            business_assets = [
                asset
                for asset in group_assets
                if asset["name"] == workflow_name or asset["name"].startswith(workflow_name)
            ]
            publishable.extend(business_assets or group_assets)
        return publishable

    def _write_system_artifacts(self, ids: _AssetIds, now: datetime) -> None:
        sys_folder = self.staging_folder / "SYS"
        sys_folder.mkdir(parents=True, exist_ok=True)
        self._write_zip(
            sys_folder / f"{self.CONNECTION_NAME}.Connection.zip",
            {
                "connection.json": self._json_bytes(
                    [
                        {
                            "@type": "connection",
                            "id": "@1",
                            "name": self.CONNECTION_NAME,
                            "runtimeEnvironmentId": f"@{ids.agent_group}",
                            "instanceDisplayName": "Oracle",
                            "host": "default-host",
                            "database": "orcl",
                            "codepage": "UTF-8",
                            "adjustedJdbcHostName": "default-host",
                            "type": "Oracle",
                            "baseType": "Oracle",
                            "port": 1521,
                            "password": "********",
                            "username": "default-username",
                            "majorUpdateTime": self._timestamp(now),
                            "timeout": 60,
                            "connParams": {"agentGroupId": ids.agent_group},
                            "internal": False,
                            "federatedId": ids.connection,
                            "retryNetworkError": False,
                            "metadataBrowsable": True,
                            "connectorStatus": "ACTIVE",
                        }
                    ]
                ),
                "metadata.meta": self._json_bytes([{"@type": "objectRef", "id": "@1", "type": "connection"}]),
            },
        )
        self._write_zip(
            sys_folder / f"{self.AGENT_GROUP_NAME}.AgentGroup.zip",
            {
                "agentGroup.json": self._json_bytes(
                    [
                        {
                            "@type": "agentGroup",
                            "id": "@1",
                            "name": self.AGENT_GROUP_NAME,
                            "description": "Generated runtime environment placeholder",
                            "federatedId": ids.agent_group,
                        }
                    ]
                ),
                "metadata.meta": self._json_bytes([{"@type": "objectRef", "id": "@1", "type": "agentGroup"}]),
            },
        )

    def _write_container_artifacts(self, ids: _AssetIds, now: datetime, mapping_count: int) -> None:
        explore = self.staging_folder / "Explore"
        project_folder = explore / self.PROJECT_NAME
        project_folder.mkdir(parents=True, exist_ok=True)
        (project_folder / self.folder_name).mkdir(parents=True, exist_ok=True)
        (explore / f"{self.PROJECT_NAME}.Project.json").write_text(
            json.dumps(
                self._odata_document(
                    "Project",
                    ids.project,
                    self.PROJECT_NAME,
                    "Migrated project",
                    now,
                    subcontainer_count=1,
                    parent_info=[{"parentId": "ROOT", "parentName": "Explore", "parentType": "Space"}],
                ),
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        (project_folder / f"{self.folder_name}.Folder.json").write_text(
            json.dumps(
                self._odata_document(
                    "Folder",
                    ids.folder,
                    self.folder_name,
                    "",
                    now,
                    subcontainer_count=mapping_count,
                    parent_info=[
                        {"parentId": "ROOT", "parentName": "Explore", "parentType": "Space"},
                        {"parentId": ids.project, "parentName": self.PROJECT_NAME, "parentType": "Project"},
                    ],
                ),
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    def _write_pcxml_source_bundle(self, xml_files: list[Path], mapping_assets: list[dict[str, Any]], now: datetime) -> None:
        bundle_folder = self.staging_folder / "PCXML" / self.folder_name
        bundle_folder.mkdir(parents=True, exist_ok=True)
        for xml_file in xml_files:
            shutil.copy2(xml_file, bundle_folder / xml_file.name)

        by_xml: dict[str, list[str]] = {}
        for asset in mapping_assets:
            by_xml.setdefault(asset["source_xml"], []).append(asset["name"])

        manifest = {
            "name": f"{self.folder_name}_PowerCenterXml_Source_Bundle",
            "createdTime": self._timestamp(now),
            "executionStrategy": self.execution_strategy,
            "nativeCdiMapping": False,
            "importBehavior": (
                "This bundle intentionally does not declare DTEMPLATE, MTT, or TASKFLOW objects in exportMetadata.v2.json. "
                "Remediated PowerCenter XML cannot be imported directly as native CDI mappings; use these XML files as "
                "PowerCenter XML task inputs, conversion sources, or IICS API payloads."
            ),
            "xmlFiles": [
                {
                    "fileName": xml_file.name,
                    "relativePath": f"PCXML/{self.folder_name}/{xml_file.name}",
                    "mappings": sorted(by_xml.get(xml_file.name, [])),
                    "sha256": hashlib.sha256(xml_file.read_bytes()).hexdigest().upper(),
                }
                for xml_file in xml_files
            ],
            "mappingCount": len(mapping_assets),
        }
        (bundle_folder / "pc_xml_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _sample_asset_templates(self) -> list[dict[str, Any]]:
        if not self.reference_package or not self.reference_package.exists():
            return []

        with zipfile.ZipFile(self.reference_package) as package:
            metadata = json.loads(package.read("exportMetadata.v2.json"))
            objects = metadata.get("exportedObjects", [])
            connections = [item for item in objects if item.get("objectType") == "Connection"]
            agent_groups = [item for item in objects if item.get("objectType") == "AgentGroup"]
            connection = connections[0] if connections else {}
            agent_group = agent_groups[0] if agent_groups else {}
            dependencies = self._load_reference_dependency_templates(package, objects)
            runtime_dependency = self._preferred_runtime_dependency(dependencies)
            connection_dependency = self._preferred_connection_dependency(dependencies)
            if runtime_dependency:
                dependencies = [
                    self._normalize_dependency_runtime(dependency, runtime_dependency)
                    for dependency in dependencies
                ]
                dependencies = [
                    dependency
                    for dependency in dependencies
                    if dependency["type"] != "AgentGroup" or dependency["id"] == runtime_dependency["id"]
                ]
            if connection_dependency:
                dependencies = [
                    dependency
                    for dependency in dependencies
                    if dependency["type"] != "Connection" or dependency["id"] == connection_dependency["id"]
                ]
            taskflows = [item for item in objects if item.get("objectType") == "TASKFLOW"]
            workflow_templates = []
            for taskflow in taskflows:
                base_path = taskflow.get("path", "").strip("/")
                name = taskflow.get("objectName", "")
                taskflow_xml = f"{base_path}/{name}.TASKFLOW.xml" if base_path else f"{name}.TASKFLOW.xml"
                if name and taskflow_xml in package.namelist():
                    workflow_templates.append(
                        {
                            "name": name,
                            "taskflow_id": taskflow.get("objectGuid", ""),
                            "taskflow_xml": package.read(taskflow_xml).decode("utf-8"),
                            "repo_handle": (taskflow.get("metadata", {}).get("repoInfo") or {}).get("repoHandle"),
                        }
                    )
            templates: list[dict[str, Any]] = []
            dtemplates = {item.get("objectGuid", ""): item for item in objects if item.get("objectType") == "DTEMPLATE"}
            dtemplates_by_name = {item.get("objectName", ""): item for item in dtemplates.values()}
            for mtt in [item for item in objects if item.get("objectType") == "MTT"]:
                name = mtt.get("objectName", "")
                if not name:
                    continue
                mtt_base_path = mtt.get("path", "").strip("/")
                mtt_zip = f"{mtt_base_path}/{name}.MTT.zip" if mtt_base_path else f"{name}.MTT.zip"
                if mtt_zip not in package.namelist():
                    continue
                mtt_payload = self._zip_json_member(package.read(mtt_zip), "mtTask.json")
                mapping_id = ""
                if mtt_payload and isinstance(mtt_payload[0], dict):
                    mapping_id = str(mtt_payload[0].get("mappingId", "")).lstrip("@")
                dtemplate = dtemplates.get(mapping_id) or dtemplates_by_name.get(name)
                if not dtemplate:
                    continue
                dtemplate_name = dtemplate.get("objectName", "")
                base_path = dtemplate.get("path", "").strip("/")
                artifact_prefix = f"{base_path}/{dtemplate_name}" if base_path else dtemplate_name
                dtemplate_zip = f"{artifact_prefix}.DTEMPLATE.zip"
                if not all(item in package.namelist() for item in [dtemplate_zip, mtt_zip]):
                    continue
                templates.append(
                    {
                        "name": name,
                        "dtemplate_id": dtemplate.get("objectGuid", ""),
                        "mtt_id": mtt.get("objectGuid", ""),
                        "workflow_templates": workflow_templates,
                        "connection_id": connection_dependency["id"] if connection_dependency else connection.get("objectGuid", ""),
                        "connection_ids": [item.get("objectGuid", "") for item in connections],
                        "agent_group_id": runtime_dependency["id"] if runtime_dependency else agent_group.get("objectGuid", ""),
                        "agent_group_ids": [item.get("objectGuid", "") for item in agent_groups],
                        "dependencies": dependencies,
                        "runtime_environment_id": runtime_dependency["id"] if runtime_dependency else agent_group.get("objectGuid", ""),
                        "dtemplate_zip": package.read(dtemplate_zip),
                        "mtt_zip": package.read(mtt_zip),
                    }
                )
            return templates

    @staticmethod
    def _template_for_asset(templates: list[dict[str, Any]], asset_name: str, index: int) -> dict[str, Any]:
        return next((template for template in templates if template.get("name") == asset_name), templates[index % len(templates)])

    @staticmethod
    def _reference_dependencies(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        dependencies: dict[str, dict[str, Any]] = {}
        for template in templates:
            for dependency in template.get("dependencies", []):
                dependencies[dependency["id"]] = dependency
        return list(dependencies.values())

    def _dependency_refs_for_template(self, template: dict[str, Any]) -> list[str]:
        runtime_id = template.get("runtime_environment_id", "")
        refs: list[str] = []
        for dependency in template.get("dependencies", []):
            if dependency["type"] == "AgentGroup":
                if dependency["id"] != runtime_id:
                    continue
            refs.append(dependency["id"])
        return self._ordered_unique(refs)

    def _preferred_runtime_dependency(self, dependencies: list[dict[str, Any]]) -> dict[str, Any] | None:
        agent_groups = [dependency for dependency in dependencies if dependency["type"] == "AgentGroup"]
        return next(
            (dependency for dependency in agent_groups if dependency["name"] == self.AGENT_GROUP_NAME),
            agent_groups[0] if agent_groups else None,
        )

    def _preferred_connection_dependency(self, dependencies: list[dict[str, Any]]) -> dict[str, Any] | None:
        connections = [dependency for dependency in dependencies if dependency["type"] == "Connection"]
        return next(
            (dependency for dependency in connections if dependency["name"] == self.CONNECTION_NAME),
            connections[0] if connections else None,
        )

    def _normalize_dependency_runtime(
        self,
        dependency: dict[str, Any],
        runtime_dependency: dict[str, Any],
    ) -> dict[str, Any]:
        if dependency["type"] != "Connection":
            return dependency

        updated = dict(dependency)
        exported_object = json.loads(json.dumps(dependency["exported_object"]))
        exported_object.setdefault("metadata", {})["objectRefs"] = [runtime_dependency["id"]]
        updated["exported_object"] = exported_object
        updated["normalized_artifact_bytes"] = self._normalize_connection_zip(
            dependency["artifact_bytes"],
            runtime_dependency,
        )
        return updated

    def _normalize_connection_zip(
        self,
        source_bytes: bytes,
        runtime_dependency: dict[str, Any],
    ) -> bytes:
        runtime_id = runtime_dependency["id"]
        runtime_repo_handle = (
            (runtime_dependency.get("exported_object", {}).get("metadata", {}).get("repoInfo") or {}).get("repoHandle")
            or runtime_id
        )
        rewritten: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as source_zip:
            for member in source_zip.namelist():
                content = source_zip.read(member)
                if member == "connection.json":
                    payload = json.loads(content.decode("utf-8"))
                    for connection in payload:
                        if not isinstance(connection, dict):
                            continue
                        connection["runtimeEnvironmentId"] = f"@{runtime_id}"
                        conn_params = connection.setdefault("connParams", {})
                        if isinstance(conn_params, dict):
                            conn_params["agentGroupId"] = runtime_repo_handle
                    content = self._json_bytes(payload)
                rewritten[member] = content

        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
            for member, content in rewritten.items():
                output_zip.writestr(member, content)
        return output.getvalue()

    def _load_reference_dependency_templates(self, package: zipfile.ZipFile, objects: list[dict[str, Any]]) -> list[dict[str, Any]]:
        dependencies = []
        for obj in objects:
            object_type = obj.get("objectType")
            if object_type not in {"Connection", "AgentGroup", "DMAPPLET"}:
                continue
            name = obj.get("objectName", "")
            base_path = obj.get("path", "").strip("/")
            artifact = f"{base_path}/{name}.{object_type}.zip" if base_path else f"{name}.{object_type}.zip"
            if not name or artifact not in package.namelist():
                continue
            metadata = obj.get("metadata", {})
            additional = metadata.get("additionalInfo", {})
            exported_object = json.loads(json.dumps(obj))
            artifact_name = artifact
            dependency_path = obj.get("path", "")
            if object_type == "DMAPPLET":
                dependency_path = f"/Explore/{self.PROJECT_NAME}/{self.folder_name}"
                exported_object["path"] = dependency_path
                artifact_name = f"Explore/{self.PROJECT_NAME}/{self.folder_name}/{name}.DMAPPLET.zip"
            dependencies.append(
                {
                    "id": obj.get("objectGuid", ""),
                    "name": name,
                    "type": object_type,
                    "path": dependency_path,
                    "content_type": additional.get("contentType", "JSON"),
                    "state": additional.get("documentState", "VALID"),
                    "description": additional.get("description"),
                    "artifact_name": artifact_name,
                    "artifact_bytes": package.read(artifact),
                    "exported_object": exported_object,
                }
            )
        return dependencies

    def _write_reference_dependency_artifact(self, dependency: dict[str, Any]) -> None:
        output_path = self.staging_folder / dependency["artifact_name"]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(dependency.get("normalized_artifact_bytes", dependency["artifact_bytes"]))

    def _write_sample_backed_mapping_artifacts(
        self,
        asset: dict[str, Any],
        ids: _AssetIds,
        template: dict[str, Any],
        base_ids: _AssetIds,
        now: datetime,
    ) -> None:
        mapping_folder = self.staging_folder / "Explore" / self.PROJECT_NAME / self.folder_name
        mapping_folder.mkdir(parents=True, exist_ok=True)
        mapping_name = asset["name"]
        replacements = {
            template["name"]: mapping_name,
            template["dtemplate_id"]: ids.dtemplate,
            template["mtt_id"]: ids.mtt,
        }
        for agent_group_id in template.get("agent_group_ids", []):
            if agent_group_id:
                replacements[agent_group_id] = template.get("runtime_environment_id", agent_group_id)
        for connection_id in template.get("connection_ids", []):
            if connection_id:
                replacements[connection_id] = template.get("connection_id", connection_id)

        self._rewrite_sample_zip(
            template["dtemplate_zip"],
            mapping_folder / f"{mapping_name}.DTEMPLATE.zip",
            replacements,
            self._rewrite_dtemplate_member,
            mapping_name,
            ids,
            now,
        )
        self._rewrite_sample_zip(
            template["mtt_zip"],
            mapping_folder / f"{mapping_name}.MTT.zip",
            replacements,
            self._rewrite_mtt_member,
            mapping_name,
            ids,
            now,
        )

    def _rewrite_sample_zip(
        self,
        source_bytes: bytes,
        output_path: Path,
        replacements: dict[str, str],
        member_rewriter,
        mapping_name: str,
        ids: _AssetIds,
        now: datetime,
    ) -> None:
        rewritten: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as source_zip:
            for member in source_zip.namelist():
                rewritten[member] = member_rewriter(
                    member, source_zip.read(member), replacements, mapping_name, ids, now
                )

        if str(output_path).endswith(".DTEMPLATE.zip"):
            rewritten = self._sync_dtemplate_file_records(rewritten, mapping_name, now)

        with zipfile.ZipFile(Path(output_path), "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
            for member, content in rewritten.items():
                output_zip.writestr(member, content)

        if str(output_path).endswith(".DTEMPLATE.zip"):
            self._assert_dtemplate_integrity(Path(output_path), mapping_name)
        elif str(output_path).endswith(".MTT.zip"):
            self._assert_mtt_integrity(Path(output_path), mapping_name, ids)

    @staticmethod
    def _zip_json_member(source_bytes: bytes, member: str) -> Any:
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as source_zip:
            return json.loads(source_zip.read(member).decode("utf-8"))

    def _rewrite_dtemplate_member(
        self,
        member: str,
        content: bytes,
        replacements: dict[str, str],
        mapping_name: str,
        ids: _AssetIds,
        now: datetime,
    ) -> bytes:
        if member == "mappingTemplate.json":
            payload = json.loads(content.decode("utf-8"))
            payload = self._replace_json_strings(payload, replacements)
            if payload:
                payload[0]["name"] = mapping_name
                payload[0]["description"] = f"Sample-backed conversion placeholder for remediated XML : {mapping_name}"
                payload[0]["assetFrsGuid"] = ids.dtemplate
                payload[0]["deployTime"] = self._epoch_millis(now)
            return self._json_bytes(payload)
        if member == "fileRecord.json":
            return content
        if member.startswith("bin/") and member.endswith(".bin"):
            return self._rewrite_imf_bin_member(content, replacements, mapping_name)
        return self._replace_text_bytes(content, replacements)

    def _rewrite_imf_bin_member(
        self,
        content: bytes,
        replacements: dict[str, str],
        mapping_name: str,
    ) -> bytes:
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._replace_text_bytes(content, replacements)

        if not isinstance(payload, dict):
            raise ValueError(f"IMF bin for {mapping_name} must be a JSON object")

        # Preserve IMF class registry. IICS resolves $$class via metadata.$$classInfo;
        # without it import fails with metaClass/ObjectNode null errors.
        class_info = ((payload.get("metadata") or {}) if isinstance(payload.get("metadata"), dict) else {}).get(
            "$$classInfo"
        )
        if not isinstance(class_info, dict) or not class_info:
            raise ValueError(
                f"IMF bin for {mapping_name} is missing metadata.$$classInfo. "
                "Use a real IICS export package as reference_package."
            )

        payload = self._replace_json_strings(payload, replacements)
        if isinstance(payload.get("content"), dict):
            payload["content"]["name"] = mapping_name
        if not isinstance(payload.get("metadata"), dict):
            payload["metadata"] = {"$$classInfo": class_info}
        elif not payload["metadata"].get("$$classInfo"):
            payload["metadata"]["$$classInfo"] = class_info
        return self._json_bytes(payload)

    def _sync_dtemplate_file_records(
        self,
        rewritten: dict[str, bytes],
        mapping_name: str,
        now: datetime,
    ) -> dict[str, bytes]:
        """Keep every fileRecord size/name aligned with its matching bin/*.bin payload.

        IICS IMF import reads `fileRecord.size` bytes from the bin. A stale size after
        name/GUID rewrite produces truncated metadata and `metaClass is null` failures.
        """

        if "fileRecord.json" not in rewritten:
            return rewritten

        payload = json.loads(rewritten["fileRecord.json"].decode("utf-8"))
        if not isinstance(payload, list):
            raise ValueError(f"fileRecord.json must be a list for mapping {mapping_name}")

        bin_members = {
            member: rewritten[member]
            for member in rewritten
            if member.startswith("bin/") and member.endswith(".bin")
        }
        attach_time = self._epoch_millis(now)
        unmatched_records: list[str] = []
        for record in payload:
            record_id = str(record.get("id", "")).lstrip("@")
            bin_member = next(
                (member for member in bin_members if member.endswith(f"/@{record_id}.bin")),
                None,
            )
            if not bin_member:
                unmatched_records.append(str(record.get("id", "")))
                continue
            bin_content = bin_members[bin_member]
            if record.get("type") == "IMFOBJECT":
                record["name"] = mapping_name
            record["size"] = len(bin_content)
            record["attachTime"] = attach_time

        if unmatched_records and not bin_members:
            raise ValueError(
                f"DTEMPLATE for {mapping_name} has fileRecord entries but no bin/*.bin content"
            )
        rewritten["fileRecord.json"] = self._json_bytes(payload)

        if "mappingTemplate.json" in rewritten:
            template = json.loads(rewritten["mappingTemplate.json"].decode("utf-8"))
            if template:
                template_id = str(template[0].get("templateId", "")).lstrip("@")
                record_ids = {str(record.get("id", "")).lstrip("@") for record in payload}
                if template_id and template_id not in record_ids:
                    raise ValueError(
                        f"mappingTemplate.templateId @{template_id} has no matching fileRecord "
                        f"for mapping {mapping_name}"
                    )
        return rewritten

    @staticmethod
    def _assert_dtemplate_integrity(path: Path, mapping_name: str) -> None:
        """Fail fast if a rewritten DTEMPLATE would cause IICS IMF import errors."""

        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            required = {"mappingTemplate.json", "fileRecord.json"}
            missing = required - names
            if missing:
                raise ValueError(f"DTEMPLATE {path.name} missing required members: {sorted(missing)}")

            template = json.loads(zf.read("mappingTemplate.json").decode("utf-8"))
            records = json.loads(zf.read("fileRecord.json").decode("utf-8"))
            if not template or not records:
                raise ValueError(f"DTEMPLATE {path.name} has empty mappingTemplate/fileRecord")

            if template[0].get("name") != mapping_name:
                raise ValueError(
                    f"DTEMPLATE {path.name} mappingTemplate name mismatch: "
                    f"{template[0].get('name')!r} != {mapping_name!r}"
                )
            if template[0].get("assetFrsGuid") in {None, ""}:
                raise ValueError(f"DTEMPLATE {path.name} missing assetFrsGuid")

            bin_members = {
                name: zf.read(name)
                for name in names
                if name.startswith("bin/") and name.endswith(".bin")
            }
            if not bin_members:
                raise ValueError(f"DTEMPLATE {path.name} missing bin/*.bin content")

            for record in records:
                record_id = str(record.get("id", "")).lstrip("@")
                bin_member = next(
                    (name for name in bin_members if name.endswith(f"/@{record_id}.bin")),
                    None,
                )
                if not bin_member:
                    continue
                actual_size = len(bin_members[bin_member])
                declared_size = int(record.get("size") or -1)
                if declared_size != actual_size:
                    raise ValueError(
                        f"DTEMPLATE {path.name} fileRecord size mismatch for {record.get('id')}: "
                        f"declared={declared_size} actual={actual_size}"
                    )
                if record.get("type") == "IMFOBJECT" and record.get("name") != mapping_name:
                    raise ValueError(
                        f"DTEMPLATE {path.name} IMFOBJECT name mismatch: "
                        f"{record.get('name')!r} != {mapping_name!r}"
                    )

                if record.get("type") == "IMFOBJECT":
                    # IMF content must be parseable JSON; truncated/corrupt bins cause metaClass null.
                    try:
                        payload = json.loads(bin_members[bin_member].decode("utf-8"))
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise ValueError(
                            f"DTEMPLATE {path.name} bin {bin_member} is not valid IMF JSON: {exc}"
                        ) from exc
                    content = payload.get("content") if isinstance(payload, dict) else None
                    if not isinstance(content, dict) or content.get("name") != mapping_name:
                        raise ValueError(
                            f"DTEMPLATE {path.name} IMF content.name must equal {mapping_name!r}"
                        )
                    metadata = payload.get("metadata") if isinstance(payload, dict) else None
                    class_info = metadata.get("$$classInfo") if isinstance(metadata, dict) else None
                    if not isinstance(class_info, dict) or not class_info:
                        raise ValueError(
                            f"DTEMPLATE {path.name} IMF bin missing metadata.$$classInfo "
                            "(IICS import will fail with metaClass/ObjectNode null)"
                        )

    @staticmethod
    def _assert_mtt_integrity(path: Path, mapping_name: str, ids: _AssetIds) -> None:
        """Fail fast if rewritten MTT metadata still references the sample template."""

        with zipfile.ZipFile(path) as zf:
            if "mtTask.json" not in zf.namelist():
                raise ValueError(f"MTT {path.name} missing mtTask.json")
            payload = json.loads(zf.read("mtTask.json").decode("utf-8"))
            if not payload:
                raise ValueError(f"MTT {path.name} has empty mtTask.json")
            task = payload[0]
            if task.get("name") != mapping_name:
                raise ValueError(
                    f"MTT {path.name} name mismatch: {task.get('name')!r} != {mapping_name!r}"
                )
            if task.get("frsGuid") != ids.mtt:
                raise ValueError(f"MTT {path.name} frsGuid mismatch")
            if task.get("mappingId") != f"@{ids.dtemplate}":
                raise ValueError(f"MTT {path.name} mappingId mismatch")
            short_description = str(task.get("shortDescription") or "")
            if mapping_name not in short_description and short_description:
                # Truncation may drop the tail of long names; require prefix match.
                expected_prefix = f"Session pushed from PC to ICS : {mapping_name}"[: len(short_description)]
                if short_description != expected_prefix:
                    raise ValueError(
                        f"MTT {path.name} shortDescription still references sample template: "
                        f"{short_description!r}"
                    )

    def _rewrite_mtt_member(
        self,
        member: str,
        content: bytes,
        replacements: dict[str, str],
        mapping_name: str,
        ids: _AssetIds,
        now: datetime,
    ) -> bytes:
        if member == "mtTask.json":
            payload = json.loads(content.decode("utf-8"))
            payload = self._replace_json_strings(payload, replacements)
            if payload:
                payload[0]["name"] = mapping_name
                payload[0]["description"] = f"Sample-backed mapping task wrapper for remediated XML : {mapping_name}"
                payload[0]["shortDescription"] = f"Session pushed from PC to ICS : {mapping_name}"[:60]
                payload[0]["mappingId"] = f"@{ids.dtemplate}"
                payload[0]["frsGuid"] = ids.mtt
                payload[0].setdefault("paramFileType", "PARAM_FILE_LOCAL")
                payload[0].setdefault("serverlessProperties", {})
            return self._json_bytes(payload)
        return self._replace_text_bytes(content, replacements)

    def _workflow_taskflow_xml(
        self,
        taskflow_name: str,
        taskflow_id: str,
        assets: list[dict[str, Any]],
        templates: list[dict[str, Any]],
        now: datetime,
        workflow_templates: list[dict[str, Any]] | None = None,
    ) -> str:
        workflow_templates = workflow_templates or next(
            (template.get("workflow_templates", []) for template in templates if template.get("workflow_templates")),
            [],
        )
        if not workflow_templates or not templates:
            fallback_ids = self._asset_ids(taskflow_name)
            fallback_ids = _AssetIds(
                project=fallback_ids.project,
                folder=fallback_ids.folder,
                connection=fallback_ids.connection,
                agent_group=fallback_ids.agent_group,
                dtemplate=fallback_ids.dtemplate,
                mtt=fallback_ids.mtt,
                taskflow=taskflow_id,
            )
            return self._taskflow_xml(taskflow_name, fallback_ids, now)

        # Prefer an exact workflow template match; otherwise clone a single-service
        # reference taskflow and rewrite it for the migrated asset names/GUIDs.
        template = next(
            (candidate for candidate in workflow_templates if candidate.get("name") == taskflow_name),
            None,
        )
        if template is None:
            template = self._select_rewriteable_workflow_template(workflow_templates, len(assets))

        entry_id = f"{taskflow_id}-gt-{self._epoch_millis(now)}::tf.xml"
        replacements: dict[str, str] = {
            template.get("taskflow_id", ""): taskflow_id,
            template.get("repo_handle", "") or "": entry_id,
        }
        self._add_asset_name_replacements(replacements, template.get("name", ""), taskflow_name)
        template_by_name = {item.get("name", ""): item for item in templates}
        service_titles = set(re.findall(r"<service\b[\s\S]*?<title>(.*?)</title>", template["taskflow_xml"]))
        retained_service_titles = {asset["name"] for asset in assets}

        # Map each retained service title from the reference taskflow onto our assets.
        # For renamed assets, replace the primary reference service with the first asset.
        primary_asset = assets[0]
        primary_template = self._template_for_asset(templates, primary_asset["name"], 0)
        primary_ids: _AssetIds = primary_asset["ids"]
        if service_titles:
            primary_service = next(
                (title for title in sorted(service_titles) if title == primary_template.get("name")),
                sorted(service_titles)[0],
            )
            self._add_asset_name_replacements(replacements, primary_service, primary_asset["name"])
            self._add_asset_name_replacements(
                replacements, primary_template.get("name", ""), primary_asset["name"]
            )
            replacements.update(
                {
                    primary_template.get("dtemplate_id", ""): primary_ids.dtemplate,
                    primary_template.get("mtt_id", ""): primary_ids.mtt,
                }
            )
            # Also replace MTT GUID constants that still point at the selected service template.
            service_template = template_by_name.get(primary_service) or primary_template
            replacements.update(
                {
                    service_template.get("dtemplate_id", ""): primary_ids.dtemplate,
                    service_template.get("mtt_id", ""): primary_ids.mtt,
                }
            )
            self._add_asset_name_replacements(
                replacements, service_template.get("name", ""), primary_asset["name"]
            )
            retained_service_titles = {primary_asset["name"]}

        # Force-map every GUID parameter from the cloned reference taskflow onto our assets.
        # Sample-backed renames often keep the source MTT GUID unless we rewrite it explicitly.
        template_guids = re.findall(
            r'<parameter\s+name="GUID"\s+source="constant"\s+updatable="true">([^<]+)</parameter>',
            template["taskflow_xml"],
        )
        if len(assets) == 1:
            for old_guid in template_guids:
                if old_guid:
                    replacements[old_guid] = primary_ids.mtt
        else:
            for index, old_guid in enumerate(template_guids):
                if not old_guid:
                    continue
                asset = assets[min(index, len(assets) - 1)]
                replacements[old_guid] = asset["ids"].mtt

        for index, asset in enumerate(assets[1:], start=1):
            asset_template = self._template_for_asset(templates, asset["name"], index)
            asset_ids: _AssetIds = asset["ids"]
            self._add_asset_name_replacements(
                replacements, asset_template.get("name", ""), asset["name"]
            )
            replacements.update(
                {
                    asset_template.get("dtemplate_id", ""): asset_ids.dtemplate,
                    asset_template.get("mtt_id", ""): asset_ids.mtt,
                }
            )
            retained_service_titles.add(asset["name"])

        for service_title in sorted(service_titles):
            if service_title in retained_service_titles:
                continue
            helper_template = template_by_name.get(service_title)
            if not helper_template and service_title.endswith("_HR"):
                helper_template = template_by_name.get(service_title.removesuffix("_HR"))
            if not helper_template:
                continue
            helper_ids = self._asset_ids(helper_template.get("name", service_title))
            replacements.update(
                {
                    helper_template.get("dtemplate_id", ""): helper_ids.dtemplate,
                    helper_template.get("mtt_id", ""): helper_ids.mtt,
                }
            )
            retained_service_titles.add(service_title)

        taskflow_text = self._replace_text(template["taskflow_xml"], replacements)
        taskflow_text = re.sub(r"<types1:EntryId>.*?</types1:EntryId>", f"<types1:EntryId>{entry_id}</types1:EntryId>", taskflow_text, count=1)
        taskflow_text = re.sub(r'<taskflow([^>]*?)GUID="[^"]+"', f'<taskflow\\1GUID="{taskflow_id}"', taskflow_text, count=1)
        taskflow_text = re.sub(r"<types1:Name>.*?</types1:Name>", f"<types1:Name>{escape(taskflow_name)}</types1:Name>", taskflow_text, count=1)
        taskflow_text = re.sub(r'displayName="[^"]+"', f'displayName="{escape(taskflow_name)}"', taskflow_text, count=1)
        taskflow_text = re.sub(
            r"(<taskflow\b[^>]*\bname=\")[^\"]+(\")",
            rf"\g<1>{escape(taskflow_name)}\2",
            taskflow_text,
            count=1,
        )
        taskflow_text = re.sub(
            r"<types1:PublishedContributionId>.*?</types1:PublishedContributionId>",
            f"<types1:PublishedContributionId>project:/tf.{escape(taskflow_name)}/{escape(taskflow_name)}.tf.xml</types1:PublishedContributionId>",
            taskflow_text,
            count=1,
        )
        taskflow_text = self._disable_inout_parameter_mapping(taskflow_text, retained_service_titles)
        taskflow_text = self._prune_unpublished_taskflow_services(taskflow_text, retained_service_titles)
        taskflow_text = self._prune_unexpected_process_objects(taskflow_text, retained_service_titles)
        if len(assets) == 1:
            taskflow_text = self._linearize_single_service_taskflow(taskflow_text, primary_asset["name"])
        taskflow_text = self._rewrite_taskflow_guid_parameters(taskflow_text, assets)
        expected_mtt_ids = {asset["ids"].mtt for asset in assets}
        actual_guids = set(
            re.findall(
                r'<parameter[^>]*name="GUID"[^>]*>([^<]+)</parameter>',
                taskflow_text,
            )
        )
        actual_guids = {guid.strip() for guid in actual_guids}
        if not actual_guids or not actual_guids.issubset(expected_mtt_ids):
            raise ValueError(
                f"Rewritten taskflow {taskflow_name} GUID refs {sorted(actual_guids)} "
                f"do not match asset MTT ids {sorted(expected_mtt_ids)}"
            )
        if "<service" not in taskflow_text:
            raise ValueError(f"Rewritten taskflow {taskflow_name} is missing MTT service references")
        self._assert_taskflow_process_objects(taskflow_text, taskflow_name, retained_service_titles)
        return taskflow_text

    @staticmethod
    def _process_object_name(name: str) -> str:
        """IICS Process Object names use hyphens where asset names use underscores."""

        return name.replace("_", "-")

    @classmethod
    def _add_asset_name_replacements(
        cls,
        replacements: dict[str, str],
        old_name: str,
        new_name: str,
    ) -> None:
        """Map both underscore asset names and hyphenated Process Object aliases."""

        if not old_name or not new_name:
            return
        replacements[old_name] = new_name
        replacements[cls._process_object_name(old_name)] = cls._process_object_name(new_name)

    @classmethod
    def _assert_taskflow_process_objects(
        cls,
        taskflow_text: str,
        taskflow_name: str,
        retained_service_titles: set[str],
    ) -> None:
        """Ensure rewritten taskflows never keep the reference Process Object identity."""

        expected = {cls._process_object_name(name) for name in retained_service_titles}
        po_names = set(re.findall(r"<processObject\b[^>]*\bname=\"([^\"]+)\"", taskflow_text))
        po_refs = set(re.findall(r'referenceTo">\$po:([^<]+)', taskflow_text))
        unexpected = (po_names | po_refs) - expected
        if unexpected:
            raise ValueError(
                f"Rewritten taskflow {taskflow_name} still references Process Objects "
                f"{sorted(unexpected)}; expected {sorted(expected)}"
            )

    @classmethod
    def _prune_unexpected_process_objects(
        cls,
        taskflow_text: str,
        retained_service_titles: set[str],
    ) -> str:
        """Remove Process Object declarations and temp fields left by unused reference services."""

        expected = {cls._process_object_name(name) for name in retained_service_titles}
        po_refs = set(re.findall(r'referenceTo">\$po:([^<]+)', taskflow_text))
        po_names = set(re.findall(r"<processObject\b[^>]*\bname=\"([^\"]+)\"", taskflow_text))

        for po_name in sorted((po_refs | po_names) - expected, key=len, reverse=True):
            escaped = re.escape(po_name)
            taskflow_text = re.sub(
                rf'\s*<field\b(?=[^>]*\btype="reference")(?:(?!</field>)[\s\S])*?<option\s+name="referenceTo">\$po:{escaped}</option>(?:(?!</field>)[\s\S])*?</field>',
                "",
                taskflow_text,
            )
            taskflow_text = re.sub(
                rf'\s*<eventContainer\b(?:(?!</eventContainer>)[\s\S])*?\bto="{escaped}(?:/[^"]*)?"(?:(?!</eventContainer>)[\s\S])*?</eventContainer>',
                "",
                taskflow_text,
            )
            taskflow_text = re.sub(
                rf'\s*<processObject\b(?=[^>]*\bname="{escaped}")[\s\S]*?</processObject>',
                "",
                taskflow_text,
            )

        return taskflow_text

    @staticmethod
    def _linearize_single_service_taskflow(taskflow_text: str, service_name: str) -> str:
        """Remove leftover reference branch containers from a one-session taskflow."""

        end_match = re.search(r"<end\b[^>]*\bid=\"([^\"]+)\"", taskflow_text)
        if not end_match:
            return taskflow_text
        end_id = end_match.group(1)

        service_title = re.escape(service_name)
        container_pattern = re.compile(
            rf'(?P<block><eventContainer\b[^>]*>(?:(?!</eventContainer>)[\s\S])*?<title>{service_title}</title>(?:(?!</eventContainer>)[\s\S])*?</eventContainer>)'
        )
        match = container_pattern.search(taskflow_text)
        if not match:
            return taskflow_text

        block = re.sub(
            r'(<link\b[^>]*\btargetId=")[^"]+(")',
            rf"\g<1>{end_id}\2",
            match.group("block"),
            count=1,
        )
        taskflow_text = taskflow_text[: match.start()] + block + taskflow_text[match.end() :]
        return re.sub(
            r'\s*<container\b(?=[^>]*\btype="exclusive")[\s\S]*?</container>',
            "",
            taskflow_text,
        )

    @staticmethod
    def _rewrite_taskflow_guid_parameters(taskflow_text: str, assets: list[dict[str, Any]]) -> str:
        """Replace every MTT GUID parameter with the migrated asset MTT ids."""

        asset_mtt_ids = [asset["ids"].mtt for asset in assets if asset.get("ids")]
        if not asset_mtt_ids:
            return taskflow_text

        counter = {"index": 0}

        def replace_guid(match: re.Match[str]) -> str:
            idx = min(counter["index"], len(asset_mtt_ids) - 1)
            counter["index"] += 1
            return f"{match.group(1)}{asset_mtt_ids[idx]}{match.group(3)}"

        return re.sub(
            r'(<parameter[^>]*name="GUID"[^>]*>)([^<]+)(</parameter>)',
            replace_guid,
            taskflow_text,
        )

    @staticmethod
    def _select_rewriteable_workflow_template(
        workflow_templates: list[dict[str, Any]],
        asset_count: int,
    ) -> dict[str, Any]:
        """Pick a reference taskflow that can be safely rewritten for migrated assets."""

        scored: list[tuple[int, dict[str, Any]]] = []
        for candidate in workflow_templates:
            xml = candidate.get("taskflow_xml", "")
            service_count = len(re.findall(r"<service\b", xml))
            if service_count == 0:
                continue
            # Prefer templates whose service count matches the asset group size.
            score = abs(service_count - max(1, asset_count))
            scored.append((score, candidate))
        if not scored:
            return workflow_templates[0]
        scored.sort(key=lambda item: (item[0], item[1].get("name", "")))
        return scored[0][1]

    @staticmethod
    def _taskflow_entry_id_from_text(taskflow_text: str) -> str | None:
        match = re.search(r"<types1:EntryId>(.*?)</types1:EntryId>", taskflow_text)
        return match.group(1) if match else None

    @staticmethod
    def _taskflow_mtt_refs(taskflow_text: str) -> list[str]:
        return re.findall(
            r'<parameter\s+name="GUID"\s+source="constant"\s+updatable="true">([^<]+)</parameter>',
            taskflow_text,
        )

    @staticmethod
    def _ordered_unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                unique.append(value)
        return unique

    def _disable_inout_parameter_mapping(self, taskflow_text: str, service_names: set[str]) -> str:
        def replace_service(match: re.Match) -> str:
            service = match.group(0)
            title_match = re.search(r"<title>(.*?)</title>", service)
            if not title_match or title_match.group(1) not in service_names:
                return service
            service_name = re.escape(title_match.group(1))
            service = re.sub(
                r'(<parameter name="Has Inout Parameters" source="constant" updatable="true">)true(</parameter>)',
                r"\1false\2",
                service,
                count=1,
            )
            return re.sub(
                rf'\s*<operation source="field"\s+to="temp\.{service_name}/inout/[^"]+">[^<]*</operation>',
                "",
                service,
            )

        return re.sub(r'<service id="[^"]+">[\s\S]*?</service>', replace_service, taskflow_text)

    def _prune_unpublished_taskflow_services(self, taskflow_text: str, published_names: set[str]) -> str:
        service_titles = set(re.findall(r"<service\b[\s\S]*?<title>(.*?)</title>", taskflow_text))
        for service_name in sorted(service_titles - published_names):
            taskflow_text = self._remove_temp_field(taskflow_text, service_name)
            taskflow_text = self._remove_linear_service_container(taskflow_text, service_name)
            taskflow_text = taskflow_text.replace(
                f"{{$temp.{service_name}[1]/output[1]/Task_Status}}",
                "{1}",
            )
        return taskflow_text

    @staticmethod
    def _remove_temp_field(taskflow_text: str, field_name: str) -> str:
        pattern = rf'\s*<field description="" name="{re.escape(field_name)}" type="reference">[\s\S]*?</field>'
        return re.sub(pattern, "", taskflow_text, count=1)

    @staticmethod
    def _remove_linear_service_container(taskflow_text: str, service_name: str) -> str:
        title = re.escape(service_name)
        pattern = re.compile(
            rf'(?P<block>\s*<eventContainer id="(?P<id>[^"]+)">[\s\S]*?<title>{title}</title>[\s\S]*?<link id="[^"]+" targetId="(?P<target>[^"]+)"\s*/>[\s\S]*?</eventContainer>)'
        )
        match = pattern.search(taskflow_text)
        if not match:
            return taskflow_text
        taskflow_text = taskflow_text.replace(match.group("block"), "", 1)
        taskflow_text = re.sub(
            rf'(<link id="[^"]+" targetId="){re.escape(match.group("id"))}(")',
            rf'\g<1>{match.group("target")}\2',
            taskflow_text,
            count=1,
        )
        return taskflow_text

    def _write_mapping_artifacts(self, asset: dict[str, Any], ids: _AssetIds, now: datetime) -> None:
        mapping_folder = self.staging_folder / "Explore" / self.PROJECT_NAME / self.folder_name
        mapping_name = asset["name"]
        template_payload = self._template_payload(asset)
        template_bytes = self._json_bytes(template_payload)
        preview_bytes = self._preview_bytes(mapping_name)
        source_xml_bytes = Path(asset["source_xml_path"]).read_bytes()

        self._write_zip(
            mapping_folder / f"{mapping_name}.DTEMPLATE.zip",
            {
                "mappingTemplate.json": self._json_bytes(
                    [
                        {
                            "@type": "mappingTemplate",
                            "id": "@1",
                            "name": mapping_name,
                            "description": f"Remediated PowerCenter XML source for task/conversion : {mapping_name}",
                            "autoExpireObject": False,
                            "bundleVersion": "0",
                            "assetFrsGuid": ids.dtemplate,
                            "templateId": "@3",
                            "remediatedPowerCenterXmlFileRecordId": "@4",
                            "executionStrategy": self.execution_strategy,
                            "nativeCdiMapping": False,
                            "deployTime": self._epoch_millis(now),
                            "hasParameters": True,
                            "valid": True,
                            "fixedConnection": False,
                            "hasParametersDeployed": True,
                            "fixedConnectionDeployed": False,
                            "isSchemaValidationEnabled": False,
                            "tasks": 1,
                            "mappingPreviewFileRecordId": "@2",
                            "documentType": "",
                            "allowMaxFieldLength": False,
                            "specialCharacterSupport": True,
                            "references": [],
                        }
                    ]
                ),
                "fileRecord.json": self._json_bytes(
                    [
                        {
                            "@type": "fileRecord",
                            "id": "@3",
                            "name": mapping_name,
                            "type": "IMFOBJECT",
                            "size": len(template_bytes),
                            "attachTime": self._epoch_millis(now),
                            "additionalInfo": "com.informatica.metadata.template.common.Template",
                        },
                        {
                            "@type": "fileRecord",
                            "id": "@2",
                            "name": f"{mapping_name}_preview.jpeg",
                            "type": "IMAGE",
                            "size": len(preview_bytes),
                            "attachTime": self._epoch_millis(now),
                        },
                        {
                            "@type": "fileRecord",
                            "id": "@4",
                            "name": asset["source_xml"],
                            "type": "POWERCENTER_XML",
                            "size": len(source_xml_bytes),
                            "attachTime": self._epoch_millis(now),
                            "additionalInfo": "Remediated PowerCenter XML. Use as PowerCenter task input, conversion source, or IICS API payload.",
                        },
                    ]
                ),
                "bin/@2.bin": preview_bytes,
                "bin/@3.bin": template_bytes,
                "bin/@4.bin": source_xml_bytes,
                "metadata.meta": self._json_bytes([{"@type": "objectRef", "id": "@1", "type": "mappingTemplate"}]),
            },
        )
        self._write_zip(
            mapping_folder / f"{mapping_name}.MTT.zip",
            {
                "mtTask.json": self._json_bytes([self._mtt_payload(asset, ids)]),
                "metadata.meta": self._json_bytes([{"@type": "objectRef", "id": "@1", "type": "mtTask"}]),
            },
        )
        (mapping_folder / f"{mapping_name}.TASKFLOW.xml").write_text(
            self._taskflow_xml(mapping_name, ids, now),
            encoding="utf-8",
        )

    def _template_payload(self, asset: dict[str, Any]) -> dict[str, Any]:
        mapping: MappingMetadata = asset["mapping"]
        targets: list[TargetMetadata] = asset["targets"]
        return {
            "content": {
                "$$IID": "stringIdentity:@3",
                "$$class": 1,
                "name": asset["name"],
                "description": f"Packaged remediated PowerCenter XML {asset['source_xml']} for task/conversion execution.",
                "sourceXml": asset["source_xml"],
                "sourceXmlFileRecordId": "@4",
                "nativeCdiMapping": False,
                "executionStrategy": self.execution_strategy,
                "supportedExecutionPaths": [
                    "Run as PowerCenter XML task payload",
                    "Convert remediated PowerCenter XML to cloud-native CDI objects",
                    "Deploy remediated PowerCenter XML through IICS APIs",
                ],
                "conversionNote": (
                    "Modified PowerCenter XML cannot be uploaded directly as a native CDI mapping. "
                    "This package preserves the remediated XML and extracted metadata for supported task, conversion, or API workflows."
                ),
                "repository": asset["repository"],
                "folder": asset["folder"],
                "parameters": [
                    {
                        "$$class": 10,
                        "input": "true",
                        "output": "false",
                        "name": "DBConnection_OLAP",
                        "anonymousType": {"$$class": 12, "typeSystem": "Oracle", "connectionType": "Oracle"},
                    }
                ],
                "sources": [to_plain_dict(source) for source in asset["sources"]],
                "targets": [to_plain_dict(target) for target in targets],
                "transformations": [to_plain_dict(transformation) for transformation in mapping.transformations],
                "connectors": [to_plain_dict(connector) for connector in mapping.connectors],
                "instances": [to_plain_dict(instance) for instance in mapping.instances],
                "sqlOverrides": [to_plain_dict(sql_override) for sql_override in mapping.sql_overrides],
            },
            "metadata": {
                "$$classInfo": {
                    "1": "com.informatica.metadata.template.common.Template",
                    "10": "com.informatica.metadata.template.common.param.TmplParam",
                    "12": "com.informatica.metadata.template.common.param.ConnectionParamType",
                }
            },
        }

    def _mtt_payload(self, asset: dict[str, Any], ids: _AssetIds) -> dict[str, Any]:
        mapping: MappingMetadata = asset["mapping"]
        session: SessionMetadata | None = asset["session"]
        target_parameters = [
            {
                "@type": "mtTaskParameter",
                "id": index + 1,
                "name": f"${target.target_name}$",
                "type": "TARGET",
                "label": "DBConnection_OLAP",
                "targetConnectionId": f"@{ids.connection}",
                "targetObject": target.target_name,
                "targetObjectLabel": target.target_name,
                "operationType": "Insert",
                "truncateTarget": False,
                "runtimeParameterData": {
                    "@type": "mtTaskRuntimeParameterData",
                    "isConnectionRuntimeParameter": True,
                    "isObjectRuntimeParameter": False,
                    "connectionParameterName": "DBConnection_OLAP",
                },
            }
            for index, target in enumerate(asset["targets"])
        ]
        return {
            "@type": "mtTask",
            "id": "@1",
            "name": asset["name"],
            "description": f"PowerCenter XML task wrapper for remediated XML : {asset['name']}",
            "autoExpireObject": False,
            "runtimeEnvironmentId": f"@{ids.agent_group}",
            "maxLogs": 10,
            "verbose": False,
            "mappingId": f"@{ids.dtemplate}",
            "frsGuid": ids.mtt,
            "shortDescription": f"PC XML task wrapper : {asset['name']}"[:60],
            "executionStrategy": self.execution_strategy,
            "nativeCdiMapping": False,
            "remediatedPowerCenterXml": {
                "fileName": asset["source_xml"],
                "fileRecordId": "@4",
                "usage": "Use this payload as a PowerCenter XML task input, cloud-native conversion source, or IICS API deployment payload.",
            },
            "sessionPropertiesList": self._session_properties(session),
            "hidden": False,
            "enableCrossSchemaPushdown": False,
            "enableParallelRun": False,
            "paramFileType": "PARAM_FILE_LOCAL",
            "schemaMode": "async",
            "valid": True,
            "schemaValidationErrorCount": -1,
            "taskProperties": [
                {"@type": "taskProperty", "name": "parameterFileDir", "currentValue": "", "type": "STRING", "required": False},
                {"@type": "taskProperty", "name": "parameterFileName", "currentValue": "", "type": "STRING", "required": False},
            ],
            "optimizationPlan": "NONE",
            "parameters": target_parameters,
            "sequences": [],
            "inOutParameters": [],
            "connRuntimeAttrs": [],
            "sourceXml": asset["source_xml"],
            "mappingSummary": {
                "transformationCount": mapping.transformation_count,
                "sourceCount": mapping.source_count,
                "targetCount": mapping.target_count,
            },
        }

    def _session_properties(self, session: SessionMetadata | None) -> list[dict[str, Any]]:
        properties = {
            "Allow Temporary Sequence for Pushdown": "NO",
            "Allow Temporary View for Pushdown": "NO",
            "Data Column Delimiter": "|",
            "DTM buffer size": "24000000",
            "Error Log File Name": "PMError.log",
            "Pushdown Optimization": "None",
        }
        if session:
            properties.update({key: value for key, value in session.attributes.items() if value})
        return [{"name": key, "value": value, "recommended": False} for key, value in properties.items()]

    def _taskflow_xml(self, mapping_name: str, ids: _AssetIds, now: datetime) -> str:
        escaped_name = escape(mapping_name)
        entry_id = f"{ids.taskflow}-gt-{self._epoch_millis(now)}::tf.xml"
        return f'''<aetgt:getResponse xmlns:aetgt="http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd"
                   xmlns:types1="http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd">
   <types1:Item>
      <types1:EntryId>{entry_id}</types1:EntryId>
      <types1:Name>{escaped_name}</types1:Name>
      <types1:MimeType>application/xml+taskflow</types1:MimeType>
      <types1:Description>PowerCenter XML task wrapper for remediated XML. Convert or deploy through supported IICS APIs before native CDI execution.</types1:Description>
      <types1:VersionLabel>1.0</types1:VersionLabel>
      <types1:State>CURRENT</types1:State>
      <types1:CreationDate>{self._timestamp(now)}</types1:CreationDate>
      <types1:PublicationStatus>published</types1:PublicationStatus>
      <types1:PublishedContributionId>project:/tf.{escaped_name}/{escaped_name}.tf.xml</types1:PublishedContributionId>
      <types1:Entry>
         <taskflow xmlns="http://schemas.active-endpoints.com/appmodules/screenflow/2010/10/avosScreenflow.xsd"
                   xmlns:tfm="http://schemas.active-endpoints.com/appmodules/screenflow/2021/04/taskflowModel.xsd"
                   GUID="{ids.taskflow}"
                   displayName="{escaped_name}"
                   name="{escaped_name}"
                   overrideAPIName="false">
            <description>PowerCenter XML task wrapper for remediated XML. This is not a direct native CDI mapping upload.</description>
            <generator>PC2Cloud Workflow Converter v1</generator>
            <input>
               <parameter name="InputMappingTaskParameterFileDir" type="string"/>
               <parameter name="InputMappingTaskParameterFileName" type="string"/>
               <parameter name="InputPowerCenterXmlFileName" type="string"/>
            </input>
            <tempFields>
               <field description="" name="{escaped_name}" type="reference">
                  <options>
                     <option name="referenceTo">$po:{escape(mapping_name.replace("_", "-"))}</option>
                     <option name="required">false</option>
                  </options>
               </field>
            </tempFields>
         </taskflow>
      </types1:Entry>
   </types1:Item>
</aetgt:getResponse>
'''

    def _assert_staging_dtemplate_integrity(self) -> None:
        """Validate every staged DTEMPLATE/MTT before packaging so broken zips never ship."""

        explore_root = self.staging_folder / "Explore" / self.PROJECT_NAME / self.folder_name
        if not explore_root.exists():
            return
        for dtemplate_path in sorted(explore_root.glob("*.DTEMPLATE.zip")):
            mapping_name = dtemplate_path.name.removesuffix(".DTEMPLATE.zip")
            self._assert_dtemplate_integrity(dtemplate_path, mapping_name)
        for mtt_path in sorted(explore_root.glob("*.MTT.zip")):
            mapping_name = mtt_path.name.removesuffix(".MTT.zip")
            with zipfile.ZipFile(mtt_path) as zf:
                payload = json.loads(zf.read("mtTask.json").decode("utf-8"))
            if not payload:
                raise ValueError(f"MTT {mtt_path.name} has empty mtTask.json")
            task = payload[0]
            if task.get("name") != mapping_name:
                raise ValueError(
                    f"MTT {mtt_path.name} name mismatch: {task.get('name')!r} != {mapping_name!r}"
                )
            mapping_id = str(task.get("mappingId") or "")
            if not mapping_id.startswith("@"):
                raise ValueError(f"MTT {mtt_path.name} mappingId must reference a DTEMPLATE GUID")
            short_description = str(task.get("shortDescription") or "")
            if short_description and mapping_name not in short_description:
                expected_prefix = f"Session pushed from PC to ICS : {mapping_name}"[: len(short_description)]
                if short_description != expected_prefix:
                    raise ValueError(
                        f"MTT {mtt_path.name} shortDescription still references sample template: "
                        f"{short_description!r}"
                    )

    def _write_export_metadata(self, exported_objects: list[dict[str, Any]], now: datetime) -> None:
        payload = {
            "name": self.folder_name,
            "sourceOrgId": "combined-local-repair",
            "sourceOrgName": "PC_IICS_MIGRATION",
            "exportedObjects": exported_objects,
        }
        (self.staging_folder / "exportMetadata.v2.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_contents_csv(self, rows: list[dict[str, str]], now: datetime) -> None:
        csv_path = self.staging_folder / f"ContentsofExportPackage_{self.folder_name}.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=["objectPath", "objectName", "objectType", "id"])
            writer.writeheader()
            writer.writerows(rows)

    def _write_checksum(self) -> None:
        rows = [
            "#",
            f"#{datetime.now(timezone.utc).strftime('%a %b %d %H:%M:%S UTC %Y')}",
        ]
        for path in sorted(file for file in self.staging_folder.rglob("*") if file.is_file() and file.name != "exportPackage.chksum"):
            relative_path = path.relative_to(self.staging_folder).as_posix()
            if path.name.startswith("ContentsofExportPackage_") and path.suffix.lower() == ".csv":
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
            rows.append(f"{self._checksum_key(relative_path)}={digest}")
        (self.staging_folder / "exportPackage.chksum").write_text("\n".join(rows) + "\n", encoding="utf-8")

    @staticmethod
    def _checksum_key(relative_path: str) -> str:
        return (
            relative_path.replace("\\", "\\\\")
            .replace(" ", "\\ ")
            .replace(":", "\\:")
            .replace("=", "\\=")
        )

    def _zip_staging_folder(self) -> None:
        self.output_folder.mkdir(parents=True, exist_ok=True)
        if self.package_path.exists():
            try:
                self.package_path.unlink()
            except PermissionError:
                fallback = self.package_path.with_name(
                    f"{self.package_path.stem}_{self._epoch_millis(datetime.now(timezone.utc))}{self.package_path.suffix}"
                )
                self.logger.warning(
                    "Existing IDMC export ZIP is locked. Writing fallback package: %s",
                    fallback,
                )
                self.package_path = fallback
        with zipfile.ZipFile(self.package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for path in sorted(file for file in self.staging_folder.rglob("*") if file.is_file()):
                package.write(path, path.relative_to(self.staging_folder).as_posix())

    def _write_zip(self, path: Path, files: dict[str, bytes]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as artifact:
            for name, content in files.items():
                artifact.writestr(name, content)

    def _exported_object(
        self,
        object_guid: str,
        name: str,
        object_type: str,
        path: str,
        content_type: str,
        document_state: str,
        description: str | None,
        refs: list[str] | None = None,
        model_version: dict[str, int] | None = None,
        repo_handle: str | None = None,
        context_attributes: list[dict[str, str]] | None | object = (),
    ) -> dict[str, Any]:
        if context_attributes == ():
            context_attributes = [] if object_type in {"Project", "Folder"} else [{"name": "id", "value": "@1"}]
        repo_info = None if object_type in {"Project", "Folder"} else {"repoHandle": repo_handle or self._repo_handle(object_guid)}
        return {
            "objectGuid": object_guid,
            "objectName": name,
            "objectType": object_type,
            "path": path,
            "providerName": None,
            "metadata": {
                "modelVersion": model_version or {"major": 0, "minor": 0},
                "repoInfo": repo_info,
                "objectRefs": refs or [],
                "contextAttributes": context_attributes,
                "additionalInfo": {
                    "description": description,
                    "contentType": content_type,
                    "documentState": document_state,
                },
            },
        }

    def _odata_document(
        self,
        document_type: str,
        object_id: str,
        name: str,
        description: str,
        now: datetime,
        subcontainer_count: int,
        parent_info: list[dict[str, str]],
    ) -> dict[str, Any]:
        properties = [
            self._primitive("id", object_id),
            self._primitive("name", name),
            self._primitive("description", description),
            self._primitive("owner", "generated"),
            self._primitive("createdBy", "generated"),
            self._primitive("lastUpdatedBy", "generated"),
            self._primitive("lastAccessedBy", "generated"),
            self._primitive("createdTime", self._timestamp(now)),
            self._primitive("lastUpdatedTime", self._timestamp(now)),
            self._primitive("lastAccessedTime", self._timestamp(now)),
            self._primitive("expiresBy", "2038-01-18T00:00:00.000Z"),
            self._primitive("documentType", document_type),
            self._primitive("contentType", "Binary"),
            self._primitive("documentState", "COMPLETE"),
            self._primitive("aclRule", "org"),
            self._primitive("subcontainerCount", subcontainer_count),
            self._complex_null("customAttributes"),
            self._complex_null("repoInfo"),
            {
                "annotations": [],
                "valueType": "COLLECTION_COMPLEX",
                "value": [
                    {
                        "annotations": [],
                        "baseURI": None,
                        "id": None,
                        "title": None,
                        "associationLinks": [],
                        "navigationLinks": [],
                        "value": [self._primitive(key, value) for key, value in parent.items()],
                        "typeName": None,
                        "navigationBindings": [],
                    }
                    for parent in parent_info
                ],
                "type": None,
                "name": "parentInfo",
                "operations": [],
                "null": False,
                "primitive": False,
                "enum": False,
                "collection": True,
                "geospatial": False,
                "complex": True,
            },
        ]
        return {
            "annotations": [],
            "baseURI": None,
            "id": f"{document_type}s({object_id})",
            "title": None,
            "associationLinks": [],
            "navigationLinks": [],
            "type": f"OData.frs.{document_type}",
            "editLink": None,
            "mediaEditLinks": [],
            "operations": [],
            "properties": properties,
            "mediaContentSource": None,
            "mediaContentType": None,
            "mediaETag": None,
            "etag": None,
            "selfLink": None,
            "mediaEntity": False,
            "navigationBindings": [],
        }

    @staticmethod
    def _primitive(name: str, value: Any) -> dict[str, Any]:
        return {
            "annotations": [],
            "valueType": "PRIMITIVE",
            "value": value,
            "type": None,
            "name": name,
            "operations": [],
            "null": False,
            "primitive": True,
            "enum": False,
            "collection": False,
            "geospatial": False,
            "complex": False,
        }

    @staticmethod
    def _complex_null(name: str) -> dict[str, Any]:
        return {
            "annotations": [],
            "valueType": "COMPLEX",
            "value": None,
            "type": None,
            "name": name,
            "operations": [],
            "null": True,
            "primitive": False,
            "enum": False,
            "collection": False,
            "geospatial": False,
            "complex": True,
        }

    def _base_ids(self) -> _AssetIds:
        return _AssetIds(
            project=self._guid("project", self.PROJECT_NAME),
            folder=self._guid("folder", self.folder_name),
            connection=self._guid("connection", self.CONNECTION_NAME),
            agent_group=self._guid("agent-group", self.AGENT_GROUP_NAME),
            dtemplate="",
            mtt="",
            taskflow="",
        )

    def _asset_ids(self, mapping_name: str) -> _AssetIds:
        base = self._base_ids()
        return _AssetIds(
            project=base.project,
            folder=base.folder,
            connection=base.connection,
            agent_group=base.agent_group,
            dtemplate=self._guid("dtemplate", mapping_name),
            mtt=self._guid("mtt", mapping_name),
            taskflow=self._guid("taskflow", mapping_name),
        )

    @staticmethod
    def _json_bytes(payload: Any) -> bytes:
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _preview_bytes(mapping_name: str) -> bytes:
        return f"Generated preview placeholder for {mapping_name}\n".encode("utf-8")

    def _replace_json_strings(self, value: Any, replacements: dict[str, str]) -> Any:
        if isinstance(value, str):
            return self._replace_text(value, replacements)
        if isinstance(value, list):
            return [self._replace_json_strings(item, replacements) for item in value]
        if isinstance(value, dict):
            return {key: self._replace_json_strings(item, replacements) for key, item in value.items()}
        return value

    @staticmethod
    def _replace_text(value: str, replacements: dict[str, str]) -> str:
        updated = value
        for before, after in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
            if before:
                updated = updated.replace(before, after)
        return updated

    def _replace_text_bytes(self, value: bytes, replacements: dict[str, str]) -> bytes:
        try:
            return self._replace_text(value.decode("utf-8"), replacements).encode("utf-8")
        except UnicodeDecodeError:
            return value

    def _success_workflow_templates(self, asset_count: int) -> list[dict[str, Any]]:
        """Load taskflow XML templates from known-good IICS import packages."""

        profile = "multi_session" if asset_count > 1 else "single_session"
        benchmark = IICSSuccessBenchmark(project_root=self.project_root)
        reference_package = benchmark.reference_package(profile)
        if not reference_package:
            return []

        try:
            with zipfile.ZipFile(reference_package) as package:
                metadata = json.loads(package.read("exportMetadata.v2.json"))
                templates: list[dict[str, Any]] = []
                for taskflow in metadata.get("exportedObjects", []):
                    if taskflow.get("objectType") != "TASKFLOW":
                        continue
                    name = taskflow.get("objectName", "")
                    base_path = taskflow.get("path", "").strip("/")
                    taskflow_xml = f"{base_path}/{name}.TASKFLOW.xml" if base_path else f"{name}.TASKFLOW.xml"
                    if not name or taskflow_xml not in package.namelist():
                        continue
                    templates.append(
                        {
                            "name": name,
                            "taskflow_id": taskflow.get("objectGuid", ""),
                            "taskflow_xml": package.read(taskflow_xml).decode("utf-8"),
                            "repo_handle": (taskflow.get("metadata", {}).get("repoInfo") or {}).get("repoHandle"),
                            "success_profile": profile,
                        }
                    )
                if templates:
                    self.logger.info(
                        "Using %s success reference taskflow template(s) from %s",
                        profile,
                        reference_package.name,
                    )
                return templates
        except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            self.logger.warning("Failed to load %s success taskflow templates: %s", profile, exc)
            return []

    def _default_reference_package(self, reference_package: str | Path | None) -> Path | None:
        candidates = []
        if reference_package:
            candidates.append(self._resolve_path(reference_package))
        candidates.extend(
            [
                self.project_root / "reference_packages/iics_success/single_session/JEG_SIL_WC_PBCS_BUDGET_ACTUALS_F-1784088987453.zip",
                self.project_root / "reference_packages/iics_success/multi_session/TaskFlow_SDE_EmployeeHeadCount_Informatica_ConvTool.zip",
                self.project_root / "reference_export_package.zip",
                Path(r"D:/Downloads/Custom_Project_Export_SelectableAssets.zip"),
                Path(r"D:/Downloads/Custom_SDE_PBCS_Export 1.zip"),
                Path(r"D:/Downloads/Custom_SDE_PBCS_Export.zip"),
                Path("D:/Download/Custom_SDE_PBCS_Export 1.zip"),
                Path("D:/Download/Custom_SDE_PBCS_Export.zip"),
            ]
        )
        for candidate in candidates:
            if not candidate.exists():
                continue
            if self._reference_has_class_info(candidate):
                return candidate
            self.logger.warning(
                "Skipping reference package without IMF $$classInfo: %s",
                candidate,
            )
        return None

    @staticmethod
    def _reference_has_class_info(package_path: Path) -> bool:
        """Accept only reference packages that contain importable IMF class metadata."""

        try:
            with zipfile.ZipFile(package_path) as package:
                for name in package.namelist():
                    if not name.endswith(".DTEMPLATE.zip"):
                        continue
                    with zipfile.ZipFile(io.BytesIO(package.read(name))) as dtemplate:
                        bin_members = [
                            member
                            for member in dtemplate.namelist()
                            if member.startswith("bin/") and member.endswith(".bin")
                        ]
                        for member in bin_members:
                            try:
                                payload = json.loads(dtemplate.read(member).decode("utf-8"))
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                continue
                            class_info = (
                                (payload.get("metadata") or {}).get("$$classInfo")
                                if isinstance(payload, dict)
                                else None
                            )
                            if isinstance(class_info, dict) and class_info:
                                return True
        except (OSError, zipfile.BadZipFile):
            return False
        return False

    def _reference_folder_name(self) -> str | None:
        if not self.reference_package or not self.reference_package.exists():
            return None
        try:
            with zipfile.ZipFile(self.reference_package) as package:
                metadata = json.loads(package.read("exportMetadata.v2.json"))
        except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError):
            return None
        folders = [item for item in metadata.get("exportedObjects", []) if item.get("objectType") == "Folder"]
        return folders[0].get("objectName") if folders else None

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    @staticmethod
    def _epoch_millis(value: datetime) -> int:
        return int(value.timestamp() * 1000)

    @staticmethod
    def _repo_handle(object_guid: str) -> str:
        return hashlib.sha1(object_guid.encode("utf-8")).hexdigest()[:20].upper()

    @staticmethod
    def _guid(*parts: str) -> str:
        digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()
        alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        number = int.from_bytes(digest[:16], "big")
        chars = []
        for _ in range(22):
            number, remainder = divmod(number, len(alphabet))
            chars.append(alphabet[remainder])
        return "".join(chars)

    @staticmethod
    def _asset_name(name: str) -> str:
        return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in (name or "Mapping")).strip("_") or "Mapping"

    @staticmethod
    def _unique_name(name: str, seen: set[str]) -> str:
        if name not in seen:
            return name
        index = 2
        while f"{name}_{index}" in seen:
            index += 1
        return f"{name}_{index}"

    def _xml_files(self) -> list[Path]:
        return sorted({path.resolve() for path in [*self.remediated_folder.glob("*.XML"), *self.remediated_folder.glob("*.xml")]})

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def generate_idmc_export_package(
    config: AppConfig,
    logger,
    remediated_folder: str | Path | None = None,
    output_folder: str | Path | None = None,
    package_name: str = "Custom_Project_Export.zip",
    execution_strategy: str = "POWERCENTER_XML_TASK",
    reference_package: str | Path | None = None,
) -> IdmcExportSummary:
    """Generate a combined IDMC export ZIP package."""

    return IdmcExportPackageGenerator(
        config=config,
        logger=logger,
        remediated_folder=remediated_folder,
        output_folder=output_folder,
        package_name=package_name,
        execution_strategy=execution_strategy,
        reference_package=reference_package,
    ).generate()

