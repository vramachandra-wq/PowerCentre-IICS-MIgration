"""
Generate IDMC export packages from remediated PowerCenter XML metadata.
"""

from __future__ import annotations

import csv
import hashlib
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
    ) -> None:
        """Initialize the package generator using existing app configuration."""

        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(output_folder or config.paths.output_folder)
        self.remediated_folder = self._resolve_path(remediated_folder or self.output_folder / "remediated_xml")
        self.package_name = package_name
        self.package_path = self.output_folder / package_name
        self.staging_folder = self.output_folder / "idmc_export_package"
        self.parser = XMLParser(config=config, logger=logger)

    def generate(self) -> IdmcExportSummary:
        """Generate one combined ZIP package from all XML files in remediated_xml."""

        xml_files = self._xml_files()
        if not xml_files:
            raise FileNotFoundError(f"No XML files found in {self.remediated_folder}")

        if self.staging_folder.exists():
            shutil.rmtree(self.staging_folder)
        self.staging_folder.mkdir(parents=True, exist_ok=True)

        parsed_files = self._parse_xml_files(xml_files)
        mapping_assets = self._mapping_assets(parsed_files)
        if not mapping_assets:
            raise ValueError(f"No mappings found in XML files under {self.remediated_folder}")

        now = datetime.now(timezone.utc)
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
                        f"Session pushed from PC to ICS : {asset['name']}",
                        [asset_ids.dtemplate, ids.connection, ids.agent_group],
                    ),
                    self._exported_object(
                        asset_ids.dtemplate,
                        asset["name"],
                        "DTEMPLATE",
                        object_path,
                        "JSON",
                        "VALID",
                        f"Mapping pushed from PC to ICS : {asset['name']}",
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

    def _write_mapping_artifacts(self, asset: dict[str, Any], ids: _AssetIds, now: datetime) -> None:
        mapping_folder = self.staging_folder / "Explore" / self.PROJECT_NAME / self.FOLDER_NAME
        mapping_name = asset["name"]
        template_payload = self._template_payload(asset)
        template_bytes = self._json_bytes(template_payload)
        preview_bytes = self._preview_bytes(mapping_name)

        self._write_zip(
            mapping_folder / f"{mapping_name}.DTEMPLATE.zip",
            {
                "mappingTemplate.json": self._json_bytes(
                    [
                        {
                            "@type": "mappingTemplate",
                            "id": "@1",
                            "name": mapping_name,
                            "description": f"Mapping pushed from PC to ICS : {mapping_name}",
                            "autoExpireObject": False,
                            "bundleVersion": "0",
                            "assetFrsGuid": ids.dtemplate,
                            "templateId": "@3",
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
                    ]
                ),
                "bin/@2.bin": preview_bytes,
                "bin/@3.bin": template_bytes,
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
                "description": f"Generated from remediated XML {asset['source_xml']}",
                "sourceXml": asset["source_xml"],
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
            "description": f"Session pushed from PC to ICS : {asset['name']}",
            "autoExpireObject": False,
            "runtimeEnvironmentId": f"@{ids.agent_group}",
            "maxLogs": 10,
            "verbose": False,
            "mappingId": f"@{ids.dtemplate}",
            "frsGuid": ids.mtt,
            "shortDescription": f"Session pushed from PC to ICS : {asset['name']}"[:60],
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
      <types1:Description>These workflows are created from the Workflow Generation Wizard.</types1:Description>
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
            <description>These workflows are created from the Workflow Generation Wizard.</description>
            <generator>PC2Cloud Workflow Converter v1</generator>
            <input>
               <parameter name="InputMappingTaskParameterFileDir" type="string"/>
               <parameter name="InputMappingTaskParameterFileName" type="string"/>
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
        rows = []
        for path in sorted(file for file in self.staging_folder.rglob("*") if file.is_file() and file.name != "exportPackage.chksum"):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append(f"{digest}  {path.relative_to(self.staging_folder).as_posix()}")
        (self.staging_folder / "exportPackage.chksum").write_text("\n".join(rows) + "\n", encoding="utf-8")

    def _zip_staging_folder(self) -> None:
        self.output_folder.mkdir(parents=True, exist_ok=True)
        if self.package_path.exists():
            self.package_path.unlink()
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
) -> IdmcExportSummary:
    """Generate a combined IDMC export ZIP package."""

    return IdmcExportPackageGenerator(
        config=config,
        logger=logger,
        remediated_folder=remediated_folder,
        output_folder=output_folder,
        package_name=package_name,
    ).generate()
