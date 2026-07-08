"""
Regression tests for combined IDMC export package generation.
"""

import json
import logging
import unittest
import uuid
import zipfile
from pathlib import Path

from business.export.idmc_export_package import IdmcExportPackageGenerator
from common.config.config import AppConfig, DatabaseConfig, LoggingConfig, PathConfig


class IdmcExportPackageTests(unittest.TestCase):
    """Verify IDMC export package generation behavior."""

    def test_generator_builds_one_combined_zip_for_all_remediated_xml(self) -> None:
        """Verify combined export ZIP contains artifacts for every discovered XML."""

        root = Path.cwd() / ".test_tmp" / f"idmc_export_package_test_{uuid.uuid4().hex}"
        remediated = root / "output" / "remediated_xml"
        remediated.mkdir(parents=True)
        self._write_xml(remediated / "First_remediated.xml", "m_First")
        self._write_xml(remediated / "Second_remediated.xml", "m_Second")

        config = self._config(root)
        summary = IdmcExportPackageGenerator(
            config=config,
            logger=logging.getLogger("test_idmc_export_package"),
            remediated_folder=remediated,
            output_folder=root / "output",
        ).generate()

        package_path = Path(summary.package_path)
        self.assertTrue(package_path.exists())
        self.assertEqual(2, summary.input_xml_count)
        self.assertEqual(2, summary.mapping_count)

        with zipfile.ZipFile(package_path) as package:
            names = set(package.namelist())
            self.assertIn("Explore/BIAINFADEV2_FLEX.Project.json", names)
            self.assertIn("Explore/BIAINFADEV2_FLEX/Custom_Project.Folder.json", names)
            self.assertIn("SYS/DBConnection_OLAP_Oracle.Connection.zip", names)
            self.assertIn("SYS/PC Secure Agent Group.AgentGroup.zip", names)
            for mapping_name in ("m_First", "m_Second"):
                base = f"Explore/BIAINFADEV2_FLEX/Custom_Project/{mapping_name}"
                self.assertIn(f"{base}.DTEMPLATE.zip", names)
                self.assertIn(f"{base}.MTT.zip", names)
                self.assertIn(f"{base}.TASKFLOW.xml", names)

            metadata = json.loads(package.read("exportMetadata.v2.json"))
            exported = metadata["exportedObjects"]
            self.assertEqual(10, len(exported))
            self.assertEqual(
                {"m_First", "m_Second"},
                {item["objectName"] for item in exported if item["objectType"] == "MTT"},
            )

    @staticmethod
    def _write_xml(path: Path, mapping_name: str) -> None:
        path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<POWERMART REPOSITORY_VERSION="188.97">'
            '<REPOSITORY NAME="Repo" VERSION="188" CODEPAGE="UTF-8" DATABASETYPE="Oracle">'
            '<FOLDER NAME="Folder">'
            '<SOURCE NAME="SRC" DATABASETYPE="Oracle" OWNERNAME="dbo">'
            '<SOURCEFIELD NAME="ID" DATATYPE="number" PRECISION="10" SCALE="0"/>'
            '</SOURCE>'
            '<TARGET NAME="TGT" DATABASETYPE="Oracle">'
            '<TARGETFIELD NAME="ID" DATATYPE="number" PRECISION="10" SCALE="0"/>'
            '</TARGET>'
            f'<MAPPING NAME="{mapping_name}" ISVALID="YES">'
            '<INSTANCE NAME="SRC" TYPE="SOURCE" TRANSFORMATION_NAME="SRC" TRANSFORMATION_TYPE="Source Definition" REUSABLE="NO"/>'
            '<INSTANCE NAME="TGT" TYPE="TARGET" TRANSFORMATION_NAME="TGT" TRANSFORMATION_TYPE="Target Definition" REUSABLE="NO"/>'
            '<CONNECTOR FROMINSTANCE="SRC" FROMFIELD="ID" FROMINSTANCETYPE="Source Definition" '
            'TOINSTANCE="TGT" TOFIELD="ID" TOINSTANCETYPE="Target Definition"/>'
            '</MAPPING>'
            f'<SESSION NAME="s_{mapping_name}" MAPPINGNAME="{mapping_name}" ISVALID="YES" REUSABLE="NO">'
            '<ATTRIBUTE NAME="Pushdown Optimization" VALUE="None"/>'
            '</SESSION>'
            '</FOLDER>'
            '</REPOSITORY>'
            '</POWERMART>',
            encoding="utf-8",
        )

    @staticmethod
    def _config(root: Path) -> AppConfig:
        return AppConfig(
            database=DatabaseConfig(
                host="localhost",
                port=3306,
                username="user",
                password="password",
                database="db",
                driver="mysql",
            ),
            paths=PathConfig(
                xml_folder=str(root / "input_xml"),
                output_folder=str(root / "output"),
                log_folder=str(root / "logs"),
            ),
            logging=LoggingConfig(level="INFO", file_name="test.log", max_bytes=1024, backup_count=1),
        )


if __name__ == "__main__":
    unittest.main()
