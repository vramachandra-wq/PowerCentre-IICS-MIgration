"""
Support transformation parser for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

try:
    from data.models.mapping_model import SqlOverrideMetadata, TransformationMetadata, TransformationPort
except ModuleNotFoundError:
    from models import SqlOverrideMetadata, TransformationMetadata, TransformationPort


class TransformationParser:
    """Parses migration metadata into application structures."""

    SQL_OVERRIDE_NAMES = {"Sql Query", "SQL Query"}

    def parse_transformations(self, mapping: Element) -> list[TransformationMetadata]:
        """Parse transformations using the provided mapping."""

        return [self.parse_transformation(item) for item in mapping.findall("TRANSFORMATION")]

    def parse_transformation(self, transformation: Element) -> TransformationMetadata:
        """Parse transformation using the provided transformation."""

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
        """Parse sql overrides using the provided mapping."""

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
        """Parse attributes using the provided transformation."""

        return {
            item.attrib.get("NAME", ""): item.attrib.get("VALUE", "")
            for item in self._attribute_elements(transformation)
            if item.attrib.get("NAME")
        }

    @staticmethod
    def _attribute_elements(parent: Element) -> list[Element]:
        """Handle attribute elements using the provided parent."""

        return [*parent.findall("TABLEATTRIBUTE"), *parent.findall("ATTRIBUTE")]
