"""Unit tests for IDMC review package generation."""

from __future__ import annotations

import csv
import json
import shutil
import unittest
import uuid
import zipfile
from pathlib import Path

from business.iics.checksum_utils import parse_checksum_file
from export.checksum_generator import ChecksumGenerator
from export.idmc_review_package_generator import IDMCReviewPackageGenerator
from export.mapping_package_generator import MappingPackageGenerator
from export.metadata_generator import MetadataGenerator
from export.package_builder import ReviewSession, ReviewWorkflow
from export.taskflow_generator import TaskflowGenerator
from export.zip_generator import ZipGenerator


class IDMCReviewPackageTests(unittest.TestCase):
    """Verify IDMC review package assets are generated from existing metadata."""

    def setUp(self) -> None:
        self.root = Path.cwd() / ".test_tmp" / f"idmc_review_{uuid.uuid4().hex}"
        self.output = self.root / "output"
        self.output.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_taskflow_generation_preserves_multiple_sessions(self) -> None:
        workflow = self._workflow()
        asset = TaskflowGenerator().generate(workflow, self.root / "taskflows")
        content = (self.root / "taskflows" / "WF_CUSTOMER.TASKFLOW.xml").read_text(encoding="utf-8")

        self.assertEqual("Workflow", asset.asset_type)
        self.assertIn('name="S_LOAD_CUSTOMER"', content)
        self.assertIn('mapping="M_CUSTOMER"', content)
        self.assertIn('name="S_LOAD_ORDER"', content)
        self.assertIn('mapping="M_ORDER"', content)

    def test_mapping_package_generation_writes_review_metadata_zip(self) -> None:
        workflow = self._workflow()
        session = workflow.sessions[0]
        generator = MappingPackageGenerator(
            mappings={"M_CUSTOMER": {"mapping_name": "M_CUSTOMER"}},
            transformations={"M_CUSTOMER": [{"transformation_name": "EXP_CUSTOMER"}]},
            ports={"M_CUSTOMER": [{"port_name": "CUSTOMER_ID"}]},
            instances={"M_CUSTOMER": [{"instance_name": "SRC_CUSTOMER"}]},
            connectors={"M_CUSTOMER": [{"from_instance": "SRC_CUSTOMER", "to_instance": "EXP_CUSTOMER"}]},
            sources_by_file={"customer.XML": [{"source_name": "CUSTOMER"}]},
            targets_by_file={"customer.XML": [{"target_name": "CUSTOMER_T"}]},
        )

        asset = generator.generate(workflow, session, self.root / "mapping_packages")

        self.assertEqual("Mapping", asset.asset_type)
        with zipfile.ZipFile(self.root / "mapping_packages" / "WF_CUSTOMER" / "S_LOAD_CUSTOMER" / "M_CUSTOMER.MTT.zip") as archive:
            payload = json.loads(archive.read("mapping.json").decode("utf-8"))
            self.assertTrue(payload["reviewOnly"])
            self.assertEqual("S_LOAD_CUSTOMER", payload["session"]["name"])
            self.assertEqual("M_CUSTOMER", payload["mapping"]["mapping_name"])

    def test_metadata_generation_writes_project_folder_and_contents(self) -> None:
        generator = MetadataGenerator()
        workflow = self._workflow()
        assets = [
            generator.write_project_metadata(self.root / "Explore", [{"name": "REP"}], [workflow]),
            generator.write_folder_metadata(self.root / "Explore", [{"folder_name": "FOLDER"}]),
        ]
        assets.append(generator.write_export_metadata(self.root, assets))
        contents_asset = generator.write_contents_csv(self.root, assets)

        self.assertTrue((self.root / "Explore" / "Project.json").exists())
        self.assertTrue((self.root / "Explore" / "Folder.json").exists())
        self.assertEqual("Package Contents", contents_asset.asset_type)
        rows = self._read_csv(self.root / "ContentsofExportPackage.csv")
        self.assertEqual(3, len(rows))

    def test_checksum_generation_includes_generated_files(self) -> None:
        (self.root / "Explore").mkdir()
        (self.root / "Explore" / "Project.json").write_text("{}", encoding="utf-8")

        checksum_path = ChecksumGenerator().write(self.root)

        checksums = parse_checksum_file(checksum_path.read_text(encoding="utf-8"))
        self.assertIn("Explore/Project.json", checksums)

    def test_review_package_generator_creates_zip_with_expected_structure(self) -> None:
        self._write_sample_output()

        summary = IDMCReviewPackageGenerator(output_folder=self.output).build()

        zip_path = Path(summary["zip_path"])
        self.assertTrue(zip_path.exists())
        with zipfile.ZipFile(zip_path) as archive:
            names = set(archive.namelist())
            self.assertIn("Explore/Project.json", names)
            self.assertIn("Explore/Folder.json", names)
            self.assertIn("Explore/Taskflows/WF_CUSTOMER.TASKFLOW.xml", names)
            self.assertIn("Explore/MappingPackages/WF_CUSTOMER/S_LOAD_CUSTOMER/M_CUSTOMER.MTT.zip", names)
            self.assertIn("Explore/RemediatedXML/customer_remediated.xml", names)
            self.assertIn("SYS/ConnectionMetadata.json", names)
            self.assertIn("SYS/AgentGroupMetadata.json", names)
            self.assertIn("exportMetadata.v2.json", names)
            self.assertIn("ContentsofExportPackage.csv", names)
            self.assertIn("exportPackage.chksum", names)

    def test_zip_generator_writes_single_zip(self) -> None:
        package_root = self.root / "package"
        (package_root / "Explore").mkdir(parents=True)
        (package_root / "Explore" / "Project.json").write_text("{}", encoding="utf-8")

        zip_path = ZipGenerator().write(package_root, self.root / "Migration_Review_Package.zip")

        self.assertTrue(zip_path.exists())
        with zipfile.ZipFile(zip_path) as archive:
            self.assertEqual(["Explore/Project.json"], archive.namelist())

    def _workflow(self) -> ReviewWorkflow:
        return ReviewWorkflow(
            workflow_name="WF_CUSTOMER",
            folder_name="FOLDER",
            repository_name="REP",
            file_name="customer.XML",
            server_name="AGENT",
            sessions=[
                ReviewSession("S_LOAD_CUSTOMER", "M_CUSTOMER", "FOLDER", "REP", "customer.XML"),
                ReviewSession("S_LOAD_ORDER", "M_ORDER", "FOLDER", "REP", "customer.XML"),
            ],
        )

    def _write_sample_output(self) -> None:
        metadata = self.output / "metadata_tables"
        metadata.mkdir(parents=True)
        self._write_csv(
            metadata / "workflows.csv",
            ["file_name", "repository_name", "folder_name", "workflow_name", "server_name"],
            [{"file_name": "customer.XML", "repository_name": "REP", "folder_name": "FOLDER", "workflow_name": "WF_CUSTOMER", "server_name": "AGENT"}],
        )
        self._write_csv(
            metadata / "sessions.csv",
            ["file_name", "repository_name", "folder_name", "session_name", "mapping_name"],
            [{"file_name": "customer.XML", "repository_name": "REP", "folder_name": "FOLDER", "session_name": "S_LOAD_CUSTOMER", "mapping_name": "M_CUSTOMER"}],
        )
        self._write_csv(
            metadata / "mappings.csv",
            ["file_name", "repository_name", "folder_name", "mapping_name"],
            [{"file_name": "customer.XML", "repository_name": "REP", "folder_name": "FOLDER", "mapping_name": "M_CUSTOMER"}],
        )
        for name, field in [
            ("transformations", "transformation_name"),
            ("ports", "port_name"),
            ("instances", "instance_name"),
            ("connectors", "from_instance"),
        ]:
            self._write_csv(metadata / f"{name}.csv", ["file_name", "mapping_name", field], [{"file_name": "customer.XML", "mapping_name": "M_CUSTOMER", field: "A"}])
        self._write_csv(metadata / "sources.csv", ["file_name", "repository_name", "folder_name", "source_name", "database_type"], [{"file_name": "customer.XML", "repository_name": "REP", "folder_name": "FOLDER", "source_name": "SRC", "database_type": "Oracle"}])
        self._write_csv(metadata / "targets.csv", ["file_name", "repository_name", "folder_name", "target_name", "database_type"], [{"file_name": "customer.XML", "repository_name": "REP", "folder_name": "FOLDER", "target_name": "TGT", "database_type": "Oracle"}])
        self._write_csv(metadata / "folders.csv", ["file_name", "repository_name", "folder_name"], [{"file_name": "customer.XML", "repository_name": "REP", "folder_name": "FOLDER"}])
        self._write_csv(metadata / "repositories.csv", ["file_name", "name"], [{"file_name": "customer.XML", "name": "REP"}])
        remediated = self.output / "remediated_xml"
        remediated.mkdir()
        (remediated / "customer_remediated.xml").write_text("<POWERMART />", encoding="utf-8")

    @staticmethod
    def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        with path.open("r", newline="", encoding="utf-8") as csv_file:
            return list(csv.DictReader(csv_file))


if __name__ == "__main__":
    unittest.main()
