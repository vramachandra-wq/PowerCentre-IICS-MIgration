"""
Module: tests/test_datatype_mapping_engine.py

Purpose:
    This module supports automated regression tests for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the automated regression tests area and verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

import unittest

from business.validation.datatype_mapping_engine import (
    DatatypeMappingEngine,
    map_datatype,
    suggest_datatype_fix,
    validate_datatype,
)


class DatatypeMappingEngineTests(unittest.TestCase):
    """
    Represents the DatatypeMappingEngineTests component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def test_map_number_precision_scale(self) -> None:
        """
        Executes the test_map_number_precision_scale workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        mapped = map_datatype("NUMBER(18,6)")

        self.assertEqual("Decimal", mapped.idmc_type)
        self.assertEqual(18, mapped.precision)
        self.assertEqual(6, mapped.scale)

    def test_validate_varchar2(self) -> None:
        """
        Executes the test_validate_varchar2 workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        result = validate_datatype("VARCHAR2", precision=100, scale=0)

        self.assertTrue(result["valid"])
        self.assertEqual("String", result["mapped_type"])

    def test_suggest_decimal_fix(self) -> None:
        """
        Executes the test_suggest_decimal_fix workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.assertEqual(
            "Retain original precision and scale.",
            suggest_datatype_fix("NUMBER", precision=18, scale=6),
        )

    def test_engine_reports_unknown_type(self) -> None:
        """
        Executes the test_engine_reports_unknown_type workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        engine = DatatypeMappingEngine()
        result = engine.validate_datatype("UNSUPPORTED_TYPE")

        self.assertFalse(result["valid"])
        self.assertTrue(result["issues"])


if __name__ == "__main__":
    unittest.main()
