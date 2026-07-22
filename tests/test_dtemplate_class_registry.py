from __future__ import annotations

import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from business.iics.dtemplate_class_registry import DtemplateClassRegistry, REQUIRED_NATIVE_TYPES


class DtemplateClassRegistryTests(unittest.TestCase):
    def test_registry_reports_missing_required_types(self) -> None:
        with TemporaryDirectory() as tmp:
            status = DtemplateClassRegistry(tmp).status()

        self.assertFalse(status.complete)
        self.assertEqual(list(REQUIRED_NATIVE_TYPES), status.missing_types)

    def test_registry_detects_type_specific_dtemplate_zip(self) -> None:
        with TemporaryDirectory() as tmp:
            type_dir = Path(tmp) / "lookup"
            type_dir.mkdir(parents=True)
            prototype = type_dir / "lookup.DTEMPLATE.zip"
            with zipfile.ZipFile(prototype, "w", compression=zipfile.ZIP_DEFLATED) as package:
                package.writestr("mappingTemplate.json", "[]")
                package.writestr("fileRecord.json", "[]")
                package.writestr("bin/@2.bin", "{}")

            status = DtemplateClassRegistry(tmp).status(["lookup"])

        self.assertTrue(status.complete)
        self.assertEqual([], status.missing_types)


if __name__ == "__main__":
    unittest.main()
