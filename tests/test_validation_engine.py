"""
Module: tests/test_validation_engine.py

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

from business.validation.validation_engine import ValidationEngine


class ValidationEngineTests(unittest.TestCase):
    """
    Represents the ValidationEngineTests component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def test_rules_repository_loads_required_day2_rules(self) -> None:
        """
        Executes the test_rules_repository_loads_required_day2_rules workflow for automated regression tests.
        
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

        engine = ValidationEngine(output_folder="output")

        self.assertGreaterEqual(len(engine.rules), 40)
        self.assertTrue(all("rule_id" in rule for rule in engine.rules))
        self.assertTrue(all("detection_logic" in rule for rule in engine.rules))

    def test_select_columns_handles_nested_functions(self) -> None:
        """
        Executes the test_select_columns_handles_nested_functions workflow for automated regression tests.
        
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

        columns = ValidationEngine._select_columns(
            "select a, concat(b, c) as bc, to_date(d, 'YYYY-MM-DD') as d1 from table_a"
        )

        self.assertEqual(["a", "concat(b, c) as bc", "to_date(d, 'YYYY-MM-DD') as d1"], columns)

    def test_datatype_issue_rule_consumes_day1_findings(self) -> None:
        """
        Executes the test_datatype_issue_rule_consumes_day1_findings workflow for automated regression tests.
        
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

        engine = ValidationEngine(output_folder="output")
        rule = {
            "rule_id": "VAL-012",
            "rule_name": "Scale Mismatch",
            "category": "Datatype Rules",
            "severity": "HIGH",
            "detection_logic": {"type": "datatype_issue", "issue_types": ["scale_mismatch"]},
            "recommendation": "Retain original numeric scale and review rounding behavior.",
        }
        engine.datatype_findings = [
            {
                "column": "SALARY_ANNL",
                "source": "DECIMAL(18,6)",
                "target": "DECIMAL(28,0)",
                "issue_type": "scale_mismatch",
                "source_file": "sample.XML",
            }
        ]

        issues = engine._datatype_issue(rule)

        self.assertEqual(1, len(issues))
        self.assertEqual("VAL-012", issues[0].rule_id)


if __name__ == "__main__":
    unittest.main()
