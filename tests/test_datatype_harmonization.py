import unittest
from pathlib import Path
from types import SimpleNamespace

from business.validation.datatype_harmonization import DatatypeHarmonizationEngine


class DatatypeHarmonizationTests(unittest.TestCase):
    def test_compare_source_target_detects_precision_and_scale_mismatch(self) -> None:
        engine = DatatypeHarmonizationEngine(output_folder=Path("output"))
        source = [
            SimpleNamespace(
                column="SALARY_ANNL",
                datatype="NUMBER",
                precision=18,
                scale=6,
                source_file="sample.XML",
                repository_name="REPO",
                folder_name="FOLDER",
                mapping_name="",
                transformation_name="",
            )
        ]
        target = [
            SimpleNamespace(
                column="SALARY_ANNL",
                datatype="NUMBER",
                precision=28,
                scale=0,
                source_file="sample.XML",
                repository_name="REPO",
                folder_name="FOLDER",
                mapping_name="",
                transformation_name="",
            )
        ]

        findings = engine.compare_source_target(source, target)

        self.assertTrue(any(finding.issue_type == "precision_mismatch" for finding in findings))
        self.assertTrue(any(finding.issue_type == "scale_mismatch" for finding in findings))
        self.assertTrue(any(finding.severity == "HIGH" for finding in findings))


if __name__ == "__main__":
    unittest.main()
