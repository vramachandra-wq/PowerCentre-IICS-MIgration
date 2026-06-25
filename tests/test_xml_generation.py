import csv
import tempfile
import unittest
from pathlib import Path

from business.validation.batch_xml_processor import BatchXmlProcessor


class XmlGenerationTests(unittest.TestCase):
    def test_batch_processor_generates_one_remediated_xml_per_input(self) -> None:
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
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
