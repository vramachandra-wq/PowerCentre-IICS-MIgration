"""
Module: business/parser/mapping_parser.py

Purpose:
    This module supports PowerCenter XML metadata parsing for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the PowerCenter XML metadata parsing area and extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

try:
    from data.models.mapping_model import ConnectorMetadata, InstanceMetadata, MappingMetadata
    from business.parser.transformation_parser import TransformationParser
except ModuleNotFoundError:
    from models import ConnectorMetadata, InstanceMetadata, MappingMetadata
    from transformation_parser import TransformationParser


class MappingParser:
    """Parses mapping-level PowerCenter metadata."""

    def __init__(self, transformation_parser: TransformationParser | None = None) -> None:
        """
        Executes the __init__ workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                transformation_parser (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.transformation_parser = transformation_parser or TransformationParser()

    def parse_mappings(self, folder: Element) -> list[MappingMetadata]:
        """
        Executes the parse_mappings workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                folder (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return [self.parse_mapping(mapping) for mapping in folder.findall("MAPPING")]

    def parse_mapping(self, mapping: Element) -> MappingMetadata:
        """
        Executes the parse_mapping workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                mapping (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        transformations = self.transformation_parser.parse_transformations(mapping)
        connectors = self._parse_connectors(mapping)
        instances = self._parse_instances(mapping)
        return MappingMetadata(
            mapping_name=mapping.attrib.get("NAME", ""),
            is_valid=mapping.attrib.get("ISVALID", ""),
            transformation_count=len(transformations),
            source_count=sum(1 for item in instances if item.instance_type == "SOURCE"),
            target_count=sum(1 for item in instances if item.instance_type == "TARGET"),
            transformations=transformations,
            connectors=connectors,
            instances=instances,
            sql_overrides=self.transformation_parser.parse_sql_overrides(mapping),
        )

    @staticmethod
    def _parse_connectors(mapping: Element) -> list[ConnectorMetadata]:
        """
        Executes the _parse_connectors workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                mapping (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return [
            ConnectorMetadata(
                from_instance=connector.attrib.get("FROMINSTANCE", ""),
                from_field=connector.attrib.get("FROMFIELD", ""),
                to_instance=connector.attrib.get("TOINSTANCE", ""),
                to_field=connector.attrib.get("TOFIELD", ""),
                from_instance_type=connector.attrib.get("FROMINSTANCETYPE", ""),
                to_instance_type=connector.attrib.get("TOINSTANCETYPE", ""),
            )
            for connector in mapping.findall("CONNECTOR")
        ]

    @staticmethod
    def _parse_instances(mapping: Element) -> list[InstanceMetadata]:
        """
        Executes the _parse_instances workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                mapping (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return [
            InstanceMetadata(
                instance_name=instance.attrib.get("NAME", ""),
                instance_type=instance.attrib.get("TYPE", ""),
                transformation_name=instance.attrib.get("TRANSFORMATION_NAME", ""),
                transformation_type=instance.attrib.get("TRANSFORMATION_TYPE", ""),
                reusable_flag=instance.attrib.get("REUSABLE", ""),
            )
            for instance in mapping.findall("INSTANCE")
        ]
