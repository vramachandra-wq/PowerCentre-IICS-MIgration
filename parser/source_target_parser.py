from __future__ import annotations

from xml.etree.ElementTree import Element

try:
    from parser.models import SourceColumn, SourceMetadata, TargetColumn, TargetMetadata
except ModuleNotFoundError:
    from models import SourceColumn, SourceMetadata, TargetColumn, TargetMetadata


class SourceTargetParser:
    """Parses folder-level PowerCenter source and target definitions."""

    def parse_sources(self, folder: Element) -> list[SourceMetadata]:
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
