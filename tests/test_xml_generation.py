"""
Module: tests/test_xml_generation.py

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

import csv
import tempfile
import unittest
from pathlib import Path

from business.validation.batch_xml_processor import BatchXmlProcessor


class XmlGenerationTests(unittest.TestCase):
    """
    Represents the XmlGenerationTests component in the automated regression tests area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    def test_batch_processor_generates_one_remediated_xml_per_input(self) -> None:
        """
        Executes the test_batch_processor_generates_one_remediated_xml_per_input workflow for automated regression tests.
        
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

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_xml = root / "input_xml"
            output = root / "output"
            input_xml.mkdir()
            output.mkdir()
            (input_xml / "sample.XML").write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE POWERMART SYSTEM "powrmart.dtd">\n'
                '<POWERMART><REPOSITORY><FOLDER>'
                '<TARGET NAME="T"><TARGETFIELD NAME="SALARY" DATATYPE="number" PRECISION="28" SCALE="0"/></TARGET>'
                '</FOLDER></REPOSITORY></POWERMART>',
                encoding="utf-8",
            )
            self._write_csv(
                output / "datatype_mismatch_report.csv",
                ["column", "source", "target", "severity", "recommendation", "issue_type", "transformation", "mapping_name", "source_file"],
                [
                    {
                        "column": "SALARY",
                        "source": "DECIMAL(18,6)",
                        "target": "DECIMAL(28,0)",
                        "severity": "HIGH",
                        "recommendation": "Retain precision and scale.",
                        "issue_type": "precision_mismatch",
                        "transformation": "",
                        "mapping_name": "SDE_PAYROLL",
                        "source_file": "sample.XML",
                    },
                    {
                        "column": "SALARY",
                        "source": "DECIMAL(18,6)",
                        "target": "DECIMAL(28,0)",
                        "severity": "HIGH",
                        "recommendation": "Retain precision and scale.",
                        "issue_type": "scale_mismatch",
                        "transformation": "",
                        "mapping_name": "SDE_PAYROLL",
                        "source_file": "sample.XML",
                    },
                ],
            )

            summary = BatchXmlProcessor(input_folder=input_xml, output_folder=output).run()

            remediated = output / "remediated_xml" / "sample_remediated.xml"
            self.assertTrue(remediated.exists())
            text = remediated.read_text(encoding="utf-8")
            self.assertIn('PRECISION="18"', text)
            self.assertIn('SCALE="6"', text)
            self.assertEqual(1, summary["xml_files"])
            self.assertTrue((output / "reports" / "xml_change_summary.csv").exists())

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        """
        Executes the _write_csv workflow for automated regression tests.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
                fieldnames (object): Value supplied by the caller and used by the workflow.
                rows (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that verifies expected behavior for parser, validation, API, AI recommendation, and reporting workflows. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
