from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET


class XmlLoader:
    """Loads PowerCenter XML exports without resolving external DTD references."""

    def parse(self, xml_path: Path) -> ET.ElementTree:
        if not xml_path.exists():
            raise FileNotFoundError(f"XML file not found: {xml_path}")
        if xml_path.suffix.lower() != ".xml":
            raise ValueError(f"Expected an XML file, received: {xml_path}")

        parser = ET.XMLParser()
        return ET.parse(xml_path, parser=parser)
