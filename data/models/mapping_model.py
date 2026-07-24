"""
Support mapping model for migration data structures and persistence.
Defines models and repository access for metadata workflows.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass
class SourceColumn:
    """Encapsulates source column behavior for migration workflows."""

    column_name: str
    datatype: str
    precision: str
    scale: str


@dataclass
class SourceMetadata:
    """Encapsulates source metadata behavior for migration workflows."""

    source_name: str
    database_type: str
    owner_name: str
    columns: list[SourceColumn] = field(default_factory=list)


@dataclass
class TargetColumn:
    """Encapsulates target column behavior for migration workflows."""

    column_name: str
    datatype: str
    precision: str
    scale: str


@dataclass
class TargetMetadata:
    """Encapsulates target metadata behavior for migration workflows."""

    target_name: str
    database_type: str
    columns: list[TargetColumn] = field(default_factory=list)


@dataclass
class TransformationPort:
    """Encapsulates transformation port behavior for migration workflows."""

    port_name: str
    datatype: str
    precision: str
    scale: str
    port_type: str
    expression: str
    mapplet_group: str = ""


@dataclass
class TransformationMetadata:
    """Encapsulates transformation metadata behavior for migration workflows."""

    transformation_name: str
    transformation_type: str
    reusable_flag: str
    attributes: dict[str, str] = field(default_factory=dict)
    ports: list[TransformationPort] = field(default_factory=list)


@dataclass
class ConnectorMetadata:
    """Encapsulates connector metadata behavior for migration workflows."""

    from_instance: str
    from_field: str
    to_instance: str
    to_field: str
    from_instance_type: str
    to_instance_type: str


@dataclass
class InstanceMetadata:
    """Encapsulates instance metadata behavior for migration workflows."""

    instance_name: str
    instance_type: str
    transformation_name: str
    transformation_type: str
    reusable_flag: str


@dataclass
class SqlOverrideMetadata:
    """Encapsulates sql override metadata behavior for migration workflows."""

    context_type: str
    context_name: str
    parent_name: str
    sql_query: str


@dataclass
class MappingMetadata:
    """Encapsulates mapping metadata behavior for migration workflows."""

    mapping_name: str
    is_valid: str
    transformation_count: int
    source_count: int
    target_count: int
    transformations: list[TransformationMetadata] = field(default_factory=list)
    connectors: list[ConnectorMetadata] = field(default_factory=list)
    instances: list[InstanceMetadata] = field(default_factory=list)
    sql_overrides: list[SqlOverrideMetadata] = field(default_factory=list)


@dataclass
class MappletMetadata:
    """Folder-level PowerCenter MAPPLET definition (reusable subgraph)."""

    mapplet_name: str
    is_valid: str
    transformation_count: int
    transformations: list[TransformationMetadata] = field(default_factory=list)
    connectors: list[ConnectorMetadata] = field(default_factory=list)
    instances: list[InstanceMetadata] = field(default_factory=list)
    sql_overrides: list[SqlOverrideMetadata] = field(default_factory=list)


@dataclass
class SessionMetadata:
    """Encapsulates session metadata behavior for migration workflows."""

    session_name: str
    mapping_name: str
    is_valid: str
    reusable_flag: str
    attributes: dict[str, str] = field(default_factory=dict)
    sql_overrides: list[SqlOverrideMetadata] = field(default_factory=list)
    transformation_instances: list[dict[str, str]] = field(default_factory=list)


@dataclass
class WorkflowMetadata:
    """Encapsulates workflow metadata behavior for migration workflows."""

    workflow_name: str
    is_valid: str
    is_enabled: str
    server_name: str
    schedule_type: str = ""
    schedule_interval: str = ""
    schedule_timezone: str = ""
    schedule_start_time: str = ""
    schedule_recurrence: str = ""
    task_instances: list[dict[str, str]] = field(default_factory=list)
    workflow_links: list[dict[str, str]] = field(default_factory=list)


@dataclass
class FolderMetadata:
    """Encapsulates folder metadata behavior for migration workflows."""

    folder_name: str
    repository_name: str
    sources: list[SourceMetadata] = field(default_factory=list)
    targets: list[TargetMetadata] = field(default_factory=list)
    mappings: list[MappingMetadata] = field(default_factory=list)
    mapplets: list[MappletMetadata] = field(default_factory=list)
    reusable_transformations: list[TransformationMetadata] = field(default_factory=list)
    sessions: list[SessionMetadata] = field(default_factory=list)
    workflows: list[WorkflowMetadata] = field(default_factory=list)


@dataclass
class ParsedXmlMetadata:
    """Encapsulates parsed xml metadata behavior for migration workflows."""

    file_name: str
    repository: dict[str, str]
    folders: list[FolderMetadata] = field(default_factory=list)


def to_plain_dict(value: Any) -> Any:
    """Handle to plain dict using the provided value."""

    if is_dataclass(value):
        return {key: to_plain_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain_dict(item) for key, item in value.items()}
    return value
