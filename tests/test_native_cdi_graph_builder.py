"""Tests for connector/instance-driven native CDI mapping bins."""

from __future__ import annotations

import json
import unittest
from xml.etree import ElementTree as ET

from business.iics.iics_package_generator import (
    _CLASS_FILTER,
    _CLASS_LOOKUP,
    _CLASS_MAPPLET,
    _build_bin,
    _build_dmapplet_zip,
)
from business.parser.mapping_parser import MappingParser
from business.parser.source_target_parser import SourceTargetParser
from data.models.mapping_model import to_plain_dict
from pathlib import Path
import zipfile
import io


class NativeCdiGraphBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input_dir = Path("input_xml")
        cls.mapping_parser = MappingParser()
        cls.source_target_parser = SourceTargetParser()

    def test_sil_jobdimension_uses_pc_connector_topology(self) -> None:
        mapping, folder_data, mapplet_guids = self._load_mapping(
            "SIL_JobDimension.XML", "SIL_JobDimension"
        )
        payload = json.loads(_build_bin(mapping, folder_data, mapplet_guids).decode("utf-8"))
        content = payload["content"]

        names = {tx["name"] for tx in content["transformations"]}
        self.assertIn("Sq_W_JOB_DS", names)
        self.assertNotIn("W_JOB_DS", names)  # Source Definition omitted when SQ exists
        self.assertIn("Fil_W_JOB_D", names)
        self.assertIn("Lkp_W_JOB_D", names)
        self.assertIn("Upd_W_JOB_D_Ins_Upd", names)
        self.assertIn("W_JOB_D", names)
        self.assertIn("mplt_SIL_JobDimension", names)

        by_name = {tx["name"]: tx for tx in content["transformations"]}
        self.assertEqual(6, by_name["Sq_W_JOB_DS"]["$$class"])  # Source
        self.assertEqual(8, by_name["W_JOB_D"]["$$class"])  # Target
        self.assertEqual(_CLASS_FILTER, by_name["Fil_W_JOB_D"]["$$class"])
        self.assertEqual(_CLASS_LOOKUP, by_name["Lkp_W_JOB_D"]["$$class"])
        self.assertEqual(_CLASS_MAPPLET, by_name["mplt_SIL_JobDimension"]["$$class"])
        self.assertTrue(by_name["mplt_SIL_JobDimension"]["saasMappletId"].startswith("@"))
        self.assertIn("PC_TYPE=Filter", by_name["Fil_W_JOB_D"]["annotations"][0]["body"])
        self.assertIn("PC_TYPE=Lookup Procedure", by_name["Lkp_W_JOB_D"]["annotations"][0]["body"])
        self.assertTrue(by_name["Lkp_W_JOB_D"].get("lookupConditions"))
        self.assertTrue(by_name["Fil_W_JOB_D"].get("filterCondition"))
        write_opts = by_name["W_JOB_D"]["dataAdapter"].get("writeOptions")
        self.assertIsNotNone(write_opts)
        self.assertEqual(["Insert", "Insert"], write_opts["operations"])
        self.assertEqual(24, write_opts["$$class"])
        read_opts = by_name["Sq_W_JOB_DS"]["dataAdapter"].get("readOptions")
        self.assertIsNotNone(read_opts)
        self.assertEqual("false", read_opts["selectDistinct"])
        self.assertEqual(26, read_opts["$$class"])

        link_pairs = {
            (
                self._tx_name(content, link["fromTransformation"]["##ID"]),
                self._tx_name(content, link["toTransformation"]["##ID"]),
            )
            for link in content["links"]
        }
        self.assertNotIn(("W_JOB_DS", "Sq_W_JOB_DS"), link_pairs)
        self.assertIn(("Sq_W_JOB_DS", "Fil_W_JOB_D"), link_pairs)
        self.assertIn(("Fil_W_JOB_D", "Exp_Custom"), link_pairs)
        self.assertIn(("_EXPR_Upd_W_JOB_D_Ins_Upd", "Upd_W_JOB_D_Ins_Upd"), link_pairs)
        self.assertIn(("Upd_W_JOB_D_Ins_Upd", "W_JOB_D"), link_pairs)
        self.assertIn("_EXPR_Upd_W_JOB_D_Ins_Upd", names)
        self.assertEqual(15, len(link_pairs))
        self.assertIn("$$classInfo", payload["metadata"])

    def test_sde_jobdimension_does_not_invent_folder_sources(self) -> None:
        mapping, folder_data, mapplet_guids = self._load_mapping(
            "SDE_ORA_JobDimension.XML", "SDE_ORA_JobDimension"
        )
        payload = json.loads(_build_bin(mapping, folder_data, mapplet_guids).decode("utf-8"))
        content = payload["content"]

        names = {tx["name"] for tx in content["transformations"]}
        self.assertEqual(
            {
                "W_JOB_DS",
                "Exp_W_JOB_DS_Integration_Id",
                "_EXPR_Input_mplt_SA_ORA_JobDimension",
                "_EXPR_W_JOB_DS",
                "X_CUSTOM",
                "mplt_SA_ORA_JobDimension",
                "mplt_BC_ORA_JobDimension",
            },
            names,
        )
        by_name = {tx["name"]: tx for tx in content["transformations"]}
        self.assertEqual(_CLASS_MAPPLET, by_name["mplt_SA_ORA_JobDimension"]["$$class"])
        self.assertEqual(_CLASS_MAPPLET, by_name["mplt_BC_ORA_JobDimension"]["$$class"])
        self.assertTrue(by_name["mplt_SA_ORA_JobDimension"]["saasMappletId"].startswith("@"))
        self.assertTrue(by_name["mplt_BC_ORA_JobDimension"]["saasMappletId"].startswith("@"))
        self.assertTrue(by_name["mplt_SA_ORA_JobDimension"].get("inputGroups"))
        self.assertNotIn("inputGroups", by_name["mplt_BC_ORA_JobDimension"])
        self.assertEqual(
            [{"name": "Output", "input": "false", "output": "true"}],
            [
                {"name": g["name"], "input": g["input"], "output": g["output"]}
                for g in by_name["mplt_BC_ORA_JobDimension"]["groups"]
            ],
        )
        # Must NOT invent SQ_PER_JOBS / SQ_PER_JOB_DEFINITIONS from folder sources.
        self.assertFalse(any(name.startswith("SQ_") for name in names))

        link_pairs = {
            (
                self._tx_name(content, link["fromTransformation"]["##ID"]),
                self._tx_name(content, link["toTransformation"]["##ID"]),
            )
            for link in content["links"]
        }
        self.assertIn(("mplt_BC_ORA_JobDimension", "X_CUSTOM"), link_pairs)
        self.assertIn(("mplt_BC_ORA_JobDimension", "Exp_W_JOB_DS_Integration_Id"), link_pairs)
        self.assertIn(
            ("mplt_BC_ORA_JobDimension", "_EXPR_Input_mplt_SA_ORA_JobDimension"),
            link_pairs,
        )
        self.assertIn(("X_CUSTOM", "_EXPR_Input_mplt_SA_ORA_JobDimension"), link_pairs)
        self.assertNotIn(("X_CUSTOM", "W_JOB_DS"), link_pairs)
        self.assertIn(("Exp_W_JOB_DS_Integration_Id", "_EXPR_Input_mplt_SA_ORA_JobDimension"), link_pairs)
        self.assertIn(("_EXPR_Input_mplt_SA_ORA_JobDimension", "mplt_SA_ORA_JobDimension"), link_pairs)
        self.assertIn(("mplt_SA_ORA_JobDimension", "_EXPR_W_JOB_DS"), link_pairs)
        self.assertIn(("_EXPR_W_JOB_DS", "W_JOB_DS"), link_pairs)
        self.assertEqual(8, len(link_pairs))

    def test_dmapplet_zip_built_for_folder_mapplet(self) -> None:
        _, folder_data, _ = self._load_mapping("SDE_ORA_JobDimension.XML", "SDE_ORA_JobDimension")
        mapplet = next(
            m for m in folder_data["mapplets"] if m["mapplet_name"] == "mplt_SA_ORA_JobDimension"
        )
        raw = _build_dmapplet_zip(mapplet, folder_data, "dmappletGuid12345678901")
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            self.assertIn("mappletTemplate.json", zf.namelist())
            self.assertIn("bin/@2.bin", zf.namelist())
            tmpl = json.loads(zf.read("mappletTemplate.json"))[0]
            self.assertEqual("mappletTemplate", tmpl["@type"])
            self.assertEqual("DMAPPLET", tmpl["documentType"])
            binj = json.loads(zf.read("bin/@2.bin"))
            self.assertEqual("DMAPPLET", binj["content"]["documentType"])
            names = {tx["name"] for tx in binj["content"]["transformations"]}
            self.assertIn("INPUT", names)
            self.assertIn("OUTPUT", names)
            self.assertIn("Exp_Sa_Jobs", names)
            # DMAPPLET classInfo must use ConvTool numbering (Input=6, Output=9).
            ci = binj["metadata"]["$$classInfo"]
            self.assertIn("tmplinput.TmplInput", ci["6"])
            self.assertIn("tmploutput.TmplOutput", ci["9"])
            by_name = {tx["name"]: tx for tx in binj["content"]["transformations"]}
            self.assertEqual(6, by_name["INPUT"]["$$class"])
            self.assertEqual(9, by_name["OUTPUT"]["$$class"])

    def test_codelookup_dmapplet_resolves_folder_reusable_lookups(self) -> None:
        _, folder_data, _ = self._load_mapping("SIL_JobDimension.XML", "SIL_JobDimension")
        mapplet = next(
            m for m in folder_data["mapplets"]
            if m["mapplet_name"] == "mplt_SIL_JobDimension_CodeLookup"
        )
        raw = _build_dmapplet_zip(mapplet, folder_data, "codeLookupGuid1234567890")
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            binj = json.loads(zf.read("bin/@2.bin"))
            by_name = {tx["name"]: tx for tx in binj["content"]["transformations"]}
            lkp = by_name["LKP_CODES_JOB_CODE"]
            self.assertEqual(8, lkp["$$class"])  # TmplLookup in DMAPPLET classInfo
            self.assertGreater(len(lkp.get("fields") or []), 1)
            self.assertTrue(lkp.get("lookupConditions"))

    def _load_mapping(self, xml_name: str, mapping_name: str) -> tuple[dict, dict, dict]:
        root = ET.parse(self.input_dir / xml_name).getroot()
        folder = root.find(".//FOLDER")
        assert folder is not None
        sources = [to_plain_dict(item) for item in self.source_target_parser.parse_sources(folder)]
        targets = [to_plain_dict(item) for item in self.source_target_parser.parse_targets(folder)]
        mapplets = [to_plain_dict(item) for item in self.mapping_parser.parse_mapplets(folder)]
        reusable = [
            to_plain_dict(item)
            for item in self.mapping_parser.parse_reusable_transformations(folder)
        ]
        mapping_el = next(
            m for m in folder.findall("MAPPING") if m.attrib.get("NAME") == mapping_name
        )
        mapping = to_plain_dict(self.mapping_parser.parse_mapping(mapping_el))
        folder_data = {
            "sources": sources,
            "targets": targets,
            "sessions": [],
            "mapplets": mapplets,
            "reusable_transformations": reusable,
        }
        mapplet_guids = {
            mp["mapplet_name"]: f"guid{mp['mapplet_name'][:16]}" for mp in mapplets
        }
        return mapping, folder_data, mapplet_guids

    @staticmethod
    def _tx_name(content: dict, tx_id: int) -> str:
        for tx in content["transformations"]:
            if tx["$$ID"] == tx_id:
                return tx["name"]
        raise AssertionError(f"transformation id {tx_id} not found")


if __name__ == "__main__":
    unittest.main()
