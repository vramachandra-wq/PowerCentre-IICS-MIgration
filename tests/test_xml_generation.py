"""
Support test xml generation for automated regression coverage.
Verifies migration parsing, validation, API, and AI behavior.
"""

import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from business.validation.batch_xml_processor import BatchXmlProcessor
from business.validation.export_metadata_builder import ExportMetadataBuilder


class XmlGenerationTests(unittest.TestCase):
    """Encapsulates xml generation tests behavior for migration workflows."""

    def test_batch_processor_generates_one_remediated_xml_per_input(self) -> None:
        """Verify batch processor generates one remediated xml per input behavior."""

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

    def test_export_metadata_builder_merges_multiple_remediated_xml_files(self) -> None:
        """Verify all remediated XML files merge into one exportMetadata JSON file."""

        source_dir = Path("output/remediated_xml")
        if not source_dir.exists():
            self.skipTest("Remediated XML folder is not available.")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remediated = root / "output" / "remediated_xml"
            remediated.mkdir(parents=True)
            selected = sorted(source_dir.glob("*_remediated.xml"))[:3]
            if len(selected) < 3:
                self.skipTest("At least three remediated XML files are required.")
            for xml_file in selected:
                shutil.copy2(xml_file, remediated / xml_file.name)

            summary = ExportMetadataBuilder(output_folder=root / "output").build_and_write()
            output_file = Path(summary["output_file"])
            self.assertTrue(output_file.exists())
            payload = json.loads(output_file.read_text(encoding="utf-8"))
            self.assertIn("exportedObjects", payload)
            self.assertEqual(3, summary["xml_files"])
            self.assertGreaterEqual(summary["exported_objects"], 11)
            self.assertEqual(1, len(list((root / "output").glob("exportMetadata.v2.json"))))

    def test_export_metadata_builder_supports_all_available_remediated_files(self) -> None:
        """Verify dynamic processing for the full remediated XML set."""

        source_dir = Path("output/remediated_xml")
        if not source_dir.exists():
            self.skipTest("Remediated XML folder is not available.")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remediated = root / "output" / "remediated_xml"
            remediated.mkdir(parents=True)
            xml_files = sorted(source_dir.glob("*_remediated.xml"))
            for xml_file in xml_files:
                shutil.copy2(xml_file, remediated / xml_file.name)

            summary = ExportMetadataBuilder(output_folder=root / "output").build_and_write()
            payload = json.loads(Path(summary["output_file"]).read_text(encoding="utf-8"))
            self.assertEqual(len(xml_files), summary["xml_files"])
            self.assertGreaterEqual(summary["mapping_records"], summary["xml_files"])
            self.assertGreater(len(payload["exportedObjects"]), summary["mapping_records"])

    @staticmethod
    def _reference_schema(value: object) -> object:
        if isinstance(value, dict):
            return {key: XmlGenerationTests._reference_schema(value[key]) for key in sorted(value)}
        if isinstance(value, list):
            if not value:
                return []
            if isinstance(value[0], dict):
                return [XmlGenerationTests._reference_schema(value[0])]
            return []
        if value is None:
            return None
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return 0
        if isinstance(value, float):
            return 0.0
        return ""

    def test_export_metadata_matches_reference_schema(self) -> None:
        """Verify consolidated export JSON matches the reference exportMetadata schema."""

        reference_path = Path(r"d:\Downloads\Custom_SDE_PBCS_Export 1\exportMetadata.v2.json")
        if not reference_path.exists():
            self.skipTest("Reference exportMetadata file is not available.")

        source_dir = Path("output/remediated_xml")
        if not source_dir.exists():
            self.skipTest("Remediated XML folder is not available.")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remediated = root / "output" / "remediated_xml"
            remediated.mkdir(parents=True)
            for xml_file in sorted(source_dir.glob("*_remediated.xml"))[:3]:
                shutil.copy2(xml_file, remediated / xml_file.name)

            summary = ExportMetadataBuilder(output_folder=root / "output").build_and_write()
            generated = json.loads(Path(summary["output_file"]).read_text(encoding="utf-8"))
            reference = json.loads(reference_path.read_text(encoding="utf-8"))
            self.assertEqual(set(reference.keys()), set(generated.keys()))
            self.assertEqual(
                self._reference_schema(reference["exportedObjects"][0]),
                self._reference_schema(generated["exportedObjects"][0]),
            )
            for obj in generated["exportedObjects"]:
                self.assertIn("objectGuid", obj)
                self.assertIn("objectName", obj)
                self.assertIn("objectType", obj)
                self.assertIn("path", obj)
                self.assertIn("metadata", obj)
                self.assertIn("modelVersion", obj["metadata"])
                self.assertIn("additionalInfo", obj["metadata"])

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        """Verify write csv behavior."""

        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
