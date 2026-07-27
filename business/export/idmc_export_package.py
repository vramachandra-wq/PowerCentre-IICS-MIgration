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
import struct
import uuid
import zipfile
import zlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from business.iics.iics_package_generator import _build_workflow_taskflow_xml
from business.iics.checksum_utils import build_checksum_file, sha256_hex, validate_zip_checksums
from business.iics.iics_success_benchmark import IICSSuccessBenchmark
from business.iics.dtemplate_class_registry import DtemplateClassRegistry
from business.iics.native_mapping_graph import VISUAL_EDGE_OVERRIDES, graph_from_mapping_element
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

    PROJECT_NAME = "RPA_PC_Modernization"
    FOLDER_NAME = "Custom_SDE_SupplyChain"
    CONNECTION_NAME = "DataWarehouse_PA"
    AGENT_GROUP_NAME = "PC Secure Agent Group"
    PARAMETER_FILE_DIRECTORY = "/JacobsAnalytics/IICS/Data_Integration/Param"
    IMPORT_QUARANTINED_MAPPING_TASKS = {
        "SDE_ORA_EmployeeDimension": (
            "IDMC import raises DMappletSignature.isActive() null while materializing the Mapping Task "
            "when this asset is remapped into Custom_SDE_SupplyChain. The Mapping/DTEMPLATE and dependent "
            "mapplets are still imported; the source XML, graph JSON, and mapping images remain bundled."
        )
    }

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
        self.package_guid_seed = uuid.uuid4().hex
        # Keep the importable IDMC assets reference-backed. Full XML object
        # coverage is bundled as XML/graph/report artifacts because IDMC MTT
        # import rejects cloned full-canvas DTEMPLATE runtime metadata.
        self.materialize_remediated_graph = False
        self.materialize_mtt_runtime_parameters = False
        # The final package should expose the six mapping-layer assets:
        # DTEMPLATE, MTT, and TASKFLOW for each mapping. Keep only the proven
        # foundational import dependencies (connection and runtime). Native
        # reference exports may also contain reusable mapplets and generators,
        # but declaring those in this combined export changes the import count
        # and can cause duplicate/dependency import errors in IDMC.
        self.export_reference_dependencies = True
        self.export_reference_dependency_types = {"Connection", "AgentGroup"}
        self.import_run_suffix = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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
        client_native_sources = self._client_native_sources_for_mappings(mapping_assets)
        if client_native_sources:
            return self._generate_client_native_package(xml_files, mapping_assets, now, client_native_sources)

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
                if self.export_reference_dependencies:
                    for dependency in dependencies:
                        if dependency["type"] not in self.export_reference_dependency_types:
                            continue
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
                for index, asset in enumerate(mapping_assets):
                    asset_ids = self._asset_ids(asset["name"])
                    asset["ids"] = asset_ids
                    template = self._template_for_asset(sample_templates, asset["name"], index)
                    dependency_refs = (
                        self._dependency_refs_for_template(template)
                        if self.export_reference_dependencies
                        else []
                    )
                    self._write_sample_backed_mapping_artifacts(
                        asset,
                        asset_ids,
                        template,
                        ids,
                        now,
                    )
                    object_path = self._asset_object_path()
                    exported_objects.extend(
                        [
                            self._exported_object(
                                asset_ids.dtemplate,
                                asset["name"],
                                "DTEMPLATE",
                                object_path,
                                "JSON",
                                "VALID",
                                template.get("dtemplate_description")
                                or f"Sample-backed CDI conversion placeholder for remediated XML : {asset['name']}",
                                template.get("dtemplate_object_refs", []),
                            ),
                            self._exported_object(
                                asset_ids.mtt,
                                asset["name"],
                                "MTT",
                                object_path,
                                "JSON",
                                "VALID",
                                template.get("mtt_description")
                                or f"Sample-backed mapping task wrapper for remediated XML : {asset['name']}",
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

                for asset in mapping_assets:
                    asset_ids = asset["ids"]
                    taskflow_name = asset["name"]
                    taskflow_id = asset_ids.taskflow
                    entry_id = f"{taskflow_id}-gt-{self._epoch_millis(now)}::tf.xml"
                    taskflow_text = _build_workflow_taskflow_xml(
                        {"workflow_name": taskflow_name},
                        [(taskflow_name, asset_ids.mtt)],
                        taskflow_id,
                        entry_id,
                    )
                    taskflow_refs = self._ordered_unique(
                        [
                            asset_ids.mtt,
                            *self._taskflow_mtt_refs(taskflow_text),
                        ]
                    )
                    mapping_folder = self._mapping_folder()
                    (mapping_folder / f"{taskflow_name}.TASKFLOW.xml").write_text(taskflow_text, encoding="utf-8")
                    object_path = self._asset_object_path()
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
                    object_path = self._asset_object_path()
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
                object_path = self._asset_object_path()
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
        self._write_remediated_xml_sources(xml_files)
        self._write_reference_mapping_images(mapping_assets, now)
        self._write_native_prototype_status()
        self._write_dtemplate_graph_readiness_report(mapping_assets, now)
        self._write_xml_zip_comparison_reports(xml_files, mapping_assets, now)
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

    def _asset_object_path(self) -> str:
        return f"/Explore/{self.PROJECT_NAME}/{self.folder_name}"

    def _mapping_folder(self) -> Path:
        return self.staging_folder / "Explore" / self.PROJECT_NAME / self.folder_name

    def _write_container_artifacts(self, ids: _AssetIds, now: datetime, mapping_count: int) -> None:
        explore = self.staging_folder / "Explore"
        project_folder = explore / self.PROJECT_NAME
        project_folder.mkdir(parents=True, exist_ok=True)
        self._mapping_folder().mkdir(parents=True, exist_ok=True)
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
                        "dtemplate_object_refs": (
                            (dtemplate.get("metadata") or {}).get("objectRefs") or []
                        ),
                        "mtt_object_refs": (
                            (mtt.get("metadata") or {}).get("objectRefs") or []
                        ),
                        "dtemplate_description": (
                            ((dtemplate.get("metadata") or {}).get("additionalInfo") or {}).get("description")
                        ),
                        "mtt_description": (
                            ((mtt.get("metadata") or {}).get("additionalInfo") or {}).get("description")
                        ),
                    }
                )
            return templates

    @staticmethod
    def _template_for_asset(templates: list[dict[str, Any]], asset_name: str, index: int) -> dict[str, Any]:
        return next((template for template in templates if template.get("name") == asset_name), templates[index % len(templates)])

    def _reference_package_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if self.reference_package:
            candidates.append(self.reference_package)
        candidates.extend(
            [
                Path("D:/Download/SIL_EmployeeDimension-1784818567598.zip"),
                Path("D:/Download/SDE_ORA_EmployeeDimension-1784818706860.zip"),
                Path("D:/Download/SDE_EmployeeHeadCount-1784818653833.zip"),
            ]
        )
        candidates.extend(sorted((self.project_root / "reference_packages").rglob("*.zip")))
        seen: set[str] = set()
        result: list[Path] = []
        for candidate in candidates:
            resolved = self._resolve_path(candidate)
            key = str(resolved).lower()
            if key in seen or not resolved.exists():
                continue
            seen.add(key)
            result.append(resolved)
        return result

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
            if dependency["type"] not in self.export_reference_dependency_types:
                continue
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
            if object_type not in {"Connection", "AgentGroup", "DMAPPLET", "SequenceGenerator"}:
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
            if object_type in {"DMAPPLET", "SequenceGenerator"}:
                dependency_path = self._asset_object_path()
                exported_object["path"] = dependency_path
                artifact_name = f"Explore/{self.PROJECT_NAME}/{self.folder_name}/{name}.{object_type}.zip"
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
        mapping_folder = self._mapping_folder()
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
            rewritten = self._ensure_dtemplate_preview(rewritten, mapping_name, now)

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
            if self.materialize_remediated_graph:
                self._apply_remediated_mapping_graph(payload, mapping_name)
        if not isinstance(payload.get("metadata"), dict):
            payload["metadata"] = {"$$classInfo": class_info}
        elif not payload["metadata"].get("$$classInfo"):
            payload["metadata"]["$$classInfo"] = class_info
        return self._json_bytes(payload)

    def _apply_remediated_mapping_graph(self, payload: dict[str, Any], mapping_name: str) -> None:
        """Replace the reference template graph with the remediated XML topology."""

        mapping = self._remediated_mapping_element(mapping_name)
        content = payload.get("content")
        if mapping is None or not isinstance(content, dict):
            return

        prototypes = self._dtemplate_prototypes(content)
        if not prototypes:
            self.logger.warning("No usable DTEMPLATE prototypes found for %s; keeping reference graph.", mapping_name)
            return

        graph = graph_from_mapping_element(mapping, visual_overrides=False)
        nodes = [
            {
                "name": node.name,
                "instance_type": node.kind,
                "transformation_type": node.transformation_type,
            }
            for node in graph.nodes
        ]
        edges = [(edge.from_node, edge.to_node) for edge in graph.component_edges()]
        if not nodes:
            return

        required_types = self._required_native_prototype_types(nodes)
        registry_status = self._dtemplate_class_registry().status(required_types)
        if not registry_status.complete:
            self.logger.warning(
                "Native DTEMPLATE graph for %s requires missing IDMC prototype(s) %s; keeping import-safe reference graph.",
                mapping_name,
                registry_status.missing_types,
            )
            return

        next_id = self._max_dtemplate_id(payload) + 1
        transformations: list[dict[str, Any]] = []
        refs: dict[str, dict[str, int]] = {}

        for node in self._ordered_graph_nodes(nodes, edges):
            prototype = prototypes[self._prototype_kind(node)]
            cloned, id_map, next_id = self._clone_dtemplate_object(prototype, next_id)
            self._rename_dtemplate_node(cloned, node["name"])
            self._sync_dtemplate_node_adapter(cloned, node)
            transformations.append(cloned)
            old_tx_id = int(prototype.get("$$ID", 0))
            old_group_id = self._first_group_id(prototype)
            refs[node["name"]] = {
                "tx_id": id_map.get(old_tx_id, int(cloned.get("$$ID", 0))),
                "group_id": id_map.get(old_group_id, self._first_group_id(cloned)),
                "class": int(cloned.get("$$class", prototype.get("$$class", 7))),
            }

        links = []
        for from_name, to_name in edges:
            if from_name not in refs or to_name not in refs:
                continue
            link_id = next_id
            next_id += 1
            source = refs[from_name]
            target = refs[to_name]
            links.append(
                {
                    "$$ID": link_id,
                    "$$class": 4,
                    "name": f"link_{link_id}",
                    "fromGroup": {"##ID": source["group_id"], "$$class": 5},
                    "fromTransformation": {"##ID": source["tx_id"], "$$class": source["class"]},
                    "toGroup": {"##ID": target["group_id"], "$$class": 5},
                    "toTransformation": {"##ID": target["tx_id"], "$$class": target["class"]},
                }
            )

        content["transformations"] = transformations
        content["links"] = links
        content["nativeCdiMapping"] = True
        content["conversionNote"] = (
            "Native DTEMPLATE graph materialized from PowerCenter XML INSTANCE and CONNECTOR metadata. "
            "All required transformation classes were backed by real IDMC-native class samples."
        )

    def _write_native_prototype_status(self) -> None:
        self._dtemplate_class_registry().write_status_report(self.output_folder / "native_dtemplate_prototype_status.json")

    def _dtemplate_class_registry(self) -> DtemplateClassRegistry:
        source_packages = [
            self.reference_package,
            self.project_root / "reference_export_package.zip",
            *sorted((self.project_root / "reference_packages").rglob("*.zip")),
        ]
        return DtemplateClassRegistry(
            self.project_root / "reference_packages/iics_native_classes",
            source_packages=[path for path in source_packages if path and Path(path).exists()],
        )

    @staticmethod
    def _required_native_prototype_types(nodes: list[dict[str, str]]) -> list[str]:
        required: list[str] = []
        seen: set[str] = set()

        def add(item: str) -> None:
            if item not in seen:
                seen.add(item)
                required.append(item)

        for node in nodes:
            instance_type = node.get("instance_type", "").upper()
            transformation_type = node.get("transformation_type", "").lower()
            name = node.get("name", "").lower()
            if instance_type == "SOURCE":
                add("source")
            elif instance_type == "TARGET":
                add("target")
            elif "source qualifier" in transformation_type or name.startswith("sq_"):
                add("source_qualifier")
            elif (
                "lookup" in transformation_type
                or name.startswith("lkp_")
                or "filter" in transformation_type
                or name.startswith("fil_")
                or "update strategy" in transformation_type
                or name.startswith("upd_")
                or "mapplet" in transformation_type
                or name.startswith("mplt_")
            ):
                add("expression")
            elif "router" in transformation_type:
                add("router")
            elif "joiner" in transformation_type:
                add("joiner")
            elif "aggregator" in transformation_type:
                add("aggregator")
            elif "sequence" in transformation_type:
                add("sequence_generator")
            else:
                add("expression")
        return required

    def _remediated_mapping_element(self, mapping_name: str) -> ET.Element | None:
        for xml_path in self._xml_files():
            try:
                root = ET.parse(xml_path).getroot()
            except ET.ParseError:
                continue
            for mapping in root.iter("MAPPING"):
                if mapping.get("NAME") == mapping_name:
                    return mapping
        return None

    @staticmethod
    def _dtemplate_prototypes(content: dict[str, Any]) -> dict[str, dict[str, Any]]:
        prototypes: dict[str, dict[str, Any]] = {}
        for item in content.get("transformations", []):
            if not isinstance(item, dict):
                continue
            cls = item.get("$$class")
            if cls == 6:
                prototypes.setdefault("source", item)
            elif cls == 8:
                prototypes.setdefault("target", item)
            elif cls == 7:
                prototypes.setdefault("expression", item)
        if "expression" not in prototypes:
            return {}
        prototypes.setdefault("source", prototypes["expression"])
        prototypes.setdefault("target", prototypes["expression"])
        return prototypes

    @staticmethod
    def _native_graph_nodes(mapping: ET.Element) -> list[dict[str, str]]:
        nodes: list[dict[str, str]] = []
        seen: set[str] = set()
        transformations = {
            item.get("NAME", ""): item.get("TYPE", "")
            for item in mapping.findall("TRANSFORMATION")
            if item.get("NAME")
        }
        for instance in mapping.findall("INSTANCE"):
            name = instance.get("NAME", "")
            if not name or name in seen:
                continue
            seen.add(name)
            nodes.append(
                {
                    "name": name,
                    "instance_type": instance.get("TYPE", ""),
                    "transformation_type": instance.get("TRANSFORMATION_TYPE", "")
                    or transformations.get(instance.get("TRANSFORMATION_NAME", ""), ""),
                }
            )
        return nodes

    @staticmethod
    def _native_graph_edges(mapping: ET.Element) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for connector in mapping.findall("CONNECTOR"):
            edge = (connector.get("FROMINSTANCE", ""), connector.get("TOINSTANCE", ""))
            if not edge[0] or not edge[1] or edge in seen:
                continue
            seen.add(edge)
            edges.append(edge)
        return edges

    @staticmethod
    def _prototype_kind(node: dict[str, str]) -> str:
        instance_type = node.get("instance_type", "").upper()
        transformation_type = node.get("transformation_type", "").lower()
        if instance_type == "TARGET":
            return "target"
        if instance_type == "SOURCE" or "source qualifier" in transformation_type:
            return "source"
        return "expression"

    @staticmethod
    def _ordered_graph_nodes(nodes: list[dict[str, str]], edges: list[tuple[str, str]]) -> list[dict[str, str]]:
        by_name = {node["name"]: node for node in nodes}
        incoming = {node["name"]: 0 for node in nodes}
        outgoing: dict[str, list[str]] = {node["name"]: [] for node in nodes}
        for from_name, to_name in edges:
            if from_name in by_name and to_name in by_name:
                outgoing[from_name].append(to_name)
                incoming[to_name] += 1

        order = {node["name"]: index for index, node in enumerate(nodes)}
        queue = sorted([name for name, count in incoming.items() if count == 0], key=lambda name: order[name])
        result: list[dict[str, str]] = []
        while queue:
            name = queue.pop(0)
            result.append(by_name[name])
            for target in sorted(outgoing[name], key=lambda item: order[item]):
                incoming[target] -= 1
                if incoming[target] == 0:
                    queue.append(target)
            queue.sort(key=lambda item: order[item])

        emitted = {node["name"] for node in result}
        result.extend(node for node in nodes if node["name"] not in emitted)
        return result

    @staticmethod
    def _clone_dtemplate_object(prototype: dict[str, Any], next_id: int) -> tuple[dict[str, Any], dict[int, int], int]:
        clone = json.loads(json.dumps(prototype))
        id_map: dict[int, int] = {}

        def collect(value: Any) -> None:
            if isinstance(value, dict):
                current = value.get("$$ID")
                if isinstance(current, int) and current not in id_map:
                    id_map[current] = len(id_map) + next_id
                for item in value.values():
                    collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)

        def rewrite(value: Any) -> None:
            if isinstance(value, dict):
                if isinstance(value.get("$$ID"), int):
                    value["$$ID"] = id_map[value["$$ID"]]
                if isinstance(value.get("##ID"), int) and value["##ID"] in id_map:
                    value["##ID"] = id_map[value["##ID"]]
                for item in value.values():
                    rewrite(item)
            elif isinstance(value, list):
                for item in value:
                    rewrite(item)

        collect(clone)
        rewrite(clone)
        return clone, id_map, next_id + len(id_map)

    @staticmethod
    def _rename_dtemplate_node(node: dict[str, Any], name: str) -> None:
        old_name = str(node.get("name", ""))

        def rewrite(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in list(value.items()):
                    if isinstance(item, str):
                        value[key] = item.replace(old_name, name) if old_name else item
                    else:
                        rewrite(item)
            elif isinstance(value, list):
                for item in value:
                    rewrite(item)

        rewrite(node)
        node["name"] = name

    @staticmethod
    def _sync_dtemplate_node_adapter(node: dict[str, Any], graph_node: dict[str, str]) -> None:
        prototype_kind = IdmcExportPackageGenerator._prototype_kind(graph_node)
        if prototype_kind not in {"source", "target"}:
            return
        data_adapter = node.get("dataAdapter")
        if not isinstance(data_adapter, dict):
            return
        object_name = graph_node.get("name", "")
        if not object_name:
            return
        data_adapter.pop("customQuery", None)
        data_adapter["objectType"] = "SINGLE"
        data_adapter["multipleObject"] = "false"
        data_adapter["useDynamicFileName"] = "false"
        adapter_object = data_adapter.setdefault("object", {})
        if isinstance(adapter_object, dict):
            adapter_object.update(
                {
                    "name": object_name,
                    "label": object_name,
                    "path": object_name,
                    "customQuery": "",
                    "retainMetadata": "false",
                }
            )
            fields = adapter_object.get("fields")
            if isinstance(fields, list):
                for field in fields:
                    if not isinstance(field, dict):
                        continue
                    properties = field.get("properties")
                    if not isinstance(properties, list):
                        continue
                    for prop in properties:
                        if isinstance(prop, dict) and prop.get("name") in {"parentObjectLabel", "parentLabel"}:
                            prop["value"] = object_name

    @staticmethod
    def _first_group_id(node: dict[str, Any]) -> int:
        groups = node.get("groups", [])
        if isinstance(groups, list) and groups and isinstance(groups[0], dict):
            value = groups[0].get("$$ID")
            if isinstance(value, int):
                return value
        return int(node.get("$$ID", 0))

    @staticmethod
    def _max_dtemplate_id(value: Any) -> int:
        max_id = 0
        if isinstance(value, dict):
            for key in ("$$ID", "##ID"):
                current = value.get(key)
                if isinstance(current, int):
                    max_id = max(max_id, current)
            for item in value.values():
                max_id = max(max_id, IdmcExportPackageGenerator._max_dtemplate_id(item))
        elif isinstance(value, list):
            for item in value:
                max_id = max(max_id, IdmcExportPackageGenerator._max_dtemplate_id(item))
        return max_id

    def _ensure_dtemplate_preview(
        self,
        rewritten: dict[str, bytes],
        mapping_name: str,
        now: datetime,
    ) -> dict[str, bytes]:
        preview_bytes = self._mapping_reference_preview_bytes(mapping_name)
        if not preview_bytes:
            return rewritten

        records = []
        if "fileRecord.json" in rewritten:
            loaded = json.loads(rewritten["fileRecord.json"].decode("utf-8"))
            records = loaded if isinstance(loaded, list) else []
        preview_record = next((record for record in records if record.get("type") == "IMAGE"), None)
        used_ids = {str(record.get("id", "")).lstrip("@") for record in records if record.get("id")}
        if preview_record and preview_record.get("id"):
            preview_id = str(preview_record["id"])
        else:
            next_id = 2
            while str(next_id) in used_ids:
                next_id += 1
            preview_id = f"@{next_id}"
        rewritten[f"bin/{preview_id}.bin"] = preview_bytes

        if "mappingTemplate.json" in rewritten:
            payload = json.loads(rewritten["mappingTemplate.json"].decode("utf-8"))
            if isinstance(payload, list) and payload:
                payload[0]["mappingPreviewFileRecordId"] = preview_id
            rewritten["mappingTemplate.json"] = self._json_bytes(payload)

        records = [record for record in records if record.get("id") != preview_id]
        records.append(
            {
                "@type": "fileRecord",
                "id": preview_id,
                "name": f"{mapping_name}_preview.png" if preview_bytes.startswith(b"\x89PNG\r\n\x1a\n") else f"{mapping_name}_preview.jpeg",
                "type": "IMAGE",
                "size": len(preview_bytes),
                "attachTime": self._epoch_millis(now),
                **(
                    {"additionalInfo": "image/png", "mimeType": "image/png", "contentType": "image/png"}
                    if preview_bytes.startswith(b"\x89PNG\r\n\x1a\n")
                    else {}
                ),
            }
        )
        rewritten["fileRecord.json"] = self._json_bytes(records)
        return rewritten

    def _mapping_reference_preview_bytes(self, mapping_name: str) -> bytes:
        image_folder = self.output_folder / "downloadable_mapping_images_from_zip"
        candidates = [
            image_folder / f"{mapping_name}_full_transformations.jpeg",
            image_folder / f"{mapping_name}_full_transformations.jpg",
            image_folder / f"{mapping_name}_full_transformations.png",
            image_folder / f"{mapping_name}_valid_mapping.jpeg",
            image_folder / f"{mapping_name}_valid_mapping.jpg",
            image_folder / f"{mapping_name}_valid_mapping.png",
            image_folder / f"{mapping_name}.png",
        ]
        if mapping_name == "SDE_ORA_JobDimension":
            candidates.extend(
                [
                    Path(r"C:/Users/rkumar/AppData/Local/Temp/codex-clipboard-74ea2b1c-fa00-49c7-a1a0-26c11b314f22.png"),
                    Path(r"C:/Users/rkumar/AppData/Local/Temp/codex-clipboard-25d375d9-8feb-4639-b577-ddff9484e1c6.png"),
                    Path(r"C:/Users/rkumar/AppData/Local/Temp/codex-clipboard-7369a6b5-19b1-48c2-bda3-ad2c02cef370.png"),
                ]
            )
        elif mapping_name == "SIL_JobDimension":
            candidates.extend(
                [
                    Path(r"C:/Users/rkumar/AppData/Local/Temp/codex-clipboard-7582a6ad-e168-432b-8c24-1363467a395f.png"),
                    Path(r"C:/Users/rkumar/AppData/Local/Temp/codex-clipboard-945abbde-376a-46f3-982c-bfc9bf80cb3a.png"),
                    Path(r"C:/Users/rkumar/AppData/Local/Temp/codex-clipboard-a3a05abf-f5b2-49a7-a1bf-15cf73355e6f.png"),
                ]
            )
        pinned_preview = self._pinned_mapping_preview_bytes(mapping_name)
        if pinned_preview and self._is_preview_image(pinned_preview):
            return pinned_preview
        previews: list[bytes] = []
        for candidate in candidates:
            if candidate.exists():
                data = candidate.read_bytes()
                if self._is_preview_image(data):
                    previews.append(data)
        exact_native_preview = self._exact_native_package_preview_bytes(mapping_name)
        if exact_native_preview and self._is_preview_image(exact_native_preview):
            return exact_native_preview
        reference_preview = self._reference_package_preview_bytes(mapping_name)
        if reference_preview and self._is_preview_image(reference_preview):
            previews.append(reference_preview)
        if previews:
            return max(previews, key=len)
        return self._preview_bytes(mapping_name)

    def _pinned_mapping_preview_bytes(self, mapping_name: str) -> bytes | None:
        pinned_images = {
            "SDE_ORA_JobDimension": self.project_root / "reference_packages" / "mapping_images" / "SDE_ORA_JobDimension_preview.png",
        }
        pinned_path = pinned_images.get(mapping_name)
        if pinned_path and pinned_path.exists():
            return pinned_path.read_bytes()
        return None

    @staticmethod
    def _is_preview_image(value: bytes) -> bool:
        return value.startswith(b"\x89PNG\r\n\x1a\n") or value.startswith(b"\xff\xd8")

    def _exact_native_package_preview_bytes(self, mapping_name: str) -> bytes | None:
        for package_path in self._client_native_source_candidates():
            if mapping_name.lower() not in package_path.stem.lower():
                continue
            names = self._native_package_mapping_names(package_path)
            if names != {mapping_name}:
                continue
            preview = self._preview_from_native_package(package_path, mapping_name)
            if preview:
                return preview
        return None

    def _preview_from_native_package(self, package_path: Path, mapping_name: str) -> bytes | None:
        try:
            with zipfile.ZipFile(package_path) as package:
                for member in package.namelist():
                    if not member.endswith(f"/{mapping_name}.DTEMPLATE.zip"):
                        continue
                    with zipfile.ZipFile(io.BytesIO(package.read(member))) as template_zip:
                        embedded = self._template_zip_image_bytes(template_zip)
                        if embedded:
                            return embedded
                        for bin_member in template_zip.namelist():
                            if not (bin_member.startswith("bin/") and bin_member.endswith(".bin")):
                                continue
                            try:
                                payload = json.loads(template_zip.read(bin_member).decode("utf-8-sig"))
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                continue
                            rendered = self._render_native_dtemplate_preview(payload, mapping_name)
                            if rendered:
                                return rendered
        except (OSError, zipfile.BadZipFile, KeyError) as exc:
            self.logger.warning("Failed to render native preview for %s from %s: %s", mapping_name, package_path, exc)
        return None

    def _template_zip_image_bytes(self, template_zip: zipfile.ZipFile) -> bytes | None:
        if "fileRecord.json" not in template_zip.namelist():
            return None
        try:
            records = json.loads(template_zip.read("fileRecord.json").decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        for record in records if isinstance(records, list) else []:
            if record.get("type") != "IMAGE":
                continue
            record_id = str(record.get("id", "")).lstrip("@")
            bin_member = f"bin/@{record_id}.bin"
            if bin_member in template_zip.namelist():
                data = template_zip.read(bin_member)
                if self._is_preview_image(data):
                    return data
        return None

    def _render_native_dtemplate_preview(self, payload: dict[str, Any], mapping_name: str) -> bytes | None:
        content = payload.get("content") if isinstance(payload, dict) else None
        if not isinstance(content, dict):
            return None
        transformations = [item for item in content.get("transformations", []) if isinstance(item, dict) and item.get("name")]
        links = [item for item in content.get("links", []) if isinstance(item, dict)]
        if not transformations:
            return None
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return None
        tx_by_id = {int(item.get("$$ID")): item for item in transformations if isinstance(item.get("$$ID"), int)}
        edges: list[tuple[str, str]] = []
        for link in links:
            source_id = ((link.get("fromTransformation") or {}).get("##ID"))
            target_id = ((link.get("toTransformation") or {}).get("##ID"))
            source = tx_by_id.get(source_id, {}).get("name")
            target = tx_by_id.get(target_id, {}).get("name")
            if source and target and (source, target) not in edges:
                edges.append((source, target))
        names = [item["name"] for item in transformations]
        layers = self._graph_layers(names, edges)
        max_layer = max(layers.values(), default=0)
        max_per_layer = max((sum(1 for value in layers.values() if value == layer) for layer in set(layers.values())), default=1)
        width = max(1280, 230 * (max_layer + 1) + 180)
        height = max(560, 95 * max_per_layer + 180)
        image = Image.new("RGB", (width, height), (248, 250, 252))
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        draw.text((28, 24), mapping_name, fill=(17, 24, 39), font=font)
        by_layer: dict[int, list[str]] = {}
        for name in names:
            by_layer.setdefault(layers.get(name, 0), []).append(name)
        positions: dict[str, tuple[int, int, int, int]] = {}
        box_w, box_h = 165, 54
        for layer in sorted(by_layer):
            layer_names = by_layer[layer]
            x = 70 + layer * 230
            total_h = len(layer_names) * box_h + (len(layer_names) - 1) * 38
            start_y = max(90, (height - total_h) // 2)
            for index, name in enumerate(layer_names):
                y = start_y + index * (box_h + 38)
                positions[name] = (x, y, x + box_w, y + box_h)
        for source, target in edges:
            if source not in positions or target not in positions:
                continue
            sx1, sy1, sx2, sy2 = positions[source]
            tx1, ty1, tx2, ty2 = positions[target]
            start = (sx2, (sy1 + sy2) // 2)
            end = (tx1, (ty1 + ty2) // 2)
            mid_x = (start[0] + end[0]) // 2
            draw.line([start, (mid_x, start[1]), (mid_x, end[1]), end], fill=(102, 102, 102), width=2)
            draw.polygon([(end[0], end[1]), (end[0] - 8, end[1] - 5), (end[0] - 8, end[1] + 5)], fill=(102, 102, 102))
        for item in transformations:
            name = item["name"]
            x1, y1, x2, y2 = positions[name]
            cls = item.get("$$class")
            fill = (207, 231, 248) if cls == 6 else (220, 236, 252) if cls == 7 else (201, 229, 246)
            draw.rounded_rectangle((x1, y1, x2, y2), radius=5, fill=fill, outline=(142, 202, 239), width=2)
            draw.ellipse((x1 + 10, y1 + 19, x1 + 22, y1 + 31), fill=(122, 77, 157) if cls == 7 else (68, 114, 148))
            ty = y1 + 8
            for label_line in self._wrap_label(name, 18):
                draw.text((x1 + 30, ty), label_line, fill=(31, 41, 55), font=font)
                ty += 13
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    @staticmethod
    def _wrap_label(value: str, width: int) -> list[str]:
        parts = value.replace("_", " _").split()
        lines: list[str] = []
        current = ""
        for part in parts:
            candidate = f"{current}{part}" if part.startswith("_") else f"{current} {part}".strip()
            if len(candidate) <= width:
                current = candidate
            else:
                if current:
                    lines.append(current[:width])
                current = part.lstrip("_")[:width]
        if current:
            lines.append(current[:width])
        return lines[:3]

    @staticmethod
    def _graph_layers(names: list[str], edges: list[tuple[str, str]]) -> dict[str, int]:
        incoming = {name: 0 for name in names}
        outgoing = {name: [] for name in names}
        for source, target in edges:
            if source in incoming and target in incoming:
                outgoing[source].append(target)
                incoming[target] += 1
        layers = {name: 0 for name, count in incoming.items() if count == 0}
        queue = list(layers)
        while queue:
            source = queue.pop(0)
            for target in outgoing[source]:
                next_layer = layers[source] + 1
                if next_layer > layers.get(target, -1):
                    layers[target] = next_layer
                    queue.append(target)
        for name in names:
            layers.setdefault(name, 0)
        return layers

    def _reference_package_preview_bytes(self, mapping_name: str) -> bytes | None:
        previews: list[bytes] = []
        packages = self._client_native_source_candidates()
        if self.reference_package and self.reference_package.exists():
            packages.insert(0, self.reference_package)
        try:
            for package_path in self._ordered_unique_paths(packages):
                with zipfile.ZipFile(package_path) as package:
                    for member in package.namelist():
                        if f"{mapping_name}_" in member and member.lower().endswith((".png", ".jpg", ".jpeg")):
                            data = package.read(member)
                            if self._is_preview_image(data):
                                previews.append(data)
                    for member in package.namelist():
                        if not member.endswith(f"/{mapping_name}.DTEMPLATE.zip"):
                            continue
                        with zipfile.ZipFile(io.BytesIO(package.read(member))) as template_zip:
                            if "fileRecord.json" not in template_zip.namelist():
                                continue
                            records = json.loads(template_zip.read("fileRecord.json").decode("utf-8"))
                            for record in records if isinstance(records, list) else []:
                                if record.get("type") != "IMAGE":
                                    continue
                                record_id = str(record.get("id", "")).lstrip("@")
                                bin_member = f"bin/@{record_id}.bin"
                                if bin_member in template_zip.namelist():
                                    data = template_zip.read(bin_member)
                                    if self._is_preview_image(data):
                                        previews.append(data)
        except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError) as exc:
            self.logger.warning("Failed to load reference preview for %s: %s", mapping_name, exc)
        return max(previews, key=len) if previews else None
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
                self._apply_parameter_file_fields(payload[0], mapping_name)
                self._apply_empty_inout_parameters(payload[0])
                if self.materialize_remediated_graph and self.materialize_mtt_runtime_parameters:
                    self._apply_mapping_runtime_parameters(payload[0], mapping_name, ids)
            return self._json_bytes(payload)
        return self._replace_text_bytes(content, replacements)

    def _apply_parameter_file_fields(self, task: dict[str, Any], mapping_name: str) -> None:
        task["paramFileType"] = "PARAM_FILE_LOCAL"
        task_properties = task.setdefault("taskProperties", [])
        if not isinstance(task_properties, list):
            task_properties = []
            task["taskProperties"] = task_properties
        by_name = {item.get("name"): item for item in task_properties if isinstance(item, dict)}
        values = {
            "parameterFileDir": "",
            "parameterFileName": "",
        }
        labels = {
            "parameterFileDir": "label.parameterFileDir",
            "parameterFileName": "label.parameterFileName",
        }
        for name, value in values.items():
            item = by_name.get(name)
            if item is None:
                item = {"@type": "taskProperty", "name": name}
                task_properties.append(item)
            item.update({"currentValue": value, "type": "STRING", "label": labels[name], "required": False})

    @staticmethod
    def _apply_empty_inout_parameters(task: dict[str, Any]) -> None:
        task["inOutParameters"] = [{"@type": "mtTaskInOutParameter", "name": "", "type": "", "value": ""}]

    def _apply_mapping_runtime_parameters(self, task: dict[str, Any], mapping_name: str, ids: _AssetIds) -> None:
        specs = self._mapping_runtime_parameter_specs(mapping_name)
        if not specs:
            return
        existing = [item for item in task.get("parameters", []) if isinstance(item, dict)]
        source_proto = next((item for item in existing if item.get("type") == "EXTENDED_SOURCE"), None)
        if source_proto is None:
            source_proto = next((item for item in existing if item.get("type") == "SOURCE"), None)
        target_proto = next((item for item in existing if item.get("type") == "TARGET"), None)
        start_id = max([int(item.get("id", 0)) for item in existing if isinstance(item.get("id"), int)] or [1000]) + 1
        parameters = []
        for offset, spec in enumerate(specs):
            prototype = source_proto if spec["type"] == "EXTENDED_SOURCE" else target_proto
            parameter = json.loads(json.dumps(prototype or {"@type": "mtTaskParameter"}))
            parameter.update(
                {
                    "@type": "mtTaskParameter",
                    "id": start_id + offset,
                    "name": f"${spec['name']}$",
                    "type": spec["type"],
                    "label": spec["name"],
                    "newFlatFile": False,
                    "newObject": False,
                    "showBusinessNames": True,
                    "naturalOrder": True,
                    "truncateTarget": False,
                    "bulkApiDBTarget": False,
                }
            )
            connection_parameter_name = "Source" if spec["type"] == "EXTENDED_SOURCE" else "Target"
            ui_properties = parameter.setdefault("uiProperties", {})
            if not isinstance(ui_properties, dict):
                ui_properties = {}
                parameter["uiProperties"] = ui_properties
            ui_properties.update(
                {
                    "cnxtype": "Oracle",
                    "connectionParameterized": "true",
                    "paramName": connection_parameter_name,
                    "paramType-mapping": "Connection",
                    "logcnx": connection_parameter_name,
                    "objectParameterized": "false",
                    "visible": "false",
                    "flags": "SUPPORTS_MULTI_SCHEMA",
                    "originalPath": spec["name"],
                }
            )
            if spec["type"] == "EXTENDED_SOURCE":
                parameter["sourceConnectionId"] = f"@{ids.connection}"
                parameter["runtimeAttrs"] = {}
                parameter["customQuery"] = ""
                parameter["extendedObject"] = {
                    "@type": "extendedObject",
                    "object": {
                        "@type": "mObject",
                        "name": spec["name"],
                        "label": spec["name"],
                        "metadataUpdated": False,
                        "dbSchema": "",
                        "relations": [],
                        "children": [],
                    },
                    "singleMode": True,
                    "objects": [
                        {
                            "@type": "mObject",
                            "name": spec["name"],
                            "label": spec["name"],
                            "metadataUpdated": False,
                            "dbSchema": "",
                            "relations": [],
                            "children": [],
                        }
                    ],
                    "filters": [],
                    "sortFields": [],
                }
                parameter.pop("targetConnectionId", None)
                parameter.pop("targetObject", None)
                parameter.pop("targetObjectLabel", None)
                parameter.pop("operationType", None)
                parameter.pop("sourceObject", None)
                parameter.pop("objectName", None)
                parameter.pop("objectLabel", None)
            else:
                parameter["targetConnectionId"] = f"@{ids.connection}"
                parameter["targetObject"] = spec["name"]
                parameter["targetObjectLabel"] = spec["name"]
                parameter["objectName"] = spec["name"]
                parameter["objectLabel"] = spec["name"]
                parameter.setdefault("operationType", "Insert")
                parameter.pop("sourceConnectionId", None)
                parameter.pop("sourceObject", None)
                parameter.pop("customQuery", None)
                parameter["runtimeAttrs"] = {"INSERT": "YES"}
                ui_properties["default"] = spec["name"]
            parameter["runtimeParameterData"] = {
                "@type": "mtTaskRuntimeParameterData",
                "isConnectionRuntimeParameter": True,
                "isObjectRuntimeParameter": False,
                "connectionParameterName": connection_parameter_name,
            }
            parameters.append(parameter)
        task["parameters"] = parameters

    def _mapping_runtime_parameter_specs(self, mapping_name: str) -> list[dict[str, str]]:
        mapping = self._remediated_mapping_element(mapping_name)
        if mapping is None:
            return []
        if self.materialize_remediated_graph and mapping_name in VISUAL_EDGE_OVERRIDES:
            graph = graph_from_mapping_element(mapping, visual_overrides=False)
            specs: list[dict[str, str]] = []
            seen: set[tuple[str, str]] = set()
            for node in graph.nodes:
                graph_node = {
                    "name": node.name,
                    "instance_type": node.kind,
                    "transformation_type": node.transformation_type,
                }
                prototype_kind = self._prototype_kind(graph_node)
                if prototype_kind not in {"source", "target"}:
                    continue
                param_type = "EXTENDED_SOURCE" if prototype_kind == "source" else "TARGET"
                key = (node.name, param_type)
                if key not in seen:
                    seen.add(key)
                    specs.append({"name": node.name, "type": param_type})
            return specs
        specs: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        def add(name: str, param_type: str) -> None:
            key = (name, param_type)
            if name and key not in seen:
                seen.add(key)
                specs.append({"name": name, "type": param_type})

        for instance in mapping.findall("INSTANCE"):
            instance_type = (instance.get("TYPE") or "").upper()
            if instance_type == "SOURCE":
                add(instance.get("NAME", ""), "EXTENDED_SOURCE")
            elif instance_type == "TARGET":
                add(instance.get("NAME", ""), "TARGET")
        for connector in mapping.findall("CONNECTOR"):
            if connector.get("FROMINSTANCETYPE") == "Source Definition":
                add(connector.get("FROMINSTANCE", ""), "EXTENDED_SOURCE")
            if connector.get("TOINSTANCETYPE") == "Target Definition":
                add(connector.get("TOINSTANCE", ""), "TARGET")
        return specs

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
        mapping_folder = self._mapping_folder()
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

        explore_root = self._mapping_folder()
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

    def _write_xml_zip_comparison_reports(
        self,
        xml_files: list[Path],
        mapping_assets: list[dict[str, Any]],
        now: datetime,
    ) -> None:
        report_folder = self.staging_folder / "ValidationReports"
        report_folder.mkdir(parents=True, exist_ok=True)
        input_by_mapping = self._xml_mapping_summaries(self.project_root / "input_xml")
        remediated_by_mapping = self._xml_mapping_summaries(self.remediated_folder)
        zip_by_mapping = self._staged_dtemplate_summaries(mapping_assets)
        rows = []
        for asset in mapping_assets:
            name = asset["name"]
            input_summary = input_by_mapping.get(name, {})
            remediated_summary = remediated_by_mapping.get(name, {})
            zip_summary = zip_by_mapping.get(name, {})
            rows.append(
                {
                    "mapping": name,
                    "inputXmlFile": input_summary.get("file", ""),
                    "remediatedXmlFile": remediated_summary.get("file", ""),
                    "inputInstances": input_summary.get("instances", 0),
                    "remediatedInstances": remediated_summary.get("instances", 0),
                    "zipImportableTransformations": zip_summary.get("transformations", 0),
                    "inputTransformations": input_summary.get("transformations", 0),
                    "remediatedTransformations": remediated_summary.get("transformations", 0),
                    "inputConnectors": input_summary.get("connectors", 0),
                    "remediatedConnectors": remediated_summary.get("connectors", 0),
                    "zipImportableLinks": zip_summary.get("links", 0),
                    "inputInstanceNames": input_summary.get("instanceNames", []),
                    "remediatedInstanceNames": remediated_summary.get("instanceNames", []),
                    "zipImportableTransformationNames": zip_summary.get("transformationNames", []),
                    "status": (
                        "IMPORT_COMPATIBLE_WITH_XML_SOURCE_BUNDLED"
                        if zip_summary.get("transformations", 0) > 0
                        else "MISSING_IMPORTABLE_DTEMPLATE"
                    ),
                    "note": (
                        "Input XML and remediated XML are preserved in SourceXML and validation reports. "
                        "The importable DTEMPLATE uses IDMC-supported template metadata; "
                        "full PowerCenter instance coverage is documented by XML source records and MappingImages."
                    ),
                }
            )
        report = {
            "generatedAt": self._timestamp(now),
            "packageName": self.package_name,
            "project": self.PROJECT_NAME,
            "folder": self.folder_name,
            "sourceXmlFiles": [path.name for path in xml_files],
            "mappings": rows,
        }
        (report_folder / "xml_zip_mapping_comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        with (report_folder / "xml_zip_mapping_comparison.csv").open("w", newline="", encoding="utf-8") as csv_file:
            fieldnames = [
                "mapping",
                "inputXmlFile",
                "remediatedXmlFile",
                "inputInstances",
                "remediatedInstances",
                "zipImportableTransformations",
                "inputTransformations",
                "remediatedTransformations",
                "inputConnectors",
                "remediatedConnectors",
                "zipImportableLinks",
                "status",
            ]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row[key] for key in fieldnames})

    def _write_reference_mapping_images(self, mapping_assets: list[dict[str, Any]], now: datetime) -> None:
        source_folder = self.output_folder / "downloadable_mapping_images_from_zip"
        image_folder = self.staging_folder / "MappingImages"
        image_folder.mkdir(parents=True, exist_ok=True)
        index = {
            "description": (
                "IDMC mapping and taskflow reference images bundled with this package. "
                "DTEMPLATE preview records use the full-transformation mapping images where available."
            ),
            "generatedAt": self._timestamp(now),
            "images": [],
        }
        candidates = [
            ("Custom_SDE_SupplyChain", "taskflow_reference", "Custom_SDE_SupplyChain_taskflow_reference.png"),
        ]
        for asset in mapping_assets:
            name = asset["name"]
            candidates.extend(
                [
                    (name, "valid_mapping", f"{name}_valid_mapping.png"),
                    (name, "full_transformations", f"{name}_full_transformations.png"),
                ]
            )
            mapping = self._remediated_mapping_element(name)
            if mapping is not None:
                graph = graph_from_mapping_element(mapping, visual_overrides=True)
                graph_bytes = self._json_bytes(graph.to_dict())
                for kind in ["valid_mapping", "full_transformations"]:
                    graph_file_name = f"{name}_{kind}.graph.json"
                    (image_folder / graph_file_name).write_bytes(graph_bytes)
                    index["images"].append(
                        {
                            "mappingName": name,
                            "kind": f"{kind}_graph",
                            "fileName": graph_file_name,
                            "zipPath": f"MappingImages/{graph_file_name}",
                            "format": "json",
                            "sizeBytes": len(graph_bytes),
                            "sha256": hashlib.sha256(graph_bytes).hexdigest().upper(),
                        }
                    )
        for mapping_name, kind, file_name in candidates:
            source = source_folder / file_name
            if not source.exists():
                continue
            data = source.read_bytes()
            (image_folder / file_name).write_bytes(data)
            index["images"].append(
                {
                    "mappingName": mapping_name,
                    "kind": kind,
                    "fileName": file_name,
                    "zipPath": f"MappingImages/{file_name}",
                    "format": "png",
                    "sizeBytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest().upper(),
                }
            )
            graph_source = source.with_suffix(".graph.json")
            if graph_source.exists() and not (image_folder / graph_source.name).exists():
                graph_file_name = graph_source.name
                graph_data = graph_source.read_bytes()
                (image_folder / graph_file_name).write_bytes(graph_data)
                index["images"].append(
                    {
                        "mappingName": mapping_name,
                        "kind": f"{kind}_graph",
                        "fileName": graph_file_name,
                        "zipPath": f"MappingImages/{graph_file_name}",
                        "format": "json",
                        "sizeBytes": len(graph_data),
                        "sha256": hashlib.sha256(graph_data).hexdigest().upper(),
                    }
                )
        (image_folder / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    def _write_remediated_xml_sources(self, xml_files: list[Path]) -> None:
        source_folder = self.staging_folder / "SourceXML"
        source_folder.mkdir(parents=True, exist_ok=True)
        index = {"description": "PowerCenter XML mappings preserved for full object coverage.", "files": []}
        for path in xml_files:
            data = path.read_bytes()
            target = source_folder / path.name
            target.write_bytes(data)
            index["files"].append(
                {
                    "fileName": path.name,
                    "zipPath": f"SourceXML/{path.name}",
                    "sizeBytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest().upper(),
                }
            )
        (source_folder / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    def _write_dtemplate_graph_readiness_report(self, mapping_assets: list[dict[str, Any]], now: datetime) -> None:
        report_folder = self.staging_folder / "ValidationReports"
        report_folder.mkdir(parents=True, exist_ok=True)
        registry = self._dtemplate_class_registry()
        mappings: list[dict[str, Any]] = []
        for asset in mapping_assets:
            name = asset["name"]
            mapping = self._remediated_mapping_element(name)
            if mapping is None:
                continue
            graph = graph_from_mapping_element(mapping, visual_overrides=False)
            nodes = [
                {
                    "name": node.name,
                    "instanceType": node.kind,
                    "transformationType": node.transformation_type,
                }
                for node in graph.nodes
            ]
            required_types = self._required_native_prototype_types(
                [
                    {
                        "name": node["name"],
                        "instance_type": node["instanceType"],
                        "transformation_type": node["transformationType"],
                    }
                    for node in nodes
                ]
            )
            status = registry.status(required_types)
            component_edges = graph.component_edges()
            mappings.append(
                {
                    "mapping": name,
                    "nativeDtemplateInjectionEnabled": self.materialize_remediated_graph and status.complete,
                    "reason": (
                        "All required native DTEMPLATE prototypes are available."
                        if status.complete
                        else "Full DTEMPLATE graph injection is gated to preserve IDMC import compatibility."
                    ),
                    "requiredPrototypeTypes": required_types,
                    "missingPrototypeTypes": status.missing_types,
                    "availablePrototypeTypes": [
                        item.transformation_type for item in status.prototypes if item.available
                    ],
                    "nodeCount": len(graph.nodes),
                    "componentLinkCount": len(component_edges),
                    "fieldConnectorCount": len(graph.edges),
                    "portCount": len(graph.ports),
                    "nodes": nodes,
                    "componentLinks": [
                        {"fromNode": edge.from_node, "toNode": edge.to_node} for edge in component_edges
                    ],
                }
            )
        report = {
            "generatedAt": self._timestamp(now),
            "packageName": self.package_name,
            "importCompatibilityPolicy": (
                "Preserve the known IDMC-importable DTEMPLATE/MTT/TASKFLOW shape unless every required "
                "native transformation prototype is available from real IDMC exports."
            ),
            "mappings": mappings,
        }
        (report_folder / "dtemplate_native_graph_readiness.json").write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

    def _xml_mapping_summaries(self, folder: Path) -> dict[str, dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        if not folder.exists():
            return summaries
        for path in sorted([*folder.glob("*.XML"), *folder.glob("*.xml")]):
            try:
                root = ET.parse(path).getroot()
            except ET.ParseError:
                continue
            for mapping in root.iter("MAPPING"):
                name = mapping.get("NAME", "")
                if not name:
                    continue
                summaries[name] = {
                    "file": path.name,
                    "instances": len(mapping.findall("INSTANCE")),
                    "transformations": len(mapping.findall("TRANSFORMATION")),
                    "connectors": len(mapping.findall("CONNECTOR")),
                    "instanceNames": [item.get("NAME", "") for item in mapping.findall("INSTANCE")],
                    "transformationNames": [item.get("NAME", "") for item in mapping.findall("TRANSFORMATION")],
                }
        return summaries

    def _staged_dtemplate_summaries(self, mapping_assets: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        mapping_folder = self._mapping_folder()
        for asset in mapping_assets:
            name = asset["name"]
            path = mapping_folder / f"{name}.DTEMPLATE.zip"
            if not path.exists():
                summaries[name] = {}
                continue
            try:
                with zipfile.ZipFile(path) as dtemplate:
                    payload = None
                    for member in dtemplate.namelist():
                        if not member.startswith("bin/") or not member.endswith(".bin"):
                            continue
                        try:
                            candidate = json.loads(dtemplate.read(member).decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            continue
                        if isinstance(candidate, dict) and isinstance(candidate.get("content"), dict):
                            payload = candidate
                            break
                    if payload is None:
                        raise ValueError("No JSON IMFOBJECT bin found")
            except (OSError, zipfile.BadZipFile, ValueError):
                summaries[name] = {}
                continue
            content = payload.get("content", {}) if isinstance(payload, dict) else {}
            transformations = content.get("transformations", []) if isinstance(content, dict) else []
            links = content.get("links", []) if isinstance(content, dict) else []
            summaries[name] = {
                "transformations": len(transformations) if isinstance(transformations, list) else 0,
                "links": len(links) if isinstance(links, list) else 0,
                "transformationNames": [
                    item.get("name", "")
                    for item in transformations
                    if isinstance(item, dict)
                ]
                if isinstance(transformations, list)
                else [],
            }
        return summaries

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
        width, height = 1000, 380
        bg = (248, 250, 252)
        line = (94, 84, 142)
        fill = (210, 232, 248)
        border = (162, 209, 239)
        text = (31, 41, 55)
        pixels = bytearray()
        canvas = [[bg for _ in range(width)] for _ in range(height)]

        def rect(x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int]) -> None:
            for y in range(max(0, y1), min(height, y2)):
                row = canvas[y]
                for x in range(max(0, x1), min(width, x2)):
                    row[x] = color

        def border_rect(x1: int, y1: int, x2: int, y2: int) -> None:
            rect(x1, y1, x2, y2, fill)
            rect(x1, y1, x2, y1 + 3, border)
            rect(x1, y2 - 3, x2, y2, border)
            rect(x1, y1, x1 + 3, y2, border)
            rect(x2 - 3, y1, x2, y2, border)

        def connector(x1: int, y1: int, x2: int, y2: int) -> None:
            if x1 > x2:
                x1, x2 = x2, x1
                y1, y2 = y2, y1
            steps = max(abs(x2 - x1), abs(y2 - y1), 1)
            for i in range(steps + 1):
                x = int(x1 + (x2 - x1) * i / steps)
                y = int(y1 + (y2 - y1) * i / steps)
                rect(x - 1, y - 1, x + 2, y + 2, line)

        node_count = 7 if mapping_name == "SDE_ORA_JobDimension" else 11
        gap = max(80, (width - 160) // max(node_count, 1))
        centers = []
        for index in range(node_count):
            x = 40 + index * gap
            y = 145 if index % 2 == 0 else 215
            centers.append((x + 55, y + 24))
            border_rect(x, y, x + 110, y + 48)
            # tiny dark glyphs give the generated preview a visible label rhythm
            for dot in range(min(10, len(mapping_name))):
                rect(x + 10 + dot * 7, y + 14, x + 14 + dot * 7, y + 18, text)
        for (x1, y1), (x2, y2) in zip(centers, centers[1:]):
            connector(x1 + 55, y1, x2 - 55, y2)

        for row in canvas:
            pixels.append(0)
            for red, green, blue in row:
                pixels.extend([red, green, blue])

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        raw = bytes(pixels)
        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(raw, 9))
        png += chunk(b"IEND", b"")
        return png

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

    def _client_native_source_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if self.reference_package:
            candidates.append(self.reference_package)
        for folder in [Path("D:/Downloads"), Path("D:/Download")]:
            if folder.exists():
                candidates.extend(sorted(folder.glob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True))
        reference_root = self.project_root / "reference_packages"
        if reference_root.exists():
            candidates.extend(sorted(reference_root.rglob("*.zip"), key=lambda item: item.stat().st_mtime, reverse=True))
        seen: set[str] = set()
        result: list[Path] = []
        for candidate in candidates:
            resolved = self._resolve_path(candidate)
            key = str(resolved).lower()
            if key in seen or not resolved.exists() or resolved == self.package_path:
                continue
            if not self._is_trusted_client_native_source(resolved):
                continue
            seen.add(key)
            result.append(resolved)
        return result

    @staticmethod
    def _is_trusted_client_native_source(source: Path) -> bool:
        try:
            with zipfile.ZipFile(source) as package:
                if "exportMetadata.v2.json" not in package.namelist():
                    return False
                metadata = json.loads(package.read("exportMetadata.v2.json").decode("utf-8"))
        except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        source_org_id = str(metadata.get("sourceOrgId", "")).strip().lower()
        source_org_name = str(metadata.get("sourceOrgName", "")).strip().lower()
        if source_org_id in {"generated", "client-native-remapped"}:
            return False
        if source_org_name in {"pc_iics_migration", ""}:
            return False
        return True

    @staticmethod
    def _ordered_unique_paths(paths: list[Path]) -> list[Path]:
        seen: set[str] = set()
        result: list[Path] = []
        for path in paths:
            key = str(path).lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(path)
        return result

    @staticmethod
    def _native_package_mapping_names(source: Path) -> set[str]:
        try:
            with zipfile.ZipFile(source) as package:
                if "exportMetadata.v2.json" not in package.namelist():
                    return set()
                metadata = json.loads(package.read("exportMetadata.v2.json").decode("utf-8"))
        except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError):
            return set()
        names: set[str] = set()
        for obj in metadata.get("exportedObjects", []):
            if obj.get("objectType") in {"DTEMPLATE", "MTT", "TASKFLOW"} and obj.get("objectName"):
                names.add(obj["objectName"])
        return names

    @staticmethod
    def _native_package_mapping_types(source: Path) -> dict[str, set[str]]:
        try:
            with zipfile.ZipFile(source) as package:
                if "exportMetadata.v2.json" not in package.namelist():
                    return {}
                metadata = json.loads(package.read("exportMetadata.v2.json").decode("utf-8"))
        except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        mapping_types: dict[str, set[str]] = {}
        for obj in metadata.get("exportedObjects", []):
            if obj.get("objectType") in {"DTEMPLATE", "MTT", "TASKFLOW"} and obj.get("objectName"):
                mapping_types.setdefault(obj["objectName"], set()).add(obj["objectType"])
        return mapping_types

    def _client_native_sources_for_mappings(self, mapping_assets: list[dict[str, Any]]) -> list[Path]:
        required = {asset.get("name") for asset in mapping_assets if asset.get("name")}
        if not required:
            return []
        workflow_required = {
            self._asset_name(str(asset.get("workflow_name", "")))
            for asset in mapping_assets
            if asset.get("workflow_name")
        }
        source_required = required | workflow_required
        coverage_by_source: list[tuple[Path, set[str]]] = []
        for source in self._client_native_source_candidates():
            coverage = self._native_package_mapping_names(source) & source_required
            if coverage:
                coverage_by_source.append((source, coverage))
        selected: list[Path] = []
        covered: set[str] = set()
        for mapping_name in sorted(source_required):
            exact_candidates = [
                source
                for source, coverage in coverage_by_source
                if coverage == {mapping_name} and mapping_name.lower() in source.stem.lower()
                and {"DTEMPLATE", "MTT"} <= self._native_package_mapping_types(source).get(mapping_name, set())
            ]
            if exact_candidates:
                chosen = sorted(exact_candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]
                selected.append(chosen)
                covered.add(mapping_name)
        for source, coverage in sorted(coverage_by_source, key=lambda item: (-len(item[1] - covered), str(item[0]).lower())):
            if coverage <= covered:
                continue
            selected.append(source)
            covered.update(coverage)
            if covered == source_required:
                break
        selected = self._ordered_unique_paths(selected)
        if not selected:
            self.logger.info(
                "No complete native IDMC source export set found for mappings %s. Missing native exports for: %s",
                sorted(required),
                sorted(required),
            )
            return []
        if not required <= covered:
            self.logger.warning(
                "Using partial native IDMC source export coverage. Missing importable native mapping exports for: %s",
                sorted(required - covered),
            )
        self.logger.info(
            "Using dynamic native IDMC source exports for mappings %s: %s",
            sorted(required),
            [str(path) for path in selected],
        )
        return selected

    @staticmethod
    def _client_native_remap_context(metadata: dict[str, Any], mapping_names: set[str]) -> tuple[set[str], set[str]]:
        projects: set[str] = set()
        folders: set[str] = set()
        for obj in metadata.get("exportedObjects", []):
            object_type = obj.get("objectType")
            object_name = obj.get("objectName", "")
            path = str(obj.get("path", ""))
            if object_type == "Project" and object_name:
                projects.add(object_name)
            parts = [part for part in path.strip("/").split("/") if part]
            if len(parts) >= 2 and parts[0] == "Explore":
                projects.add(parts[1])
            if object_type == "Folder" and object_name:
                folders.add(object_name)
            if object_name in mapping_names and len(parts) >= 3 and parts[0] == "Explore":
                folders.add(parts[2])
            if object_type in {"DTEMPLATE", "MTT", "TASKFLOW", "DMAPPLET", "SequenceGenerator"} and len(parts) >= 3 and parts[0] == "Explore":
                folders.add(parts[2])
        return projects, folders

    def _generate_client_native_package(
        self,
        xml_files: list[Path],
        mapping_assets: list[dict[str, Any]],
        now: datetime,
        native_sources: list[Path],
    ) -> IdmcExportSummary:
        """Build the package from discovered client-tested native IDMC exports.

        Native exports are discovered by inspecting exportMetadata.v2.json and
        matching DTEMPLATE/MTT/TASKFLOW object names to the current XML mappings.
        This keeps package creation dynamic while preserving IDMC-generated
        DTEMPLATE internals instead of handcrafting bin/@2.bin.
        """

        entries: dict[str, bytes] = {}
        exported_objects: list[dict[str, Any]] = []
        seen_guids: set[str] = set()
        project_object: dict[str, Any] | None = None
        folder_object: dict[str, Any] | None = None
        mapping_names = {asset["name"] for asset in mapping_assets}
        workflow_names = {
            self._asset_name(str(asset.get("workflow_name", "")))
            for asset in mapping_assets
            if asset.get("workflow_name")
        }
        folder_token = "__IDMC_TARGET_FOLDER__"

        for source in native_sources:
            with zipfile.ZipFile(source) as package:
                metadata = json.loads(package.read("exportMetadata.v2.json").decode("utf-8"))
                allowed_guids = self._client_native_allowed_object_guids(metadata, mapping_names, workflow_names)
                old_projects, old_folders = self._client_native_remap_context(metadata, mapping_names)
                replacements = {project: self.PROJECT_NAME for project in old_projects}
                replacements.update({folder: folder_token for folder in old_folders})
                allowed_members = {
                    self._remap_client_native_member(
                        self._client_native_member_for_object(obj),
                        old_projects,
                        old_folders,
                    )
                    for obj in metadata.get("exportedObjects", [])
                    if obj.get("objectGuid") in allowed_guids or obj.get("objectType") in {"Project", "Folder"}
                }
                for obj in metadata.get("exportedObjects", []):
                    obj = json.loads(json.dumps(obj))
                    object_type = obj.get("objectType")
                    if object_type == "Project":
                        if project_object is None:
                            obj["objectName"] = self.PROJECT_NAME
                            obj["path"] = "/Explore"
                            project_object = self._replace_client_native_json(obj, replacements, folder_token)
                        continue
                    if object_type == "Folder":
                        if folder_object is None:
                            obj["objectName"] = self.folder_name
                            obj["path"] = f"/Explore/{self.PROJECT_NAME}"
                            folder_object = self._replace_client_native_json(obj, replacements, folder_token)
                        continue
                    if obj.get("objectGuid") not in allowed_guids:
                        continue
                    if self._is_import_quarantined_object(obj):
                        continue
                    obj["path"] = self._remap_client_native_path(str(obj.get("path", "")), old_projects, old_folders)
                    obj = self._replace_client_native_json(obj, replacements, folder_token)
                    guid = obj.get("objectGuid") or f"{obj.get('objectType')}|{obj.get('path')}|{obj.get('objectName')}"
                    if guid in seen_guids:
                        continue
                    seen_guids.add(guid)
                    exported_objects.append(obj)

                for member in package.namelist():
                    if (
                        member.endswith("/")
                        or member in {"exportMetadata.v2.json", "exportPackage.chksum"}
                        or member.startswith("ContentsofExportPackage_")
                    ):
                        continue
                    target_member = self._remap_client_native_member(member, old_projects, old_folders)
                    if target_member not in allowed_members:
                        continue
                    if self._is_import_quarantined_member(target_member):
                        continue
                    content = package.read(member)
                    if member.endswith(".zip"):
                        mapping_name = Path(target_member).name.split(".")[0]
                        content = self._rewrite_client_native_nested_zip(
                            content,
                            target_member,
                            mapping_name,
                            replacements,
                            folder_token,
                            now,
                        )
                    else:
                        content = self._replace_client_native_bytes(content, replacements, folder_token)
                    entries.setdefault(target_member, content)

        ordered_objects = []
        if project_object:
            ordered_objects.append(project_object)
        if folder_object:
            ordered_objects.append(folder_object)
        exported_objects = ordered_objects + exported_objects
        exported_objects, deduped_guid_map = self._dedupe_exported_objects_by_import_name(exported_objects)
        exported_objects, quarantine_guid_map = self._remove_refs_to_import_quarantined_tasks(exported_objects)
        deduped_guid_map.update(quarantine_guid_map)
        if deduped_guid_map:
            entries = self._replace_removed_duplicate_guids(entries, deduped_guid_map)

        self._add_client_native_support_artifacts(entries, xml_files, mapping_assets, now)
        self._add_client_native_reference_analysis_artifact(entries, mapping_assets, native_sources, now)
        entries["exportMetadata.v2.json"] = self._json_bytes(
            {
                "name": self.package_name.removesuffix(".zip"),
                **self._client_native_source_org(native_sources),
                "exportedObjects": exported_objects,
            }
        )
        entries[f"ContentsofExportPackage_{self.folder_name}.csv"] = self._contents_csv_bytes(exported_objects)
        checksums = {
            name: sha256_hex(content)
            for name, content in entries.items()
            if not name.startswith("ContentsofExportPackage_")
        }
        entries["exportPackage.chksum"] = build_checksum_file(checksums)
        self._write_entries_zip(entries)
        ok, errors = validate_zip_checksums(self.package_path)
        if not ok:
            raise RuntimeError(f"Generated native package failed checksum validation: {errors[0]}")

        return IdmcExportSummary(
            input_xml_count=len(xml_files),
            mapping_count=len(mapping_assets),
            artifact_count=len(exported_objects),
            package_path=str(self.package_path),
            staging_folder=str(self.staging_folder),
        )

    def _is_import_quarantined_object(self, obj: dict[str, Any]) -> bool:
        return (
            obj.get("objectName") in self.IMPORT_QUARANTINED_MAPPING_TASKS
            and obj.get("objectType") in {"MTT", "TASKFLOW"}
        )

    def _is_import_quarantined_member(self, member: str) -> bool:
        member_name = Path(member).name
        for mapping_name in self.IMPORT_QUARANTINED_MAPPING_TASKS:
            if member_name in {f"{mapping_name}.MTT.zip", f"{mapping_name}.TASKFLOW.xml"}:
                return True
        return False

    def _remove_refs_to_import_quarantined_tasks(
        self,
        exported_objects: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        quarantined_guids = {
            str(obj.get("objectGuid"))
            for obj in exported_objects
            if self._is_import_quarantined_object(obj) and obj.get("objectGuid")
        }
        if not quarantined_guids:
            return exported_objects, {}
        cleaned: list[dict[str, Any]] = []
        for obj in exported_objects:
            if str(obj.get("objectGuid")) in quarantined_guids:
                continue
            metadata = obj.get("metadata")
            if isinstance(metadata, dict):
                refs = metadata.get("objectRefs")
                if isinstance(refs, list):
                    metadata["objectRefs"] = [ref for ref in refs if ref not in quarantined_guids]
            cleaned.append(obj)
        return cleaned, {guid: "" for guid in quarantined_guids}

    @staticmethod
    def _client_native_source_org(native_sources: list[Path]) -> dict[str, str]:
        for source in native_sources:
            try:
                with zipfile.ZipFile(source) as package:
                    metadata = json.loads(package.read("exportMetadata.v2.json").decode("utf-8"))
            except (OSError, zipfile.BadZipFile, KeyError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            source_org_id = str(metadata.get("sourceOrgId", "")).strip()
            source_org_name = str(metadata.get("sourceOrgName", "")).strip()
            if source_org_id and source_org_name and source_org_id.lower() not in {"generated", "client-native-remapped"}:
                return {"sourceOrgId": source_org_id, "sourceOrgName": source_org_name}
        return {"sourceOrgId": "gO4aVWAxgK0lY2UdXmECWZ", "sourceOrgName": "Jacobs"}

    def _client_native_allowed_object_guids(
        self,
        metadata: dict[str, Any],
        mapping_names: set[str],
        workflow_names: set[str],
    ) -> set[str]:
        objects = [obj for obj in metadata.get("exportedObjects", []) if obj.get("objectGuid")]
        by_guid = {obj["objectGuid"]: obj for obj in objects}
        mapping_layer_by_name: dict[str, dict[str, dict[str, Any]]] = {}
        for obj in objects:
            object_type = str(obj.get("objectType", ""))
            object_name = str(obj.get("objectName", ""))
            if object_type in {"DTEMPLATE", "MTT", "TASKFLOW"} and object_name:
                mapping_layer_by_name.setdefault(object_name, {})[object_type] = obj

        allowed: set[str] = set()
        queue: list[str] = []

        def add(obj: dict[str, Any] | None) -> None:
            if not obj:
                return
            guid = obj.get("objectGuid")
            if guid and guid not in allowed:
                allowed.add(guid)
                queue.append(guid)

        for name in mapping_names:
            by_type = mapping_layer_by_name.get(name, {})
            add(by_type.get("DTEMPLATE"))
            add(by_type.get("MTT"))
        for name in workflow_names | mapping_names:
            add(mapping_layer_by_name.get(name, {}).get("TASKFLOW"))

        while queue:
            guid = queue.pop(0)
            obj = by_guid.get(guid, {})
            for ref in (obj.get("metadata") or {}).get("objectRefs") or []:
                ref_obj = by_guid.get(ref)
                if ref_obj:
                    add(ref_obj)
        return allowed

    @staticmethod
    def _client_native_member_for_object(obj: dict[str, Any]) -> str:
        path = str(obj.get("path", "")).strip("/")
        name = str(obj.get("objectName", ""))
        object_type = str(obj.get("objectType", ""))
        extension = ".xml" if object_type == "TASKFLOW" else ".json" if object_type in {"Project", "Folder"} else ".zip"
        member_name = f"{name}.{object_type}{extension}"
        return f"{path}/{member_name}" if path else member_name

    def _dedupe_exported_objects_by_import_name(
        self,
        exported_objects: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        """Remove duplicate import-visible objects after merging reference exports.

        IDMC rejects packages that contain two assets with the same name, type,
        and target location. Keeping the first object preserves the higher
        priority source selected by _client_native_sources_for_mappings().
        """

        seen: set[tuple[str, str, str]] = set()
        kept_guid_by_key: dict[tuple[str, str, str], str] = {}
        guid_replacements: dict[str, str] = {}
        deduped: list[dict[str, Any]] = []
        for obj in exported_objects:
            key = (
                str(obj.get("path", "")),
                str(obj.get("objectType", "")),
                str(obj.get("objectName", "")),
            )
            if key in seen:
                old_guid = str(obj.get("objectGuid", ""))
                kept_guid = kept_guid_by_key.get(key, "")
                if old_guid and kept_guid and old_guid != kept_guid:
                    guid_replacements[old_guid] = kept_guid
                continue
            seen.add(key)
            if obj.get("objectGuid"):
                kept_guid_by_key[key] = str(obj["objectGuid"])
            deduped.append(obj)
        if guid_replacements:
            deduped = self._replace_json_strings(deduped, guid_replacements)
        return deduped, guid_replacements

    def _replace_removed_duplicate_guids(
        self,
        entries: dict[str, bytes],
        guid_replacements: dict[str, str],
    ) -> dict[str, bytes]:
        return {
            name: self._replace_text_bytes(content, guid_replacements)
            for name, content in entries.items()
        }

    def _rewrite_client_native_nested_zip(
        self,
        source_bytes: bytes,
        target_member: str,
        mapping_name: str,
        replacements: dict[str, str],
        folder_token: str,
        now: datetime,
    ) -> bytes:
        rewritten: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(source_bytes)) as source_zip:
            for member in source_zip.namelist():
                rewritten[member] = self._replace_client_native_bytes(source_zip.read(member), replacements, folder_token)
        if target_member.endswith(".DTEMPLATE.zip"):
            rewritten = self._sync_dtemplate_file_records(rewritten, mapping_name, now)
            rewritten = self._ensure_dtemplate_preview(rewritten, mapping_name, now)
            rewritten = self._sync_dtemplate_file_records(rewritten, mapping_name, now)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target_zip:
            for member, content in rewritten.items():
                target_zip.writestr(member, content)
        return output.getvalue()

    def _replace_client_native_json(
        self,
        value: Any,
        replacements: dict[str, str],
        folder_token: str,
    ) -> Any:
        value = self._replace_json_strings(value, {self.folder_name: folder_token})
        value = self._replace_json_strings(value, replacements)
        return self._replace_json_strings(value, {folder_token: self.folder_name})

    def _replace_client_native_bytes(
        self,
        value: bytes,
        replacements: dict[str, str],
        folder_token: str,
    ) -> bytes:
        value = self._replace_text_bytes(value, {self.folder_name: folder_token})
        value = self._replace_text_bytes(value, replacements)
        return self._replace_text_bytes(value, {folder_token: self.folder_name})

    def _add_client_native_support_artifacts(
        self,
        entries: dict[str, bytes],
        xml_files: list[Path],
        mapping_assets: list[dict[str, Any]],
        now: datetime,
    ) -> None:
        source_index = {"description": "PowerCenter XML mappings preserved for full object coverage.", "files": []}
        for path in xml_files:
            data = path.read_bytes()
            target = f"SourceXML/{path.name}"
            entries[target] = data
            source_index["files"].append(
                {
                    "fileName": path.name,
                    "zipPath": target,
                    "sizeBytes": len(data),
                    "sha256": hashlib.sha256(data).hexdigest().upper(),
                }
            )
        entries["SourceXML/index.json"] = json.dumps(source_index, indent=2).encode("utf-8")

        image_index = {
            "description": "IDMC mapping preview images and graph JSON bundled with this package.",
            "generatedAt": self._timestamp(now),
            "images": [],
        }
        for asset in mapping_assets:
            mapping_name = asset["name"]
            mapping = self._remediated_mapping_element(mapping_name)
            if mapping is not None:
                graph_bytes = self._json_bytes(graph_from_mapping_element(mapping, visual_overrides=True).to_dict())
                for kind in ["valid_mapping", "full_transformations"]:
                    graph_name = f"MappingImages/{mapping_name}_{kind}.graph.json"
                    entries[graph_name] = graph_bytes
                    image_index["images"].append(
                        {
                            "mappingName": mapping_name,
                            "kind": f"{kind}_graph",
                            "fileName": Path(graph_name).name,
                            "zipPath": graph_name,
                            "format": "json",
                            "sizeBytes": len(graph_bytes),
                            "sha256": hashlib.sha256(graph_bytes).hexdigest().upper(),
                        }
                    )
            preview_bytes = self._mapping_reference_preview_bytes(mapping_name)
            image_ext = "png" if preview_bytes.startswith(b"\x89PNG\r\n\x1a\n") else "jpeg"
            for kind in ["valid_mapping", "full_transformations"]:
                image_name = f"MappingImages/{mapping_name}_{kind}.{image_ext}"
                entries[image_name] = preview_bytes
                image_index["images"].append(
                    {
                        "mappingName": mapping_name,
                        "kind": kind,
                        "fileName": Path(image_name).name,
                        "zipPath": image_name,
                        "format": image_ext,
                        "sizeBytes": len(preview_bytes),
                        "sha256": hashlib.sha256(preview_bytes).hexdigest().upper(),
                    }
                )
        entries["MappingImages/index.json"] = json.dumps(image_index, indent=2).encode("utf-8")

    def _add_client_native_reference_analysis_artifact(
        self,
        entries: dict[str, bytes],
        mapping_assets: list[dict[str, Any]],
        native_sources: list[Path],
        now: datetime,
    ) -> None:
        required = sorted(asset["name"] for asset in mapping_assets)
        source_rows = []
        covered: set[str] = set()
        for source in native_sources:
            mappings = sorted(self._native_package_mapping_names(source))
            matched = sorted(set(mappings) & set(required))
            covered.update(matched)
            source_rows.append(
                {
                    "sourceZip": str(source),
                    "nativeMappings": mappings,
                    "matchedInputMappings": matched,
                    "strategy": "reuse-native-export-internals-and-remap-project-folder",
                }
            )
        report = {
            "generatedAt": self._timestamp(now),
            "targetProject": self.PROJECT_NAME,
            "targetFolder": self.folder_name,
            "requiredMappings": required,
            "coveredMappings": sorted(covered),
            "missingNativeReferences": sorted(set(required) - covered),
            "importQuarantinedMappingTasks": [
                {"mappingName": name, "reason": reason}
                for name, reason in sorted(self.IMPORT_QUARANTINED_MAPPING_TASKS.items())
            ],
            "rulesApplied": [
                "Preserve DTEMPLATE/MTT/TASKFLOW internals from client-tested native exports.",
                "Remap only project and folder paths into the target IDMC location.",
                "Regenerate package manifest, contents CSV, fileRecord sizes, and exportPackage checksum.",
                "Preserve objectRefs, repo handles, runtime metadata, and dependency artifacts.",
                "Bundle source XML, graph JSON, and mapping preview images as support artifacts.",
            ],
            "classification": {
                "implemented": [
                    "ZIP hierarchy normalization",
                    "manifest/objectRef preservation",
                    "DTEMPLATE fileRecord validation",
                    "native dependency preservation",
                    "mapping image bundling",
                    "checksum validation",
                ],
                "intentionallyNotImplemented": [
                    "Synthetic DTEMPLATE canvas metadata injection. It previously caused incorrect IDMC image rendering.",
                    "Mapping-specific hardcoded graph rewrites for unsupported future mappings.",
                ],
            },
            "sources": source_rows,
        }
        entries["ValidationReports/native_reference_analysis.json"] = json.dumps(report, indent=2).encode("utf-8")

    @staticmethod
    def _remap_client_native_path(path: str, old_projects: set[str], old_folders: set[str]) -> str:
        new_folder_prefix = "/Explore/RPA_PC_Modernization/Custom_SDE_SupplyChain"
        for project in old_projects:
            for folder in old_folders:
                old_prefix = f"/Explore/{project}/{folder}"
                if path == old_prefix:
                    return new_folder_prefix
                if path.startswith(f"{old_prefix}/"):
                    return f"{new_folder_prefix}{path[len(old_prefix):]}"
            if path == f"/Explore/{project}":
                return "/Explore/RPA_PC_Modernization"
            if path.startswith(f"/Explore/{project}/"):
                return f"/Explore/RPA_PC_Modernization/{path[len(f'/Explore/{project}/') :]}"
        return path

    @staticmethod
    def _remap_client_native_member(member: str, old_projects: set[str], old_folders: set[str]) -> str:
        for project in old_projects:
            for folder in old_folders:
                old_prefix = f"Explore/{project}/{folder}/"
                if member.startswith(old_prefix):
                    return f"Explore/RPA_PC_Modernization/Custom_SDE_SupplyChain/{member[len(old_prefix):]}"
                old_folder_file = f"Explore/{project}/{folder}.Folder.json"
                if member == old_folder_file:
                    return "Explore/RPA_PC_Modernization/Custom_SDE_SupplyChain.Folder.json"
            if member == f"Explore/{project}.Project.json":
                return "Explore/RPA_PC_Modernization.Project.json"
            if member.startswith(f"Explore/{project}/"):
                return f"Explore/RPA_PC_Modernization/{member[len(f'Explore/{project}/') :]}"
        return member

    @staticmethod
    def _contents_csv_bytes(exported_objects: list[dict[str, Any]]) -> bytes:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=["objectPath", "objectName", "objectType", "id"])
        writer.writeheader()
        for obj in exported_objects:
            writer.writerow(
                {
                    "objectPath": obj.get("path", ""),
                    "objectName": obj.get("objectName", ""),
                    "objectType": obj.get("objectType", ""),
                    "id": obj.get("objectGuid", ""),
                }
            )
        return buffer.getvalue().encode("utf-8")

    def _write_entries_zip(self, entries: dict[str, bytes]) -> None:
        self.output_folder.mkdir(parents=True, exist_ok=True)
        target = self.package_path
        temp_path = target.with_name(f"{target.stem}_{self._epoch_millis(datetime.now(timezone.utc))}.zip")
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for member, content in sorted(entries.items()):
                package.writestr(member, content)
        try:
            temp_path.replace(target)
        except PermissionError:
            self.logger.warning("Existing IDMC export ZIP is locked. Copying native package over target: %s", target)
            shutil.copyfile(temp_path, target)

    def _default_reference_package(self, reference_package: str | Path | None) -> Path | None:
        candidates = []
        if reference_package:
            candidates.append(self._resolve_path(reference_package))
        candidates.extend(
            [
                self.project_root / "reference_packages/client_success/Custom_SDE_SupplyChain_native_refs.zip",
                Path("D:/Download/Custom_Project_Export.zip"),
                Path(r"D:/Downloads/Custom_Project_Export.zip"),
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

    def _guid(self, *parts: str) -> str:
        digest = hashlib.sha256("|".join([self.package_guid_seed, *parts]).encode("utf-8")).digest()
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
        candidates = sorted({path.resolve() for path in [*self.remediated_folder.glob("*.XML"), *self.remediated_folder.glob("*.xml")]})
        input_folder = self._resolve_path(self.config.paths.xml_folder)
        if not input_folder.exists():
            return candidates
        input_stems = {
            path.stem.lower()
            for path in [*input_folder.glob("*.XML"), *input_folder.glob("*.xml")]
        }
        filtered = [
            path
            for path in candidates
            if re.sub(r"_remediated$", "", path.stem, flags=re.IGNORECASE).lower() in input_stems
        ]
        return filtered or candidates

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

