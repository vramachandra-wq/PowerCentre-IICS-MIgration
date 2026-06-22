from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass
class CanonicalAsset:
    asset_id: str
    asset_name: str
    asset_type: str
    platform: str
    repository_name: str
    folder_name: str
    source_file: str
    parent_asset_id: str
    complexity: str


@dataclass
class CanonicalMapping:
    mapping_id: str
    mapping_name: str
    repository_name: str
    folder_name: str
    source_file: str
    sources: str
    targets: str
    transformation_count: int
    connector_count: int
    sql_override_count: int
    complexity: str


@dataclass
class CanonicalTransformation:
    transformation_id: str
    mapping_id: str
    mapping_name: str
    transformation_name: str
    transformation_type: str
    reusable_flag: str
    attribute_count: int
    port_count: int


@dataclass
class CanonicalColumn:
    column_id: str
    asset_id: str
    table_name: str
    table_type: str
    column_name: str
    datatype: str
    precision: str
    scale: str
    repository_name: str
    folder_name: str
    source_file: str


@dataclass
class CanonicalConnector:
    connector_id: str
    mapping_id: str
    mapping_name: str
    from_instance: str
    from_field: str
    to_instance: str
    to_field: str
    from_instance_type: str
    to_instance_type: str


@dataclass
class CanonicalSqlOverride:
    sql_override_id: str
    mapping_id: str
    mapping_name: str
    context_type: str
    context_name: str
    sql_query: str


@dataclass
class CanonicalMappingJson:
    mapping_id: str
    mapping_name: str
    repository_name: str
    folder_name: str
    source_file: str
    complexity: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    targets: list[dict[str, Any]] = field(default_factory=list)
    transformations: list[dict[str, Any]] = field(default_factory=list)
    connectors: list[dict[str, Any]] = field(default_factory=list)
    sql_overrides: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class CanonicalRepository:
    assets: list[CanonicalAsset] = field(default_factory=list)
    mappings: list[CanonicalMapping] = field(default_factory=list)
    transformations: list[CanonicalTransformation] = field(default_factory=list)
    columns: list[CanonicalColumn] = field(default_factory=list)
    connectors: list[CanonicalConnector] = field(default_factory=list)
    sql_overrides: list[CanonicalSqlOverride] = field(default_factory=list)
    mapping_json: list[CanonicalMappingJson] = field(default_factory=list)


def canonical_to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: canonical_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [canonical_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical_to_dict(item) for key, item in value.items()}
    return value
