"""
Module: common/utils/xml_utils.py

Purpose:
    This module supports shared utility functions for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the shared utility functions area and provides reusable helpers used across parsing, validation, and reporting modules. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET


class XmlLoader:
    """Loads PowerCenter XML exports without resolving external DTD references."""

    def parse(self, xml_path: Path) -> ET.ElementTree:
        """
        Executes the parse workflow for shared utility functions.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                xml_path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that provides reusable helpers used across parsing, validation, and reporting modules. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not xml_path.exists():
            raise FileNotFoundError(f"XML file not found: {xml_path}")
        if xml_path.suffix.lower() != ".xml":
            raise ValueError(f"Expected an XML file, received: {xml_path}")

        parser = ET.XMLParser()
        return ET.parse(xml_path, parser=parser)
