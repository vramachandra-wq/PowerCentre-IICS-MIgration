"""
Support xml utils for shared application infrastructure.
Provides configuration, logging, constants, and reusable helpers.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET


class XmlLoader:
    """Encapsulates xml loader behavior for migration workflows."""

    def parse(self, xml_path: Path) -> ET.ElementTree:
        """Parse migration data using the provided xml_path."""

        if not xml_path.exists():
            raise FileNotFoundError(f"XML file not found: {xml_path}")
        if xml_path.suffix.lower() != ".xml":
            raise ValueError(f"Expected an XML file, received: {xml_path}")

        parser = ET.XMLParser()
        return ET.parse(xml_path, parser=parser)
