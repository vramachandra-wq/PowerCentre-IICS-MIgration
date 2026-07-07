"""
Module: business/parser/transformation_parser.py

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
    from data.models.mapping_model import SqlOverrideMetadata, TransformationMetadata, TransformationPort
except ModuleNotFoundError:
    from models import SqlOverrideMetadata, TransformationMetadata, TransformationPort


class TransformationParser:
    """Parses PowerCenter transformations, ports, attributes, and SQL overrides."""

    SQL_OVERRIDE_NAMES = {"Sql Query", "SQL Query"}

    def parse_transformations(self, mapping: Element) -> list[TransformationMetadata]:
        """
        Executes the parse_transformations workflow for PowerCenter XML metadata parsing.
        
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

        return [self.parse_transformation(item) for item in mapping.findall("TRANSFORMATION")]

    def parse_transformation(self, transformation: Element) -> TransformationMetadata:
        """
        Executes the parse_transformation workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                transformation (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        attributes = self._parse_attributes(transformation)
        ports = [
            TransformationPort(
                port_name=field.attrib.get("NAME", ""),
                datatype=field.attrib.get("DATATYPE", ""),
                precision=field.attrib.get("PRECISION", ""),
                scale=field.attrib.get("SCALE", ""),
                port_type=field.attrib.get("PORTTYPE", ""),
                expression=field.attrib.get("EXPRESSION", ""),
            )
            for field in transformation.findall("TRANSFORMFIELD")
        ]
        return TransformationMetadata(
            transformation_name=transformation.attrib.get("NAME", ""),
            transformation_type=transformation.attrib.get("TYPE", ""),
            reusable_flag=transformation.attrib.get("REUSABLE", ""),
            attributes=attributes,
            ports=ports,
        )

    def parse_sql_overrides(self, mapping: Element) -> list[SqlOverrideMetadata]:
        """
        Executes the parse_sql_overrides workflow for PowerCenter XML metadata parsing.
        
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

        overrides: list[SqlOverrideMetadata] = []
        mapping_name = mapping.attrib.get("NAME", "")
        for transformation in mapping.findall("TRANSFORMATION"):
            transformation_name = transformation.attrib.get("NAME", "")
            for attribute in self._attribute_elements(transformation):
                if attribute.attrib.get("NAME") in self.SQL_OVERRIDE_NAMES:
                    sql_query = attribute.attrib.get("VALUE", "")
                    if sql_query:
                        overrides.append(
                            SqlOverrideMetadata(
                                context_type="TRANSFORMATION",
                                context_name=transformation_name,
                                parent_name=mapping_name,
                                sql_query=sql_query,
                            )
                        )
        return overrides

    def _parse_attributes(self, transformation: Element) -> dict[str, str]:
        """
        Executes the _parse_attributes workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                transformation (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return {
            item.attrib.get("NAME", ""): item.attrib.get("VALUE", "")
            for item in self._attribute_elements(transformation)
            if item.attrib.get("NAME")
        }

    @staticmethod
    def _attribute_elements(parent: Element) -> list[Element]:
        """
        Executes the _attribute_elements workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                parent (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return [*parent.findall("TABLEATTRIBUTE"), *parent.findall("ATTRIBUTE")]
