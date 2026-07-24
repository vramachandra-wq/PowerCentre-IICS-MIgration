from __future__ import annotations

import unittest
import io
import json
import shutil
import zipfile
from pathlib import Path

from business.iics.dtemplate_class_registry import DtemplateClassRegistry, REQUIRED_NATIVE_TYPES


TEST_TMP = Path("output/test_temp/dtemplate_registry")


class DtemplateClassRegistryTests(unittest.TestCase):
    def test_registry_reports_missing_required_types(self) -> None:
        tmp = _prepare_test_tmp("missing")
        status = DtemplateClassRegistry(tmp).status()

        self.assertFalse(status.complete)
        self.assertEqual(list(REQUIRED_NATIVE_TYPES), status.missing_types)

    def test_registry_detects_type_specific_dtemplate_zip(self) -> None:
        tmp = _prepare_test_tmp("direct")
        type_dir = tmp / "lookup"
        type_dir.mkdir(parents=True, exist_ok=True)
        prototype = type_dir / "lookup.DTEMPLATE.zip"
        with zipfile.ZipFile(prototype, "w", compression=zipfile.ZIP_DEFLATED) as package:
            package.writestr("mappingTemplate.json", "[]")
            package.writestr("fileRecord.json", "[]")
            package.writestr("bin/@2.bin", "{}")

        status = DtemplateClassRegistry(tmp).status(["lookup"])

        self.assertTrue(status.complete)
        self.assertEqual([], status.missing_types)

    def test_registry_discovers_nested_prototype_from_success_package(self) -> None:
        tmp = _prepare_test_tmp("nested")
        package_path = tmp / "success.zip"
        dtemplate_bytes = io.BytesIO()
        with zipfile.ZipFile(dtemplate_bytes, "w", compression=zipfile.ZIP_DEFLATED) as dtemplate:
            dtemplate.writestr("mappingTemplate.json", "[]")
            dtemplate.writestr("fileRecord.json", "[]")
            dtemplate.writestr(
                "bin/@2.bin",
                json.dumps(
                    {
                        "content": {
                            "transformations": [
                                {
                                    "$$ID": 10,
                                    "$$class": 20,
                                    "name": "LKP_SAMPLE",
                                }
                            ]
                        },
                        "metadata": {
                            "$$classInfo": {
                                "20": "com.informatica.metadata.template.tx.tmpllookup.TmplLookup"
                            }
                        },
                    }
                ),
            )
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED) as package:
            package.writestr("Explore/Project/Folder/Sample.DTEMPLATE.zip", dtemplate_bytes.getvalue())

        status = DtemplateClassRegistry(tmp / "classes", [package_path]).status(["lookup"])

        self.assertTrue(status.complete)
        self.assertIn("Sample.DTEMPLATE.zip", status.prototypes[0].source_path)


if __name__ == "__main__":
    unittest.main()


def _prepare_test_tmp(name: str) -> Path:
    path = TEST_TMP / name
    try:
        shutil.rmtree(path)
    except OSError:
        pass
    path.mkdir(parents=True, exist_ok=True)
    return path
