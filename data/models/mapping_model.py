from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass
class SourceColumn:
    column_name: str
    datatype: str
    precision: str
    scale: str


@dataclass
class SourceMetadata:
    source_name: str
    database_type: str
    owner_name: str
    columns: list[SourceColumn] = field(default_factory=list)


@dataclass
class TargetColumn:
    column_name: str
    datatype: str
    precision: str
    scale: str


@dataclass
class TargetMetadata:
    target_name: str
    database_type: str
    columns: list[TargetColumn] = field(default_factory=list)


@dataclass
class TransformationPort:
    port_name: str
    datatype: str
    precision: str
    scale: str
    port_type: str
    expression: str


@dataclass
class TransformationMetadata:
    transformation_name: str
    transformation_type: str
    reusable_flag: str
    attributes: dict[str, str] = field(default_factory=dict)
    ports: list[TransformationPort] = field(default_factory=list)


@dataclass
class ConnectorMetadata:
    from_instance: str
    from_field: str
    to_instance: str
    to_field: str
    from_instance_type: str
    to_instance_type: str


@dataclass
class InstanceMetadata:
    instance_name: str
    instance_type: str
    transformation_name: str
    transformation_type: str
    reusable_flag: str


@dataclass
class SqlOverrideMetadata:
    context_type: str
    context_name: str
    parent_name: str
    sql_query: str


@dataclass
class MappingMetadata:
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
class SessionMetadata:
    session_name: str
    mapping_name: str
    is_valid: str
    reusable_flag: str
    attributes: dict[str, str] = field(default_factory=dict)
    sql_overrides: list[SqlOverrideMetadata] = field(default_factory=list)


@dataclass
class WorkflowMetadata:
    workflow_name: str
    is_valid: str
    is_enabled: str
    server_name: str
    task_instances: list[dict[str, str]] = field(default_factory=list)
    workflow_links: list[dict[str, str]] = field(default_factory=list)


@dataclass
class FolderMetadata:
    folder_name: str
    repository_name: str
    sources: list[SourceMetadata] = field(default_factory=list)
    targets: list[TargetMetadata] = field(default_factory=list)
    mappings: list[MappingMetadata] = field(default_factory=list)
    sessions: list[SessionMetadata] = field(default_factory=list)
    workflows: list[WorkflowMetadata] = field(default_factory=list)


@dataclass
class ParsedXmlMetadata:
    file_name: str
    repository: dict[str, str]
    folders: list[FolderMetadata] = field(default_factory=list)


def to_plain_dict(value: Any) -> Any:
    if is_dataclass(value):
        return {key: to_plain_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain_dict(item) for key, item in value.items()}
    return value
