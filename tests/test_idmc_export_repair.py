"""Tests for IDMC export repair helpers."""

from __future__ import annotations

import io
import json
import unittest
import zipfile

from business.export.repair_idmc_export import repair_dtemplate_zip


class IdmcExportRepairTests(unittest.TestCase):
    def test_repair_dtemplate_zip_syncs_file_record_size(self) -> None:
        bin_payload = json.dumps(
            {"content": {"name": "SDE_ORA_JobDimension", "$$class": 1}},
            separators=(",", ":"),
        ).encode("utf-8")
        source = io.BytesIO()
        with zipfile.ZipFile(source, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "mappingTemplate.json",
                json.dumps([{"name": "SDE_ORA_JobDimension"}], separators=(",", ":")),
            )
            zf.writestr(
                "fileRecord.json",
                json.dumps(
                    [
                        {
                            "@type": "fileRecord",
                            "id": "@2",
                            "name": "SDE_ORA_JobDimension",
                            "type": "IMFOBJECT",
                            "size": 99999,
                        }
                    ],
                    separators=(",", ":"),
                ),
            )
            zf.writestr("bin/@2.bin", bin_payload)

        repaired_bytes = repair_dtemplate_zip(source.getvalue(), "SDE_ORA_JobDimension")
        with zipfile.ZipFile(io.BytesIO(repaired_bytes)) as zf:
            file_record = json.loads(zf.read("fileRecord.json").decode("utf-8"))[0]
            actual_size = len(zf.read("bin/@2.bin"))

        self.assertEqual(actual_size, file_record["size"])
        self.assertEqual("SDE_ORA_JobDimension", file_record["name"])


if __name__ == "__main__":
    unittest.main()
