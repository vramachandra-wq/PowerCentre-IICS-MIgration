"""
Module: business/parser/source_target_parser.py

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
    from data.models.mapping_model import SourceColumn, SourceMetadata, TargetColumn, TargetMetadata
except ModuleNotFoundError:
    from models import SourceColumn, SourceMetadata, TargetColumn, TargetMetadata


class SourceTargetParser:
    """Parses folder-level PowerCenter source and target definitions."""

    def parse_sources(self, folder: Element) -> list[SourceMetadata]:
        """
        Executes the parse_sources workflow for PowerCenter XML metadata parsing.
        
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

        sources: list[SourceMetadata] = []
        for source in folder.findall("SOURCE"):
            columns = [
                SourceColumn(
                    column_name=field.attrib.get("NAME", ""),
                    datatype=field.attrib.get("DATATYPE", ""),
                    precision=field.attrib.get("PRECISION", ""),
                    scale=field.attrib.get("SCALE", ""),
                )
                for field in source.findall("SOURCEFIELD")
            ]
            sources.append(
                SourceMetadata(
                    source_name=source.attrib.get("NAME", ""),
                    database_type=source.attrib.get("DATABASETYPE", ""),
                    owner_name=source.attrib.get("OWNERNAME", ""),
                    columns=columns,
                )
            )
        return sources

    def parse_targets(self, folder: Element) -> list[TargetMetadata]:
        """
        Executes the parse_targets workflow for PowerCenter XML metadata parsing.
        
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

        targets: list[TargetMetadata] = []
        for target in folder.findall("TARGET"):
            columns = [
                TargetColumn(
                    column_name=field.attrib.get("NAME", ""),
                    datatype=field.attrib.get("DATATYPE", ""),
                    precision=field.attrib.get("PRECISION", ""),
                    scale=field.attrib.get("SCALE", ""),
                )
                for field in target.findall("TARGETFIELD")
            ]
            targets.append(
                TargetMetadata(
                    target_name=target.attrib.get("NAME", ""),
                    database_type=target.attrib.get("DATABASETYPE", ""),
                    columns=columns,
                )
            )
        return targets
