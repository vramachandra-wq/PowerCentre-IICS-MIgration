from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - exercised only when dependencies are missing locally.
    pd = None

try:
    from business.parser.mapping_parser import MappingParser
    from data.models.mapping_model import FolderMetadata, ParsedXmlMetadata, to_plain_dict
    from business.parser.source_target_parser import SourceTargetParser
    from business.parser.workflow_parser import WorkflowParser
    from common.utils.xml_utils import XmlLoader
except ModuleNotFoundError:
    from mapping_parser import MappingParser
    from models import FolderMetadata, ParsedXmlMetadata, to_plain_dict
    from source_target_parser import SourceTargetParser
    from workflow_parser import WorkflowParser
    from xml_loader import XmlLoader

from common.config.config import AppConfig


class XMLParser:
    """Coordinates batch parsing of PowerCenter XML exports into structured metadata."""

    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        self.xml_folder = self._resolve_path(config.paths.xml_folder)
        self.output_folder = self._resolve_path(config.paths.output_folder)
        self.json_output_folder = self.output_folder / "parsed_json"
        self.table_output_folder = self.output_folder / "metadata_tables"
        self.loader = XmlLoader()
        self.source_target_parser = SourceTargetParser()
        self.mapping_parser = MappingParser()
        self.workflow_parser = WorkflowParser()

    def parse_folder(self) -> dict[str, Any]:
        xml_files = sorted(self.xml_folder.glob("*.XML")) + sorted(self.xml_folder.glob("*.xml"))
        unique_files = sorted(set(xml_files))
        if not unique_files:
            self.logger.warning("No XML files found in %s", self.xml_folder)
            return {"parsed_files": [], "dataframes": {}, "errors": []}

        self.json_output_folder.mkdir(parents=True, exist_ok=True)
        self.table_output_folder.mkdir(parents=True, exist_ok=True)

        parsed_files: list[ParsedXmlMetadata] = []
        errors: list[dict[str, str]] = []
        for xml_file in unique_files:
            try:
                parsed = self.parse_file(xml_file)
                parsed_files.append(parsed)
                self._write_json(parsed)
                self.logger.info("Parsed metadata from %s", xml_file.name)
            except Exception as exc:
                self.logger.exception("Failed to parse metadata from %s", xml_file)
                errors.append({"file_name": xml_file.name, "error": str(exc)})

        tables = self.to_dataframes(parsed_files)
        self._write_tables(tables)
        self._write_batch_summary(parsed_files, errors)
        return {"parsed_files": parsed_files, "dataframes": tables, "errors": errors}

    def parse_file(self, xml_path: Path) -> ParsedXmlMetadata:
        xml_file = self._resolve_path(xml_path)
        tree = self.loader.parse(xml_file)
        root = tree.getroot()
        repository = self._repository(root)
        folders: list[FolderMetadata] = []

        for folder in root.findall(".//FOLDER"):
            folders.append(
                FolderMetadata(
                    folder_name=folder.attrib.get("NAME", ""),
                    repository_name=repository.get("name", ""),
                    sources=self.source_target_parser.parse_sources(folder),
                    targets=self.source_target_parser.parse_targets(folder),
                    mappings=self.mapping_parser.parse_mappings(folder),
                    sessions=self.workflow_parser.parse_sessions(folder),
                    workflows=self.workflow_parser.parse_workflows(folder),
                )
            )

        return ParsedXmlMetadata(file_name=xml_file.name, repository=repository, folders=folders)

    def to_dataframes(self, parsed_files: list[ParsedXmlMetadata]) -> dict[str, Any]:
        rows = self._flatten(parsed_files)
        if pd is None:
            self.logger.warning("pandas is not installed. Returning table rows and writing CSV outputs only.")
            return rows
        return {name: pd.DataFrame(data) for name, data in rows.items()}

    def _flatten(self, parsed_files: list[ParsedXmlMetadata]) -> dict[str, list[dict[str, Any]]]:
        tables: dict[str, list[dict[str, Any]]] = {
            "repositories": [],
            "folders": [],
            "workflows": [],
            "sessions": [],
            "mappings": [],
            "sources": [],
            "source_columns": [],
            "targets": [],
            "target_columns": [],
            "transformations": [],
            "ports": [],
            "connectors": [],
            "instances": [],
            "sql_overrides": [],
        }

        for parsed in parsed_files:
            tables["repositories"].append({"file_name": parsed.file_name, **parsed.repository})
            for folder in parsed.folders:
                base = {
                    "file_name": parsed.file_name,
                    "repository_name": folder.repository_name,
                    "folder_name": folder.folder_name,
                }
                tables["folders"].append(
                    {
                        **base,
                        "source_count": len(folder.sources),
                        "target_count": len(folder.targets),
                        "mapping_count": len(folder.mappings),
                        "session_count": len(folder.sessions),
                        "workflow_count": len(folder.workflows),
                    }
                )
                self._flatten_sources(folder.sources, base, tables)
                self._flatten_targets(folder.targets, base, tables)
                self._flatten_mappings(folder.mappings, base, tables)
                self._flatten_sessions(folder.sessions, base, tables)
                self._flatten_workflows(folder.workflows, base, tables)
        return tables

    @staticmethod
    def _flatten_sources(sources, base, tables) -> None:
        for source in sources:
            source_base = {**base, "source_name": source.source_name}
            tables["sources"].append(
                {
                    **source_base,
                    "database_type": source.database_type,
                    "owner_name": source.owner_name,
                    "column_count": len(source.columns),
                }
            )
            for column in source.columns:
                tables["source_columns"].append({**source_base, **asdict(column)})

    @staticmethod
    def _flatten_targets(targets, base, tables) -> None:
        for target in targets:
            target_base = {**base, "target_name": target.target_name}
            tables["targets"].append(
                {
                    **target_base,
                    "database_type": target.database_type,
                    "column_count": len(target.columns),
                }
            )
            for column in target.columns:
                tables["target_columns"].append({**target_base, **asdict(column)})

    @staticmethod
    def _flatten_mappings(mappings, base, tables) -> None:
        for mapping in mappings:
            mapping_base = {**base, "mapping_name": mapping.mapping_name}
            tables["mappings"].append(
                {
                    **mapping_base,
                    "is_valid": mapping.is_valid,
                    "transformation_count": mapping.transformation_count,
                    "source_count": mapping.source_count,
                    "target_count": mapping.target_count,
                    "connector_count": len(mapping.connectors),
                    "instance_count": len(mapping.instances),
                    "sql_override_count": len(mapping.sql_overrides),
                }
            )
            for transformation in mapping.transformations:
                transformation_base = {
                    **mapping_base,
                    "transformation_name": transformation.transformation_name,
                }
                tables["transformations"].append(
                    {
                        **transformation_base,
                        "transformation_type": transformation.transformation_type,
                        "reusable_flag": transformation.reusable_flag,
                        "attribute_count": len(transformation.attributes),
                        "port_count": len(transformation.ports),
                    }
                )
                for port in transformation.ports:
                    tables["ports"].append(
                        {
                            **transformation_base,
                            "port_scope": "TRANSFORMATION",
                            **asdict(port),
                        }
                    )
            for connector in mapping.connectors:
                tables["connectors"].append({**mapping_base, **asdict(connector)})
            for instance in mapping.instances:
                tables["instances"].append({**mapping_base, **asdict(instance)})
            for sql_override in mapping.sql_overrides:
                tables["sql_overrides"].append({**mapping_base, **asdict(sql_override)})

    @staticmethod
    def _flatten_sessions(sessions, base, tables) -> None:
        for session in sessions:
            session_base = {**base, "session_name": session.session_name}
            tables["sessions"].append(
                {
                    **session_base,
                    "mapping_name": session.mapping_name,
                    "is_valid": session.is_valid,
                    "reusable_flag": session.reusable_flag,
                    "attribute_count": len(session.attributes),
                    "sql_override_count": len(session.sql_overrides),
                }
            )
            for sql_override in session.sql_overrides:
                tables["sql_overrides"].append({**session_base, **asdict(sql_override)})

    @staticmethod
    def _flatten_workflows(workflows, base, tables) -> None:
        for workflow in workflows:
            tables["workflows"].append(
                {
                    **base,
                    "workflow_name": workflow.workflow_name,
                    "is_valid": workflow.is_valid,
                    "is_enabled": workflow.is_enabled,
                    "server_name": workflow.server_name,
                    "task_instance_count": len(workflow.task_instances),
                    "workflow_link_count": len(workflow.workflow_links),
                }
            )

    def _write_json(self, parsed: ParsedXmlMetadata) -> None:
        output_file = self.json_output_folder / f"{Path(parsed.file_name).stem}.json"
        output_file.write_text(json.dumps(to_plain_dict(parsed), indent=2), encoding="utf-8")

    def _write_tables(self, tables: dict[str, Any]) -> None:
        for table_name, table in tables.items():
            output_file = self.table_output_folder / f"{table_name}.csv"
            if pd is not None and hasattr(table, "to_csv"):
                table.to_csv(output_file, index=False)
                continue

            rows = table
            fieldnames = sorted({key for row in rows for key in row.keys()})
            with output_file.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

    def _write_batch_summary(self, parsed_files: list[ParsedXmlMetadata], errors: list[dict[str, str]]) -> None:
        summary = {
            "processed_file_count": len(parsed_files),
            "error_count": len(errors),
            "errors": errors,
            "json_output_folder": str(self.json_output_folder),
            "table_output_folder": str(self.table_output_folder),
        }
        (self.output_folder / "parser_batch_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )

    @staticmethod
    def _repository(root: Element) -> dict[str, str]:
        repository = root.find("REPOSITORY")
        if repository is None:
            return {
                "name": "",
                "version": "",
                "codepage": "",
                "database_type": "",
                "repository_version": root.attrib.get("REPOSITORY_VERSION", ""),
            }
        return {
            "name": repository.attrib.get("NAME", ""),
            "version": repository.attrib.get("VERSION", ""),
            "codepage": repository.attrib.get("CODEPAGE", ""),
            "database_type": repository.attrib.get("DATABASETYPE", ""),
            "repository_version": root.attrib.get("REPOSITORY_VERSION", ""),
        }

    def _resolve_path(self, path_value: str | Path) -> Path:
        path = Path(path_value)
        return path if path.is_absolute() else self.project_root / path
