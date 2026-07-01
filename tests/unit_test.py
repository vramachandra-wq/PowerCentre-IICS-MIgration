import csv
import tempfile
import unittest
from pathlib import Path

from business.validation.datatype_harmonization import DatatypeHarmonizationEngine, MetadataColumn
from business.validation.datatype_mapping_engine import DatatypeMappingEngine
from business.validation.readiness_engine import MigrationReadinessEngine
from business.validation.risk_assessment import RiskAssessmentEngine
from business.validation.validation_engine import ValidationEngine


class DatatypeValidationTests(unittest.TestCase):
    def test_datatype_mapping_rules_map_aliases_and_recommend_decimal_scale(self) -> None:
        engine = DatatypeMappingEngine()

        number = engine.map_datatype("NUMBER(18,6)")
        varchar = engine.map_datatype("VARCHAR2", precision=50)
        unsupported = engine.validate_datatype("POWER_CENTER_ONLY_TYPE")

        self.assertEqual("Decimal", number.idmc_type)
        self.assertEqual(18, number.precision)
        self.assertEqual(6, number.scale)
        self.assertEqual("String", varchar.idmc_type)
        self.assertEqual(50, varchar.length)
        self.assertFalse(unsupported["valid"])
        self.assertIn("Unsupported datatype", unsupported["issues"][0])
        self.assertEqual(
            "Retain original precision and scale.",
            engine.suggest_datatype_fix("NUMBER", precision=18, scale=6),
        )

    def test_datatype_harmonization_detects_core_mismatches(self) -> None:
        engine = DatatypeHarmonizationEngine(output_folder=Path("output"))
        source_columns = [
            MetadataColumn(
                column="AMOUNT",
                datatype="NUMBER",
                precision=18,
                scale=6,
                source_file="sample.XML",
                repository_name="REPO",
                folder_name="FOLDER",
            ),
            MetadataColumn(
                column="DESCRIPTION",
                datatype="VARCHAR2",
                precision=500,
                scale=0,
                source_file="sample.XML",
                repository_name="REPO",
                folder_name="FOLDER",
            ),
        ]
        target_columns = [
            MetadataColumn(
                column="AMOUNT",
                datatype="DOUBLE",
                precision=15,
                scale=0,
                source_file="sample.XML",
                repository_name="REPO",
                folder_name="FOLDER",
            ),
            MetadataColumn(
                column="DESCRIPTION",
                datatype="VARCHAR2",
                precision=100,
                scale=0,
                source_file="sample.XML",
                repository_name="REPO",
                folder_name="FOLDER",
            ),
        ]

        findings = engine.compare_source_target(source_columns, target_columns)
        issue_types = {finding.issue_type for finding in findings}

        self.assertIn("precision_mismatch", issue_types)
        self.assertIn("scale_mismatch", issue_types)
        self.assertIn("decimal_vs_double", issue_types)
        self.assertIn("truncation_risk", issue_types)

    def test_harmonization_flags_lookup_datatype_mismatch_for_lookup_ports(self) -> None:
        engine = DatatypeHarmonizationEngine(output_folder=Path("output"))
        source_columns = [
            MetadataColumn(
                column="CUSTOMER_ID",
                datatype="NUMBER",
                precision=18,
                scale=0,
                source_file="lookup.XML",
                repository_name="REPO",
                folder_name="FOLDER",
            )
        ]
        lookup_ports = [
            MetadataColumn(
                column="CUSTOMER_ID",
                datatype="VARCHAR2",
                precision=18,
                scale=0,
                transformation_name="LKP_CUSTOMER",
                transformation_type="LOOKUP",
                source_file="lookup.XML",
                repository_name="REPO",
                folder_name="FOLDER",
            )
        ]

        findings = engine.compare_transformation_metadata(source_columns, [], lookup_ports)

        self.assertTrue(any(finding.issue_type == "lookup_datatype_mismatch" for finding in findings))

    def test_validation_rules_repository_detects_sql_and_datatype_issues(self) -> None:
        engine = ValidationEngine(output_folder="output")
        self.assertGreaterEqual(len(engine.rules), 40)

        engine.tables = {
            "sql_overrides": [
                {
                    "file_name": "sample.XML",
                    "mapping_name": "SDE_SAMPLE",
                    "context_name": "SQ_SAMPLE",
                    "sql_query": "SELECT TO_DATE(order_date, 'YYYY-MM-DD') FROM ORDERS",
                }
            ]
        }
        sql_rule = {
            "rule_id": "VAL-003",
            "rule_name": "Datetime Parameter Format Conversion",
            "category": "Runtime Rules",
            "severity": "MEDIUM",
            "detection_logic": {
                "type": "sql_pattern",
                "tables": ["sql_overrides"],
                "fields": ["sql_query"],
                "patterns": ["TO_DATE\\s*\\("],
                "case_insensitive": True,
            },
            "recommendation": "Convert datetime formats.",
        }
        datatype_rule = {
            "rule_id": "VAL-012",
            "rule_name": "Scale Mismatch",
            "category": "Datatype Rules",
            "severity": "HIGH",
            "detection_logic": {"type": "datatype_issue", "issue_types": ["scale_mismatch"]},
            "recommendation": "Retain original numeric scale.",
        }
        engine.datatype_findings = [
            {
                "column": "AMOUNT",
                "source": "DECIMAL(18,6)",
                "target": "DECIMAL(18,0)",
                "issue_type": "scale_mismatch",
                "source_file": "sample.XML",
            }
        ]

        sql_issues = engine._evaluate_rule(sql_rule)
        datatype_issues = engine._evaluate_rule(datatype_rule)

        self.assertEqual(1, len(sql_issues))
        self.assertEqual("VAL-003", sql_issues[0].rule_id)
        self.assertEqual(1, len(datatype_issues))
        self.assertEqual("VAL-012", datatype_issues[0].rule_id)

    def test_readiness_scorecard_and_risk_report_use_remaining_issues_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self._write_remediation_reports(output)

            readiness = MigrationReadinessEngine(output_folder=output).build_report()
            risk = RiskAssessmentEngine(output_folder=output).build_report()

            record = next(item for item in readiness if item.mapping_name == "SDE_REMEDIATION")
            risk_record = next(item for item in risk if item.mapping_name == "SDE_REMEDIATION")

            self.assertEqual(3, record.issues_found)
            self.assertEqual(2, record.issues_auto_fixed)
            self.assertEqual(1, record.issues_remaining)
            self.assertGreater(record.readiness_after, record.readiness_before)
            self.assertEqual("mapplet_nesting", risk_record.top_risk_factor)
            self.assertEqual(20, risk_record.risk_score)
            self.assertEqual("LOW", risk_record.risk_level)

    @staticmethod
    def _write_remediation_reports(output: Path) -> None:
        metadata = output / "metadata_tables"
        metadata.mkdir(parents=True, exist_ok=True)
        DatatypeValidationTests._write_csv(
            output / "complexity_classification_report.csv",
            ["Mapping", "XML"],
            [{"Mapping": "SDE_REMEDIATION", "XML": "remediation.XML"}],
        )
        DatatypeValidationTests._write_csv(
            output / "datatype_mismatch_report.csv",
            [
                "column",
                "source",
                "target",
                "severity",
                "recommendation",
                "issue_type",
                "mapping_name",
                "source_file",
            ],
            [
                {
                    "column": "AMOUNT",
                    "source": "DECIMAL(18,6)",
                    "target": "DECIMAL(18,0)",
                    "severity": "HIGH",
                    "recommendation": "Retain original precision and scale.",
                    "issue_type": "scale_mismatch",
                    "mapping_name": "SDE_REMEDIATION",
                    "source_file": "remediation.XML",
                },
                {
                    "column": "CUSTOMER_ID",
                    "source": "NUMBER(18,0)",
                    "target": "VARCHAR2(18)",
                    "severity": "HIGH",
                    "recommendation": "Align lookup datatype.",
                    "issue_type": "lookup_datatype_mismatch",
                    "mapping_name": "SDE_REMEDIATION",
                    "source_file": "remediation.XML",
                },
                {
                    "column": "DESCRIPTION",
                    "source": "VARCHAR2(500)",
                    "target": "VARCHAR2(100)",
                    "severity": "HIGH",
                    "recommendation": "Increase target length.",
                    "issue_type": "truncation_risk",
                    "mapping_name": "SDE_REMEDIATION",
                    "source_file": "remediation.XML",
                },
            ],
        )
        DatatypeValidationTests._write_csv(
            output / "validation_report.csv",
            [
                "Issue",
                "Severity",
                "Recommendation",
                "Auto Fixed",
                "Fix Applied",
                "Before Value",
                "After Value",
                "Status",
                "Asset",
                "Source File",
            ],
            [
                {
                    "Issue": "Mapplet Nesting Detected",
                    "Severity": "HIGH",
                    "Recommendation": "Flatten nested mapplet logic.",
                    "Auto Fixed": "False",
                    "Fix Applied": "",
                    "Before Value": "SDE_REMEDIATION",
                    "After Value": "SDE_REMEDIATION",
                    "Status": "Open",
                    "Asset": "SDE_REMEDIATION",
                    "Source File": "remediation.XML",
                }
            ],
        )
        DatatypeValidationTests._write_csv(
            output / "remediation_report.csv",
            [
                "Issue",
                "Severity",
                "Recommendation",
                "Auto Fixed",
                "Fix Applied",
                "Before Value",
                "After Value",
                "Status",
                "Asset",
                "Approval Required",
                "Manual Remediation Required",
            ],
            [
                {
                    "Issue": "scale_mismatch",
                    "Severity": "HIGH",
                    "Recommendation": "Retain original precision and scale.",
                    "Auto Fixed": "True",
                    "Fix Applied": "copy_source_scale",
                    "Before Value": "DECIMAL(18,0)",
                    "After Value": "DECIMAL(18,6)",
                    "Status": "Resolved",
                    "Asset": "SDE_REMEDIATION",
                    "Approval Required": "False",
                    "Manual Remediation Required": "False",
                },
                {
                    "Issue": "lookup_datatype_mismatch",
                    "Severity": "HIGH",
                    "Recommendation": "Align lookup datatype.",
                    "Auto Fixed": "True",
                    "Fix Applied": "align_lookup_datatype",
                    "Before Value": "VARCHAR2(18)",
                    "After Value": "NUMBER(18,0)",
                    "Status": "Resolved",
                    "Asset": "SDE_REMEDIATION",
                    "Approval Required": "False",
                    "Manual Remediation Required": "False",
                },
                {
                    "Issue": "mapplet_nesting",
                    "Severity": "HIGH",
                    "Recommendation": "Flatten nested mapplet logic.",
                    "Auto Fixed": "False",
                    "Fix Applied": "",
                    "Before Value": "SDE_REMEDIATION",
                    "After Value": "SDE_REMEDIATION",
                    "Status": "Manual Remediation Required",
                    "Asset": "SDE_REMEDIATION",
                    "Approval Required": "False",
                    "Manual Remediation Required": "True",
                },
            ],
        )

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
