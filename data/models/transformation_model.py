"""
Module: data/models/transformation_model.py

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
class CanonicalAsset:
    """
    Represents the CanonicalAsset component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

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
    """
    Represents the CanonicalMapping component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

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
    """
    Represents the CanonicalTransformation component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

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
    """
    Represents the CanonicalColumn component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

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
    """
    Represents the CanonicalConnector component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

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
    """
    Represents the CanonicalSqlOverride component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    sql_override_id: str
    mapping_id: str
    mapping_name: str
    context_type: str
    context_name: str
    sql_query: str


@dataclass
class CanonicalMappingJson:
    """
    Represents the CanonicalMappingJson component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

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
    """
    Represents the CanonicalRepository component in the domain data models area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that defines structured records used by parsers, validators, and reporting components. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    assets: list[CanonicalAsset] = field(default_factory=list)
    mappings: list[CanonicalMapping] = field(default_factory=list)
    transformations: list[CanonicalTransformation] = field(default_factory=list)
    columns: list[CanonicalColumn] = field(default_factory=list)
    connectors: list[CanonicalConnector] = field(default_factory=list)
    sql_overrides: list[CanonicalSqlOverride] = field(default_factory=list)
    mapping_json: list[CanonicalMappingJson] = field(default_factory=list)


def canonical_to_dict(value: Any) -> Any:
    """
    Executes the canonical_to_dict workflow for domain data models.
    
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
        return {key: canonical_to_dict(item) for key, item in asdict(value).items()}
    if isinstance(value, list):
        return [canonical_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical_to_dict(item) for key, item in value.items()}
    return value
