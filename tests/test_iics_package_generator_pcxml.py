"""Regression tests for generated IICS package native IDMC payloads."""

from __future__ import annotations

import json
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path

from business.iics.iics_package_generator import IICSPackageGenerator


class IICSPackageGeneratorNativeTests(unittest.TestCase):
    """Verify generated DTEMPLATE assets follow the sample native IDMC layout."""

    def setUp(self) -> None:
        self.root = Path.cwd() / ".test_tmp" / f"iics_pcxml_{uuid.uuid4().hex}"
        self.parsed = self.root / "parsed_json"
        self.remediated = self.root / "remediated_xml"
        self.output = self.root / "iics_generated"
        self.parsed.mkdir(parents=True)
        self.remediated.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_generated_dtemplate_uses_sample_file_record_layout(self) -> None:
        self._write_sample_inputs()

        summary = IICSPackageGenerator(
            parsed_json_dir=self.parsed,
            remediated_xml_dir=self.remediated,
            output_dir=self.output,
        ).generate()

        self.assertEqual(2, summary["asset_types"]["DTEMPLATE"])
        with zipfile.ZipFile(summary["output_zip"]) as package:
            dtemplate_path = next(name for name in package.namelist() if name.endswith(".DTEMPLATE.zip"))
            with zipfile.ZipFile(package.open(dtemplate_path)) as dtemplate:
                mapping_template = json.loads(dtemplate.read("mappingTemplate.json").decode("utf-8"))
                file_record = json.loads(dtemplate.read("fileRecord.json").decode("utf-8"))

        self.assertEqual("@3", mapping_template[0]["templateId"])
        self.assertEqual("@2", mapping_template[0]["mappingPreviewFileRecordId"])
        self.assertEqual(["IMAGE", "IMFOBJECT"], [row["type"] for row in file_record])

    def test_scoped_primary_workflow_package_contains_only_runtime_objects(self) -> None:
        self._write_sample_inputs(include_helper=True)

        summary = IICSPackageGenerator(
            parsed_json_dir=self.parsed,
            remediated_xml_dir=self.remediated,
            output_dir=self.output,
            source_file_filter="customer.XML",
            workflow_name_filter="WF_CUSTOMER",
            primary_workflow_sessions_only=True,
        ).generate()

        self.assertEqual(5, summary["total_assets"])
        self.assertEqual(2, summary["asset_types"]["DTEMPLATE"])
        self.assertEqual(2, summary["asset_types"]["MTT"])
        self.assertEqual(1, summary["asset_types"]["TASKFLOW"])

    def _write_sample_inputs(self, include_helper: bool = False) -> None:
        sessions = [
            {"session_name": "WF_CUSTOMER_LOAD_A", "mapping_name": "WF_CUSTOMER_LOAD_A", "attributes": {}},
            {"session_name": "WF_CUSTOMER_LOAD_B", "mapping_name": "WF_CUSTOMER_LOAD_B", "attributes": {}},
        ]
        mappings = [
            {
                "mapping_name": "WF_CUSTOMER_LOAD_A",
                "transformations": [{"transformation_name": "EXP_CUSTOMER_A", "transformation_type": "Expression", "ports": []}],
                "connectors": [],
                "instances": [],
                "sql_overrides": [],
            },
            {
                "mapping_name": "WF_CUSTOMER_LOAD_B",
                "transformations": [{"transformation_name": "EXP_CUSTOMER_B", "transformation_type": "Expression", "ports": []}],
                "connectors": [],
                "instances": [],
                "sql_overrides": [],
            },
        ]
        if include_helper:
            sessions.append({"session_name": "HELPER_TRUNCATE", "mapping_name": "HELPER_TRUNCATE", "attributes": {}})
            mappings.append(
                {
                    "mapping_name": "HELPER_TRUNCATE",
                    "transformations": [],
                    "connectors": [],
                    "instances": [],
                    "sql_overrides": [],
                }
            )
        payload = {
            "repository": {"name": "REP"},
            "folders": [
                {
                    "folder_name": "FOLDER",
                    "sources": [{"source_name": "SRC_CUSTOMER", "columns": [{"column_name": "CUSTOMER_ID", "datatype": "integer"}]}],
                    "targets": [{"target_name": "TGT_CUSTOMER", "columns": [{"column_name": "CUSTOMER_ID", "datatype": "integer"}]}],
                    "sessions": sessions,
                    "workflows": [{"workflow_name": "WF_CUSTOMER"}],
                    "mappings": mappings,
                }
            ],
        }
        (self.parsed / "customer.json").write_text(json.dumps(payload), encoding="utf-8")
        for mapping in mappings:
            (self.remediated / f"{mapping['mapping_name']}_remediated.xml").write_text("<POWERMART />", encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
