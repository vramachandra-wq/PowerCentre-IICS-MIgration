"""
Support mapping parser for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

try:
    from data.models.mapping_model import (
        ConnectorMetadata,
        InstanceMetadata,
        MappingMetadata,
        MappletMetadata,
        TransformationMetadata,
    )
    from business.parser.transformation_parser import TransformationParser
except ModuleNotFoundError:
    from models import ConnectorMetadata, InstanceMetadata, MappingMetadata, MappletMetadata
    from transformation_parser import TransformationParser


class MappingParser:
    """Parses migration metadata into application structures."""

    def __init__(self, transformation_parser: TransformationParser | None = None) -> None:
        """Initialize migration data using the provided transformation_parser."""

        self.transformation_parser = transformation_parser or TransformationParser()

    def parse_mappings(self, folder: Element) -> list[MappingMetadata]:
        """Parse mappings using the provided folder."""

        return [self.parse_mapping(mapping) for mapping in folder.findall("MAPPING")]

    def parse_mapplets(self, folder: Element) -> list[MappletMetadata]:
        """Parse folder-level MAPPLET definitions (same graph shape as MAPPING)."""

        return [self.parse_mapplet(mapplet) for mapplet in folder.findall("MAPPLET")]

    def parse_reusable_transformations(self, folder: Element) -> list[TransformationMetadata]:
        """Parse folder-level reusable TRANSFORMATION defs referenced by mapplet instances."""

        reusable: list[TransformationMetadata] = []
        for item in folder.findall("TRANSFORMATION"):
            if str(item.attrib.get("REUSABLE", "")).upper() != "YES":
                continue
            reusable.append(self.transformation_parser.parse_transformation(item))
        return reusable

    def parse_mapping(self, mapping: Element) -> MappingMetadata:
        """Parse mapping using the provided mapping."""

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

    def parse_mapplet(self, mapplet: Element) -> MappletMetadata:
        """Parse a folder-level MAPPLET element like a mapping graph."""

        transformations = self.transformation_parser.parse_transformations(mapplet)
        connectors = self._parse_connectors(mapplet)
        instances = self._parse_instances(mapplet)
        return MappletMetadata(
            mapplet_name=mapplet.attrib.get("NAME", ""),
            is_valid=mapplet.attrib.get("ISVALID", ""),
            transformation_count=len(transformations),
            transformations=transformations,
            connectors=connectors,
            instances=instances,
            sql_overrides=self.transformation_parser.parse_sql_overrides(mapplet),
        )

    @staticmethod
    def _parse_connectors(mapping: Element) -> list[ConnectorMetadata]:
        """Parse connectors using the provided mapping."""

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
        """Parse instances using the provided mapping."""

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
