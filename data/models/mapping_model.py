"""
Module: data/models/mapping_model.py

Purpose:
    This module supports domain data models for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the domain data models area and defines structured records used by parsers, validators, and reporting components. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any


@dataclass
class SourceColumn:
    """
    Represents the SourceColumn component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    column_name: str
    datatype: str
    precision: str
    scale: str


@dataclass
class SourceMetadata:
    """
    Represents the SourceMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    source_name: str
    database_type: str
    owner_name: str
    columns: list[SourceColumn] = field(default_factory=list)


@dataclass
class TargetColumn:
    """
    Represents the TargetColumn component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    column_name: str
    datatype: str
    precision: str
    scale: str


@dataclass
class TargetMetadata:
    """
    Represents the TargetMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    target_name: str
    database_type: str
    columns: list[TargetColumn] = field(default_factory=list)


@dataclass
class TransformationPort:
    """
    Represents the TransformationPort component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    port_name: str
    datatype: str
    precision: str
    scale: str
    port_type: str
    expression: str


@dataclass
class TransformationMetadata:
    """
    Represents the TransformationMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    transformation_name: str
    transformation_type: str
    reusable_flag: str
    attributes: dict[str, str] = field(default_factory=dict)
    ports: list[TransformationPort] = field(default_factory=list)


@dataclass
class ConnectorMetadata:
    """
    Represents the ConnectorMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    from_instance: str
    from_field: str
    to_instance: str
    to_field: str
    from_instance_type: str
    to_instance_type: str


@dataclass
class InstanceMetadata:
    """
    Represents the InstanceMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    instance_name: str
    instance_type: str
    transformation_name: str
    transformation_type: str
    reusable_flag: str


@dataclass
class SqlOverrideMetadata:
    """
    Represents the SqlOverrideMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    context_type: str
    context_name: str
    parent_name: str
    sql_query: str


@dataclass
class MappingMetadata:
    """
    Represents the MappingMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

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
    """
    Represents the SessionMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    session_name: str
    mapping_name: str
    is_valid: str
    reusable_flag: str
    attributes: dict[str, str] = field(default_factory=dict)
    sql_overrides: list[SqlOverrideMetadata] = field(default_factory=list)


@dataclass
class WorkflowMetadata:
    """
    Represents the WorkflowMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

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
    """
    Represents the FolderMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    folder_name: str
    repository_name: str
    sources: list[SourceMetadata] = field(default_factory=list)
    targets: list[TargetMetadata] = field(default_factory=list)
    mappings: list[MappingMetadata] = field(default_factory=list)
    sessions: list[SessionMetadata] = field(default_factory=list)
    workflows: list[WorkflowMetadata] = field(default_factory=list)


@dataclass
class ParsedXmlMetadata:
    """
    Represents the ParsedXmlMetadata component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    file_name: str
    repository: dict[str, str]
    folders: list[FolderMetadata] = field(default_factory=list)


def to_plain_dict(value: Any) -> Any:
    """
    Executes the to_plain_dict workflow for domain data models.
    
    Purpose:
        Support the module responsibility by performing one focused step in the migration assessment process.
    
    Workflow:
        1. Receive inputs from the caller or surrounding service layer.
        2. Apply the existing project logic without changing business rules.
        3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
    
    Parameters:
            value (object): Value supplied by the caller and used by the workflow.
    
    Returns:
        object:
            The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
    
    Raises:
        Exception:
            This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
    
    Implementation Notes:
        This function belongs to the layer that defines structured records used by parsers, validators, and reporting components. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    if is_dataclass(value):
        return {key: to_plain_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_plain_dict(item) for key, item in value.items()}
    return value
