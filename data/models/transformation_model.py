"""
Support transformation model for migration data structures and persistence.
Defines models and repository access for metadata workflows.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass
class CanonicalAsset:
    """Encapsulates canonical asset behavior for migration workflows."""

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
    """Encapsulates canonical mapping behavior for migration workflows."""

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
    """Encapsulates canonical transformation behavior for migration workflows."""

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
    """Encapsulates canonical column behavior for migration workflows."""

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
    """Encapsulates canonical connector behavior for migration workflows."""

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
    """Encapsulates canonical sql override behavior for migration workflows."""

    sql_override_id: str
    mapping_id: str
    mapping_name: str
    context_type: str
    context_name: str
    sql_query: str


@dataclass
class CanonicalMappingJson:
    """Encapsulates canonical mapping json behavior for migration workflows."""

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
    """Handles persistence operations for migration metadata."""

    assets: list[CanonicalAsset] = field(default_factory=list)
    mappings: list[CanonicalMapping] = field(default_factory=list)
    transformations: list[CanonicalTransformation] = field(default_factory=list)
    columns: list[CanonicalColumn] = field(default_factory=list)
    connectors: list[CanonicalConnector] = field(default_factory=list)
    sql_overrides: list[CanonicalSqlOverride] = field(default_factory=list)
    mapping_json: list[CanonicalMappingJson] = field(default_factory=list)


def canonical_to_dict(value: Any) -> Any:
    """Handle canonical to dict using the provided value."""

    if is_dataclass(value):
        return {key: canonical_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [canonical_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical_to_dict(item) for key, item in value.items()}
    return value
