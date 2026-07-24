"""Reference-shell packages must not copy bloated /SYS manifests from client samples."""

from __future__ import annotations

import io
import json
import unittest
import zipfile
from pathlib import Path

from business.iics.iics_package_generator import (
    PRIMARY_REFERENCE_AGENT_GROUP,
    PRIMARY_REFERENCE_CONNECTION,
    SDE_FLAT_FILE_CONNECTION,
    _load_reference_shell,
    _slim_reference_shell,
)


class ReferenceShellAssetTests(unittest.TestCase):
    def test_slim_sde_shell_keeps_primary_and_flat_file_connections_only(self) -> None:
        ref = Path("reference_packages/iics_success/single_session/SDE_ORA_EmployeeDimension-1784818706860.zip")
        if not ref.exists():
            self.skipTest("reference zip missing")
        slim = _slim_reference_shell(_load_reference_shell(ref), "SDE_ORA_JobDimension")
        conn_names = {
            o["objectName"]
            for o in slim["exported_objects"]
            if o["objectType"] == "Connection"
        }
        agent_names = {
            o["objectName"]
            for o in slim["exported_objects"]
            if o["objectType"] == "AgentGroup"
        }
        self.assertEqual(
            {PRIMARY_REFERENCE_CONNECTION, SDE_FLAT_FILE_CONNECTION},
            conn_names,
        )
        self.assertEqual({PRIMARY_REFERENCE_AGENT_GROUP}, agent_names)
        self.assertEqual(3, len(slim["sys_entries"]))

    def test_reference_dmapplet_shell_has_preview_image(self) -> None:
        out = Path("output/SDE_ORA_JobDimension.zip")
        if not out.exists():
            self.skipTest("run iics-package first")
        with zipfile.ZipFile(out) as zf:
            mp = next(
                n for n in zf.namelist()
                if n.endswith("mplt_SA_ORA_JobDimension.DMAPPLET.zip")
            )
            with zipfile.ZipFile(io.BytesIO(zf.read(mp))) as inner:
                names = inner.namelist()
                records = json.loads(inner.read("fileRecord.json"))
                template = json.loads(inner.read("mappletTemplate.json"))[0]
                imf_size = len(inner.read("bin/@2.bin"))
        self.assertIn("bin/@3.bin", names)
        self.assertEqual("@3", template.get("templateImageId"))
        types = {r.get("type") for r in records}
        self.assertIn("IMAGE", types)
        self.assertIn("IMFOBJECT", types)
        imf = next(r for r in records if r.get("type") == "IMFOBJECT")
        self.assertEqual(imf_size, imf["size"])

    def test_generated_sde_zip_manifest_is_not_bloated(self) -> None:
        out = Path("output/SDE_ORA_JobDimension.zip")
        if not out.exists():
            self.skipTest("run iics-package first")
        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read("exportMetadata.v2.json"))
            names = zf.namelist()
            dt_bytes = zf.read(next(n for n in names if n.endswith("SDE_ORA_JobDimension.DTEMPLATE.zip")))
        sys_rows = [o for o in manifest["exportedObjects"] if o.get("path") == "/SYS"]
        folder_rows = [
            o for o in manifest["exportedObjects"]
            if o.get("path") == "/Explore/RPA_PC_Modernization/Custom_SDE_SupplyChain"
            or (
                o.get("objectType") == "Folder"
                and o.get("objectName") == "Custom_SDE_SupplyChain"
            )
        ]
        self.assertLessEqual(len(sys_rows), 3)
        self.assertEqual(6, len(folder_rows))
        self.assertFalse(any("EmployeeDimension" in n for n in names))
        by_guid = {o["objectGuid"]: o for o in manifest["exportedObjects"]}
        with zipfile.ZipFile(io.BytesIO(dt_bytes)) as inner:
            tpl = json.loads(inner.read("mappingTemplate.json"))[0]
            for ref in tpl.get("references") or []:
                guid = str(ref.get("refObjectId") or "").lstrip("@")
                self.assertIn(guid, by_guid, msg=f"DTEMPLATE ref {guid} missing from manifest")
        oracle = next(
            o for o in manifest["exportedObjects"]
            if o["objectType"] == "Connection" and o["objectName"] == "Orcl_BI_Jacobs_HR_PC2CDI"
        )
        pc_agent = next(
            o for o in manifest["exportedObjects"]
            if o["objectType"] == "AgentGroup" and o["objectName"] == "PC Secure Agent Group"
        )
        self.assertEqual([pc_agent["objectGuid"]], (oracle.get("metadata") or {}).get("objectRefs"))
        with zipfile.ZipFile(out) as zf:
            conn = zipfile.ZipFile(
                io.BytesIO(zf.read("SYS/Orcl_BI_Jacobs_HR_PC2CDI.Connection.zip"))
            )
            runtime = json.loads(conn.read("connection.json"))[0]["runtimeEnvironmentId"]
            self.assertEqual(f"@{pc_agent['objectGuid']}", runtime)
            mtt = zipfile.ZipFile(
                io.BytesIO(next(
                    zf.read(n) for n in zf.namelist()
                    if n.endswith("SDE_ORA_JobDimension.MTT.zip")
                ))
            )
            task = json.loads(mtt.read("mtTask.json"))[0]
            param_blob = json.dumps(task.get("parameters") or [])
            self.assertNotIn("EmployeeDimension", param_blob)
            self.assertIn("W_JOB_DS", param_blob)
            tf = zf.read(next(n for n in names if n.endswith("SDE_ORA_JobDimension.TASKFLOW.xml"))).decode("utf-8")
            self.assertNotIn("SDE-ORA-EmployeeDimension", tf)
            self.assertIn("SDE-ORA-JobDimension", tf)

    def test_generated_sil_zip_manifest_is_not_bloated(self) -> None:
        out = Path("output/SIL_JobDimension.zip")
        if not out.exists():
            self.skipTest("run iics-package first")
        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read("exportMetadata.v2.json"))
        sys_rows = [o for o in manifest["exportedObjects"] if o.get("path") == "/SYS"]
        folder_rows = [
            o for o in manifest["exportedObjects"]
            if o.get("path") == "/Explore/RPA_PC_Modernization/Custom_SDE_SupplyChain"
            or (
                o.get("objectType") == "Folder"
                and o.get("objectName") == "Custom_SDE_SupplyChain"
            )
        ]
        self.assertLessEqual(len(sys_rows), 2)
        self.assertEqual(8, len(folder_rows))


    def test_generated_sde_dtemplate_uses_native_pc_graph(self) -> None:
        out = Path("output/SDE_ORA_JobDimension.zip")
        if not out.exists():
            self.skipTest("run iics-package first")
        with zipfile.ZipFile(out) as zf:
            dt_bytes = zf.read(next(
                n for n in zf.namelist() if n.endswith("SDE_ORA_JobDimension.DTEMPLATE.zip")
            ))
        with zipfile.ZipFile(io.BytesIO(dt_bytes)) as inner:
            fr = json.loads(inner.read("fileRecord.json"))
            imf_path = next(
                f"bin/{r['id']}.bin" for r in fr if r.get("type") == "IMFOBJECT"
            )
            imf = inner.read(imf_path).decode("utf-8")
            names = inner.namelist()
        self.assertIn("bin/@3.bin", names)
        self.assertIn("TmplSource", imf)
        self.assertIn("mplt_BC_ORA_JobDimension", imf)
        self.assertNotIn("EmployeeDimension", imf)

    def test_generated_sil_mapplets_do_not_retain_employee_table_names(self) -> None:
        out = Path("output/SIL_JobDimension.zip")
        if not out.exists():
            self.skipTest("run iics-package first")
        with zipfile.ZipFile(out) as zf:
            for mp_name in ("mplt_SIL_JobDimension", "mplt_SIL_JobDimension_CodeLookup"):
                inner_path = next(
                    n for n in zf.namelist()
                    if n.endswith(f"{mp_name}.DMAPPLET.zip")
                )
                with zipfile.ZipFile(io.BytesIO(zf.read(inner_path))) as inner:
                    imf = inner.read("bin/@2.bin").decode("utf-8")
                self.assertNotIn("W_EMPLOYEE_D", imf, msg=mp_name)
                self.assertNotIn("Exp_W_Employee_D_Defaults", imf, msg=mp_name)
                self.assertNotIn("Exp_W_Employee_D_Defaults", imf, msg=mp_name)
                self.assertIn("W_JOB_D", imf, msg=mp_name)

    def test_generated_sil_main_mapplet_references_sequence_generator(self) -> None:
        out = Path("output/SIL_JobDimension.zip")
        if not out.exists():
            self.skipTest("run iics-package first")
        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read("exportMetadata.v2.json"))
            by_name = {o["objectName"]: o for o in manifest["exportedObjects"]}
            seq_guid = by_name["Seq_W_JOB_D_Wid"]["objectGuid"]
            mp_obj = by_name["mplt_SIL_JobDimension"]
            self.assertIn(seq_guid, mp_obj["metadata"]["objectRefs"])
            inner_path = next(
                n for n in zf.namelist()
                if n.endswith("mplt_SIL_JobDimension.DMAPPLET.zip")
            )
            with zipfile.ZipFile(io.BytesIO(zf.read(inner_path))) as inner:
                template = json.loads(inner.read("mappletTemplate.json"))[0]
                imf = inner.read("bin/@2.bin").decode("utf-8")
            ref_ids = {
                str(ref["refObjectId"]).lstrip("@")
                for ref in template.get("references") or []
            }
            self.assertIn(seq_guid, ref_ids)
            self.assertNotIn("6CKaeTGR9spiGMxHdh8Ua1", imf)
            self.assertIn(seq_guid, imf)


if __name__ == "__main__":
    unittest.main()
