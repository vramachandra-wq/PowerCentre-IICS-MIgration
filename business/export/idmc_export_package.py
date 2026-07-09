"""
Generate IDMC export packages from remediated PowerCenter XML metadata.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

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
    FOLDER_NAME = "Custom_Project"
    CONNECTION_NAME = "DBConnection_OLAP_Oracle"
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
        if not mapping_assets:
            raise ValueError(f"No mappings found in XML files under {self.remediated_folder}")

        ids = self._base_ids()
        self._write_system_artifacts(ids, now)
        self._write_container_artifacts(ids, now, len(mapping_assets))

        exported_objects = [
            self._exported_object(ids.project, self.PROJECT_NAME, "Project", "/Explore", "Binary", "COMPLETE", "Migrated project"),
            self._exported_object(ids.connection, self.CONNECTION_NAME, "Connection", "/SYS", "JSON", "COMPLETE", None, [ids.agent_group]),
        ]
        contents_rows = [
            {"objectPath": "/Explore", "objectName": self.PROJECT_NAME, "objectType": "Project", "id": ids.project},
            {"objectPath": "/SYS", "objectName": self.CONNECTION_NAME, "objectType": "Connection", "id": ids.connection},
        ]

        if self.execution_strategy == "POWERCENTER_XML_TASK":
            self._write_pcxml_source_bundle(xml_files, mapping_assets, now)
            sample_templates = self._sample_asset_templates()
            if sample_templates:
                for index, asset in enumerate(mapping_assets):
                    asset_ids = self._asset_ids(asset["name"])
                    self._write_sample_backed_mapping_artifacts(
                        asset,
                        asset_ids,
                        sample_templates[index % len(sample_templates)],
                        ids,
                        now,
                    )
                    object_path = f"/Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}"
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
                                [asset_ids.dtemplate, ids.connection, ids.agent_group],
                            ),
                            self._exported_object(
                                asset_ids.taskflow,
                                asset["name"],
                                "TASKFLOW",
                                object_path,
                                "application/json; charset=utf-8",
                                "VALID",
                                "PowerCenter XML conversion taskflow wrapper generated from the reference export package.",
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
                self.logger.warning(
                    "No reference IDMC export package was found. Generated PCXML bundle only; the IDMC UI may show no selectable assets."
                )
        else:
            for asset in mapping_assets:
                asset_ids = self._asset_ids(asset["name"])
                self._write_mapping_artifacts(asset, asset_ids, now)
                object_path = f"/Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}"
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
            self._exported_object(ids.folder, self.FOLDER_NAME, "Folder", f"/Explore/{self.PROJECT_NAME}", "Binary", "COMPLETE", "")
        )
        exported_objects.append(
            self._exported_object(ids.agent_group, self.AGENT_GROUP_NAME, "AgentGroup", "/SYS", "JSON", "VALID", None)
        )
        contents_rows.extend(
            [
                {"objectPath": f"/Explore/{self.PROJECT_NAME}", "objectName": self.FOLDER_NAME, "objectType": "Folder", "id": ids.folder},
                {"objectPath": "/SYS", "objectName": self.AGENT_GROUP_NAME, "objectType": "AgentGroup", "id": ids.agent_group},
            ]
        )

        self._write_export_metadata(exported_objects, now)
        self._write_contents_csv(contents_rows, now)
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
                for mapping in folder.mappings:
                    name = self._asset_name(mapping.mapping_name)
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
                            "session": sessions.get(mapping.mapping_name),
                            "sources": folder.sources,
                            "targets": folder.targets,
                        }
                    )
        return assets

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
        (project_folder / self.FOLDER_NAME).mkdir(parents=True, exist_ok=True)
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
        (project_folder / f"{self.FOLDER_NAME}.Folder.json").write_text(
            json.dumps(
                self._odata_document(
                    "Folder",
                    ids.folder,
                    self.FOLDER_NAME,
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
        bundle_folder = self.staging_folder / "PCXML" / self.FOLDER_NAME
        bundle_folder.mkdir(parents=True, exist_ok=True)
        for xml_file in xml_files:
            shutil.copy2(xml_file, bundle_folder / xml_file.name)

        by_xml: dict[str, list[str]] = {}
        for asset in mapping_assets:
            by_xml.setdefault(asset["source_xml"], []).append(asset["name"])

        manifest = {
            "name": f"{self.FOLDER_NAME}_PowerCenterXml_Source_Bundle",
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
                    "relativePath": f"PCXML/{self.FOLDER_NAME}/{xml_file.name}",
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
            connection = next((item for item in objects if item.get("objectType") == "Connection"), {})
            agent_group = next((item for item in objects if item.get("objectType") == "AgentGroup"), {})
            templates: list[dict[str, Any]] = []
            dtemplates = [item for item in objects if item.get("objectType") == "DTEMPLATE"]
            for dtemplate in dtemplates:
                name = dtemplate.get("objectName", "")
                mtt = next((item for item in objects if item.get("objectType") == "MTT" and item.get("objectName") == name), None)
                taskflow = next((item for item in objects if item.get("objectType") == "TASKFLOW" and item.get("objectName") == name), None)
                if not name or not mtt or not taskflow:
                    continue
                base_path = dtemplate.get("path", "").strip("/")
                artifact_prefix = f"{base_path}/{name}" if base_path else name
                dtemplate_zip = f"{artifact_prefix}.DTEMPLATE.zip"
                mtt_zip = f"{artifact_prefix}.MTT.zip"
                taskflow_xml = f"{artifact_prefix}.TASKFLOW.xml"
                if not all(item in package.namelist() for item in [dtemplate_zip, mtt_zip, taskflow_xml]):
                    continue
                templates.append(
                    {
                        "name": name,
                        "dtemplate_id": dtemplate.get("objectGuid", ""),
                        "mtt_id": mtt.get("objectGuid", ""),
                        "taskflow_id": taskflow.get("objectGuid", ""),
                        "connection_id": connection.get("objectGuid", ""),
                        "agent_group_id": agent_group.get("objectGuid", ""),
                        "dtemplate_zip": package.read(dtemplate_zip),
                        "mtt_zip": package.read(mtt_zip),
                        "taskflow_xml": package.read(taskflow_xml).decode("utf-8"),
                    }
                )
            return templates

    def _write_sample_backed_mapping_artifacts(
        self,
        asset: dict[str, Any],
        ids: _AssetIds,
        template: dict[str, Any],
        base_ids: _AssetIds,
        now: datetime,
    ) -> None:
        mapping_folder = self.staging_folder / "Explore" / self.PROJECT_NAME / self.FOLDER_NAME
        mapping_folder.mkdir(parents=True, exist_ok=True)
        mapping_name = asset["name"]
        replacements = {
            template["name"]: mapping_name,
            template["dtemplate_id"]: ids.dtemplate,
            template["mtt_id"]: ids.mtt,
            template["taskflow_id"]: ids.taskflow,
            template["connection_id"]: base_ids.connection,
            template["agent_group_id"]: base_ids.agent_group,
        }

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
        taskflow_text = self._replace_text(template["taskflow_xml"], replacements)
        taskflow_text = taskflow_text.replace(
            "<types1:Description>These workflows are created from the Workflow Generation Wizard.</types1:Description>",
            "<types1:Description>Sample-backed taskflow wrapper for remediated PowerCenter XML.</types1:Description>",
        )
        (mapping_folder / f"{mapping_name}.TASKFLOW.xml").write_text(taskflow_text, encoding="utf-8")

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
        with zipfile.ZipFile(Path(output_path), "w", compression=zipfile.ZIP_DEFLATED) as output_zip:
            with zipfile.ZipFile(io.BytesIO(source_bytes)) as source_zip:
                for member in source_zip.namelist():
                    content = source_zip.read(member)
                    output_zip.writestr(member, member_rewriter(member, content, replacements, mapping_name, ids, now))

    def _rewrite_dtemplate_member(
        self,
        member: str,
        content: bytes,
        replacements: dict[str, str],
        mapping_name: str,
        ids: _AssetIds,
        now: datetime,
    ) -> bytes:
        if member in {"mappingTemplate.json", "fileRecord.json"}:
            payload = json.loads(content.decode("utf-8"))
            payload = self._replace_json_strings(payload, replacements)
            if member == "mappingTemplate.json" and payload:
                payload[0]["name"] = mapping_name
                payload[0]["description"] = f"Sample-backed conversion placeholder for remediated XML : {mapping_name}"
                payload[0]["assetFrsGuid"] = ids.dtemplate
                payload[0]["deployTime"] = self._epoch_millis(now)
            return self._json_bytes(payload)
        if member == "bin/@3.bin":
            try:
                payload = json.loads(content.decode("utf-8"))
                payload = self._replace_json_strings(payload, replacements)
                if isinstance(payload, dict) and isinstance(payload.get("content"), dict):
                    payload["content"]["name"] = mapping_name
                return self._json_bytes(payload)
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._replace_text_bytes(content, replacements)
        return self._replace_text_bytes(content, replacements)

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
                payload[0]["mappingId"] = f"@{ids.dtemplate}"
                payload[0]["frsGuid"] = ids.mtt
            return self._json_bytes(payload)
        return self._replace_text_bytes(content, replacements)

    def _write_mapping_artifacts(self, asset: dict[str, Any], ids: _AssetIds, now: datetime) -> None:
        mapping_folder = self.staging_folder / "Explore" / self.PROJECT_NAME / self.FOLDER_NAME
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

    def _write_export_metadata(self, exported_objects: list[dict[str, Any]], now: datetime) -> None:
        payload = {
            "name": f"job-{self._epoch_millis(now)}",
            "sourceOrgId": "generated",
            "sourceOrgName": "PC_IICS_MIGRATION",
            "exportedObjects": exported_objects,
        }
        (self.staging_folder / "exportMetadata.v2.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _write_contents_csv(self, rows: list[dict[str, str]], now: datetime) -> None:
        csv_path = self.staging_folder / f"ContentsofExportPackage_job-{self._epoch_millis(now)}.csv"
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
    ) -> dict[str, Any]:
        return {
            "objectGuid": object_guid,
            "objectName": name,
            "objectType": object_type,
            "path": path,
            "providerName": None,
            "metadata": {
                "modelVersion": model_version or {"major": 0, "minor": 0},
                "repoInfo": None if object_type in {"Project", "Folder"} else {"repoHandle": self._repo_handle(object_guid)},
                "objectRefs": refs or [],
                "contextAttributes": [] if object_type in {"Project", "Folder"} else [{"name": "id", "value": "@1"}],
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
            folder=self._guid("folder", self.FOLDER_NAME),
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
        for before, after in replacements.items():
            if before:
                updated = updated.replace(before, after)
        return updated

    def _replace_text_bytes(self, value: bytes, replacements: dict[str, str]) -> bytes:
        try:
            return self._replace_text(value.decode("utf-8"), replacements).encode("utf-8")
        except UnicodeDecodeError:
            return value

    def _default_reference_package(self, reference_package: str | Path | None) -> Path | None:
        candidates = []
        if reference_package:
            candidates.append(self._resolve_path(reference_package))
        candidates.extend(
            [
                self.project_root / "reference_export_package.zip",
                Path("D:/Download/Custom_SDE_PBCS_Export 1.zip"),
                Path("D:/Download/Custom_SDE_PBCS_Export.zip"),
            ]
        )
        return next((candidate for candidate in candidates if candidate.exists()), None)

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
