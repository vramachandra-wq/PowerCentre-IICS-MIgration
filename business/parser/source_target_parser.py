"""
Support source target parser for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

try:
    from data.models.mapping_model import SourceColumn, SourceMetadata, TargetColumn, TargetMetadata
except ModuleNotFoundError:
    from models import SourceColumn, SourceMetadata, TargetColumn, TargetMetadata


class SourceTargetParser:
    """Parses migration metadata into application structures."""

    def parse_sources(self, folder: Element) -> list[SourceMetadata]:
        """Parse sources using the provided folder."""

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
        """Parse targets using the provided folder."""

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
