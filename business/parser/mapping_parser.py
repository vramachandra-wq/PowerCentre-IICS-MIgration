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
        self.transformation_parser = transformation_parser or TransformationParser()

    def parse_mappings(self, folder: Element) -> list[MappingMetadata]:
        return [self.parse_mapping(mapping) for mapping in folder.findall("MAPPING")]

    def parse_mapping(self, mapping: Element) -> MappingMetadata:
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
