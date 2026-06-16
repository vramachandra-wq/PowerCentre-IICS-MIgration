from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - local dependency fallback.
    pd = None

from parser.models import FolderMetadata, MappingMetadata, ParsedXmlMetadata
from repository.canonical_models import (
    CanonicalAsset,
    CanonicalColumn,
    CanonicalConnector,
    CanonicalMapping,
    CanonicalMappingJson,
    CanonicalRepository,
    CanonicalSqlOverride,
    CanonicalTransformation,
    canonical_to_dict,
)
from utils.config_loader import AppConfig


class CanonicalMetadataBuilder:
    """Normalizes parsed PowerCenter metadata into stable canonical repository tables."""

    PLATFORM = "POWERCENTER"

    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(config.paths.output_folder) / "canonical"
        self.json_output_folder = self.output_folder / "mapping_json_by_id"
        self.table_output_folder = self.output_folder / "tables"

    def build(self, parsed_files: list[ParsedXmlMetadata]) -> CanonicalRepository:
        canonical = CanonicalRepository()
        for parsed in parsed_files:
            repository_name = parsed.repository.get("name", "")
            for folder in parsed.folders:
                self._add_folder_assets(canonical, parsed.file_name, repository_name, folder)
                for mapping in folder.mappings:
                    self._add_mapping(canonical, parsed.file_name, repository_name, folder, mapping)
        self._deduplicate(canonical)
        return canonical

    def to_dataframes(self, canonical: CanonicalRepository) -> dict[str, Any]:
        rows = self.to_rows(canonical)
        if pd is None:
            self.logger.warning("pandas is not installed. Returning canonical rows and writing CSV outputs only.")
            return rows
        return {name: pd.DataFrame(data) for name, data in rows.items()}

    def to_rows(self, canonical: CanonicalRepository) -> dict[str, list[dict[str, Any]]]:
        return {
            "canonical_assets": [asdict(item) for item in canonical.assets],
            "canonical_mappings": [asdict(item) for item in canonical.mappings],
            "canonical_transformations": [asdict(item) for item in canonical.transformations],
            "canonical_columns": [asdict(item) for item in canonical.columns],
            "canonical_connectors": [asdict(item) for item in canonical.connectors],
            "canonical_sql_overrides": [asdict(item) for item in canonical.sql_overrides],
        }

    def write_outputs(self, canonical: CanonicalRepository) -> None:
        self.json_output_folder.mkdir(parents=True, exist_ok=True)
        self.table_output_folder.mkdir(parents=True, exist_ok=True)

        self._write_tables(self.to_dataframes(canonical))
        self._write_mapping_json(canonical.mapping_json)
        self._write_summary(canonical)
        self.logger.info("Canonical repository outputs written to %s", self.output_folder)

    def _add_folder_assets(
        self,
        canonical: CanonicalRepository,
        source_file: str,
        repository_name: str,
        folder: FolderMetadata,
    ) -> None:
        for source in folder.sources:
            asset_id = self._asset_id(repository_name, folder.folder_name, "SOURCE", source.source_name)
            canonical.assets.append(
                CanonicalAsset(
                    asset_id=asset_id,
                    asset_name=source.source_name,
                    asset_type="SOURCE",
                    platform=self.PLATFORM,
                    repository_name=repository_name,
                    folder_name=folder.folder_name,
                    source_file=source_file,
                    parent_asset_id="",
                    complexity="LOW",
                )
            )
            for column in source.columns:
                canonical.columns.append(
                    CanonicalColumn(
                        column_id=self._column_id(asset_id, column.column_name),
                        asset_id=asset_id,
                        table_name=source.source_name,
                        table_type="SOURCE",
                        column_name=column.column_name,
                        datatype=column.datatype,
                        precision=column.precision,
                        scale=column.scale,
                        repository_name=repository_name,
                        folder_name=folder.folder_name,
                        source_file=source_file,
                    )
                )

        for target in folder.targets:
            asset_id = self._asset_id(repository_name, folder.folder_name, "TARGET", target.target_name)
            canonical.assets.append(
                CanonicalAsset(
                    asset_id=asset_id,
                    asset_name=target.target_name,
                    asset_type="TARGET",
                    platform=self.PLATFORM,
                    repository_name=repository_name,
                    folder_name=folder.folder_name,
                    source_file=source_file,
                    parent_asset_id="",
                    complexity="LOW",
                )
            )
            for column in target.columns:
                canonical.columns.append(
                    CanonicalColumn(
                        column_id=self._column_id(asset_id, column.column_name),
                        asset_id=asset_id,
                        table_name=target.target_name,
                        table_type="TARGET",
                        column_name=column.column_name,
                        datatype=column.datatype,
                        precision=column.precision,
                        scale=column.scale,
                        repository_name=repository_name,
                        folder_name=folder.folder_name,
                        source_file=source_file,
                    )
                )

    def _add_mapping(
        self,
        canonical: CanonicalRepository,
        source_file: str,
        repository_name: str,
        folder: FolderMetadata,
        mapping: MappingMetadata,
    ) -> None:
        mapping_id = self._asset_id(repository_name, folder.folder_name, "MAPPING", mapping.mapping_name)
        source_names = self._mapping_instances(mapping, "SOURCE")
        target_names = self._mapping_instances(mapping, "TARGET")
        sql_overrides = self._mapping_sql_overrides(folder, mapping)
        complexity = self._classify_mapping(mapping, sql_overrides)

        canonical.assets.append(
            CanonicalAsset(
                asset_id=mapping_id,
                asset_name=mapping.mapping_name,
                asset_type="MAPPING",
                platform=self.PLATFORM,
                repository_name=repository_name,
                folder_name=folder.folder_name,
                source_file=source_file,
                parent_asset_id="",
                complexity=complexity,
            )
        )
        canonical.mappings.append(
            CanonicalMapping(
                mapping_id=mapping_id,
                mapping_name=mapping.mapping_name,
                repository_name=repository_name,
                folder_name=folder.folder_name,
                source_file=source_file,
                sources="|".join(source_names),
                targets="|".join(target_names),
                transformation_count=mapping.transformation_count,
                connector_count=len(mapping.connectors),
                sql_override_count=len(sql_overrides),
                complexity=complexity,
            )
        )

        transformations_json: list[dict[str, Any]] = []
        for transformation in mapping.transformations:
            transformation_id = self._asset_id(
                repository_name,
                folder.folder_name,
                "TRANSFORMATION",
                f"{mapping.mapping_name}.{transformation.transformation_name}",
            )
            canonical.assets.append(
                CanonicalAsset(
                    asset_id=transformation_id,
                    asset_name=transformation.transformation_name,
                    asset_type="TRANSFORMATION",
                    platform=self.PLATFORM,
                    repository_name=repository_name,
                    folder_name=folder.folder_name,
                    source_file=source_file,
                    parent_asset_id=mapping_id,
                    complexity=self._classify_transformation(transformation.transformation_type),
                )
            )
            canonical.transformations.append(
                CanonicalTransformation(
                    transformation_id=transformation_id,
                    mapping_id=mapping_id,
                    mapping_name=mapping.mapping_name,
                    transformation_name=transformation.transformation_name,
                    transformation_type=transformation.transformation_type,
                    reusable_flag=transformation.reusable_flag,
                    attribute_count=len(transformation.attributes),
                    port_count=len(transformation.ports),
                )
            )
            transformations_json.append(
                {
                    "transformation_name": transformation.transformation_name,
                    "type": transformation.transformation_type,
                    "reusable": transformation.reusable_flag,
                    "attributes": transformation.attributes,
                    "ports": [asdict(port) for port in transformation.ports],
                }
            )

        connectors_json: list[dict[str, Any]] = []
        for index, connector in enumerate(mapping.connectors, start=1):
            canonical_connector = CanonicalConnector(
                connector_id=self._hash_id("CONN", mapping_id, str(index), connector.from_instance, connector.to_instance),
                mapping_id=mapping_id,
                mapping_name=mapping.mapping_name,
                from_instance=connector.from_instance,
                from_field=connector.from_field,
                to_instance=connector.to_instance,
                to_field=connector.to_field,
                from_instance_type=connector.from_instance_type,
                to_instance_type=connector.to_instance_type,
            )
            canonical.connectors.append(canonical_connector)
            connectors_json.append(asdict(canonical_connector))

        sql_json: list[dict[str, Any]] = []
        for index, sql_override in enumerate(sql_overrides, start=1):
            canonical_sql = CanonicalSqlOverride(
                sql_override_id=self._hash_id("SQL", mapping_id, str(index), sql_override.context_name),
                mapping_id=mapping_id,
                mapping_name=mapping.mapping_name,
                context_type=sql_override.context_type,
                context_name=sql_override.context_name,
                sql_query=sql_override.sql_query,
            )
            canonical.sql_overrides.append(canonical_sql)
            sql_json.append(asdict(canonical_sql))

        canonical.mapping_json.append(
            CanonicalMappingJson(
                mapping_id=mapping_id,
                mapping_name=mapping.mapping_name,
                repository_name=repository_name,
                folder_name=folder.folder_name,
                source_file=source_file,
                complexity=complexity,
                sources=[asdict(source) for source in folder.sources if source.source_name in source_names],
                targets=[asdict(target) for target in folder.targets if target.target_name in target_names],
                transformations=transformations_json,
                connectors=connectors_json,
                sql_overrides=sql_json,
            )
        )

    @staticmethod
    def _mapping_instances(mapping: MappingMetadata, instance_type: str) -> list[str]:
        return sorted(
            {
                instance.transformation_name or instance.instance_name
                for instance in mapping.instances
                if instance.instance_type == instance_type
            }
        )

    @staticmethod
    def _mapping_sql_overrides(folder: FolderMetadata, mapping: MappingMetadata) -> list[Any]:
        overrides = list(mapping.sql_overrides)
        for session in folder.sessions:
            if session.mapping_name == mapping.mapping_name:
                overrides.extend(session.sql_overrides)
        return overrides

    @staticmethod
    def _classify_mapping(mapping: MappingMetadata, sql_overrides: list[Any]) -> str:
        score = 0
        score += mapping.transformation_count
        score += len(mapping.connectors) // 25
        score += len(sql_overrides) * 3
        complex_types = {"Lookup Procedure", "Stored Procedure", "Java", "SQL", "Update Strategy", "Router"}
        score += sum(2 for item in mapping.transformations if item.transformation_type in complex_types)
        if score >= 18:
            return "HIGH"
        if score >= 8:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _classify_transformation(transformation_type: str) -> str:
        if transformation_type in {"Lookup Procedure", "Stored Procedure", "Java", "SQL"}:
            return "HIGH"
        if transformation_type in {"Router", "Update Strategy", "Aggregator", "Joiner"}:
            return "MEDIUM"
        return "LOW"

    def _write_tables(self, tables: dict[str, Any]) -> None:
        for table_name, table in tables.items():
            output_file = self.table_output_folder / f"{table_name}.csv"
            if pd is not None and hasattr(table, "to_csv"):
                table.to_csv(output_file, index=False)
                continue
            self._write_csv(output_file, table)

    def _write_mapping_json(self, mappings: list[CanonicalMappingJson]) -> None:
        for mapping in mappings:
            file_name = f"{self._safe_name(mapping.mapping_name)}__{mapping.mapping_id}.json"
            (self.json_output_folder / file_name).write_text(
                json.dumps(canonical_to_dict(mapping), indent=2),
                encoding="utf-8",
            )

        all_mappings = [canonical_to_dict(mapping) for mapping in mappings]
        (self.output_folder / "canonical_mappings.json").write_text(
            json.dumps(all_mappings, indent=2),
            encoding="utf-8",
        )

    def _write_summary(self, canonical: CanonicalRepository) -> None:
        summary = {
            "asset_count": len(canonical.assets),
            "mapping_count": len(canonical.mappings),
            "transformation_count": len(canonical.transformations),
            "column_count": len(canonical.columns),
            "connector_count": len(canonical.connectors),
            "sql_override_count": len(canonical.sql_overrides),
            "mapping_json_count": len(canonical.mapping_json),
            "table_output_folder": str(self.table_output_folder),
            "mapping_json_output_folder": str(self.json_output_folder),
        }
        (self.output_folder / "canonical_summary.json").write_text(
            json.dumps(summary, indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _deduplicate(canonical: CanonicalRepository) -> None:
        canonical.assets = list({item.asset_id: item for item in canonical.assets}.values())
        canonical.mappings = list({item.mapping_id: item for item in canonical.mappings}.values())
        canonical.transformations = list(
            {item.transformation_id: item for item in canonical.transformations}.values()
        )
        canonical.columns = list({item.column_id: item for item in canonical.columns}.values())
        canonical.connectors = list({item.connector_id: item for item in canonical.connectors}.values())
        canonical.sql_overrides = list(
            {item.sql_override_id: item for item in canonical.sql_overrides}.values()
        )
        canonical.mapping_json = list({item.mapping_id: item for item in canonical.mapping_json}.values())

    @staticmethod
    def _write_csv(output_file: Path, rows: list[dict[str, Any]]) -> None:
        fieldnames = sorted({key for row in rows for key in row.keys()})
        with output_file.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _asset_id(repository_name: str, folder_name: str, asset_type: str, asset_name: str) -> str:
        return CanonicalMetadataBuilder._hash_id("AST", repository_name, folder_name, asset_type, asset_name)

    @staticmethod
    def _column_id(asset_id: str, column_name: str) -> str:
        return CanonicalMetadataBuilder._hash_id("COL", asset_id, column_name)

    @staticmethod
    def _hash_id(prefix: str, *parts: str) -> str:
        normalized = "||".join(part.strip().upper() for part in parts)
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
        return f"{prefix}_{digest}"

    @staticmethod
    def _safe_name(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "mapping"

    def _resolve_path(self, path_value: str | Path) -> Path:
        path = Path(path_value)
        return path if path.is_absolute() else self.project_root / path
