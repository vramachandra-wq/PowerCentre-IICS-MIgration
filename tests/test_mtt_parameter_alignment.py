"""MTT parameter alignment with mapping Source/Target transforms."""

from __future__ import annotations

import json
import unittest
import zipfile
import io
from pathlib import Path
from xml.etree import ElementTree as ET

from business.iics.iics_package_generator import (
    SDE_FLAT_FILE_CONNECTION,
    _build_dtemplate_zip,
    _build_mtt_zip,
)
from business.parser.mapping_parser import MappingParser
from business.parser.source_target_parser import SourceTargetParser
from business.parser.workflow_parser import WorkflowParser
from data.models.mapping_model import to_plain_dict


class MttParameterAlignmentTests(unittest.TestCase):
    def test_sil_mtt_uses_sq_source_and_session_lookup_generator_params(self) -> None:
        mapping, folder_data, session = self._load("SIL_JobDimension.XML", "SIL_JobDimension")
        seq_guids = {"Seq_W_JOB_D_Wid": "seqGuid1234567890123"}
        mtt = zipfile.ZipFile(
            io.BytesIO(
                _build_mtt_zip(
                    session,
                    "mttGuidSIL123456789012",
                    "dtGuidSIL1234567890123",
                    "agentGuid123456789012",
                    {"DBConnection_OLAP": "connGuid123456789012"},
                    folder_data,
                    "SIL_JobDimension",
                    mapping=mapping,
                    seq_guids=seq_guids,
                )
            )
        )
        task = json.loads(mtt.read("mtTask.json"))[0]
        params = {(p["name"], p["type"]) for p in task["parameters"]}
        self.assertIn(("$Sq_W_JOB_DS$", "SOURCE"), params)
        self.assertIn(("$W_JOB_D$", "TARGET"), params)
        self.assertIn(("$Lkp_W_JOB_D$", "LOOKUP"), params)
        self.assertIn(("$MPLT_GET_ETL_PROC_WID_LKP_ETL_PROC_WID$", "LOOKUP"), params)
        self.assertIn(("$mplt_SIL_JobDimension_Lkp_W_USER_D_Created_By_Wid$", "LOOKUP"), params)
        self.assertIn(("$mplt_SIL_JobDimension_Lkp_W_USER_D_Changed_By_Wid$", "LOOKUP"), params)
        self.assertIn(("$mplt_SIL_JobDimension_Seq_W_JOB_D_Wid$", "GENERATOR"), params)
        self.assertNotIn(("$W_JOB_DS$", "SOURCE"), params)
        code_lookup_params = [p for p in task["parameters"] if "CodeLookup" in p["name"]]
        self.assertEqual([], code_lookup_params)

        dt = zipfile.ZipFile(
            io.BytesIO(_build_dtemplate_zip(mapping, folder_data, "dtGuidSIL1234567890123"))
        )
        binj = json.loads(dt.read("bin/@2.bin"))
        names = {tx["name"] for tx in binj["content"]["transformations"]}
        self.assertIn("Sq_W_JOB_DS", names)
        self.assertNotIn("W_JOB_DS", names)

    def test_sde_mtt_has_mapplet_source_target_and_session_lookups(self) -> None:
        mapping, folder_data, session = self._load("SDE_ORA_JobDimension.XML", "SDE_ORA_JobDimension")
        mtt = zipfile.ZipFile(
            io.BytesIO(
                _build_mtt_zip(
                    session,
                    "mttGuidSDE123456789012",
                    "dtGuidSDE1234567890123",
                    "agentGuid123456789012",
                    {
                        "Orcl_BI_Jacobs_HR_PC2CDI": "connGuid123456789012",
                        "Target": "connGuid123456789012",
                        SDE_FLAT_FILE_CONNECTION: "flatFileConnGuid1234567",
                    },
                    folder_data,
                    "SDE_ORA_JobDimension",
                    mapping=mapping,
                )
            )
        )
        task = json.loads(mtt.read("mtTask.json"))[0]
        params = {(p["name"], p["type"]) for p in task["parameters"]}
        self.assertIn(("$mplt_BC_ORA_JobDimension_Sq_Jobs$", "SOURCE"), params)
        self.assertIn(("$W_JOB_DS$", "TARGET"), params)
        self.assertIn(("$mplt_SA_ORA_JobDimension_Lkp_EEO_Job_Cat$", "LOOKUP"), params)
        self.assertIn(("$mplt_SA_ORA_JobDimension_Lkp_Flsa_Exempt_Stat_Code$", "LOOKUP"), params)
        target = next(p for p in task["parameters"] if p["type"] == "TARGET")
        self.assertEqual("Target", target["runtimeParameterData"]["connectionParameterName"])
        source = next(p for p in task["parameters"] if p["type"] == "SOURCE")
        self.assertEqual(
            "mplt_BC_ORA_JobDimension_Source",
            source["runtimeParameterData"]["connectionParameterName"],
        )
        self.assertNotIn("EXTENDED_SOURCE", {p["type"] for p in task["parameters"]})
        for lk in (
            p for p in task["parameters"]
            if p["type"] == "LOOKUP" and "LookupParameter" in (
                (p.get("runtimeParameterData") or {}).get("connectionParameterName") or ""
            )
        ):
            self.assertEqual("@flatFileConnGuid1234567", lk.get("lookupConnectionId"))
            self.assertEqual("CSVFile", (lk.get("uiProperties") or {}).get("cnxtype"))

        dt = zipfile.ZipFile(
            io.BytesIO(_build_dtemplate_zip(mapping, folder_data, "dtGuidSDE1234567890123"))
        )
        binj = json.loads(dt.read("bin/@2.bin"))
        param_names = {p["name"] for p in binj["content"]["parameters"]}
        self.assertIn("Target", param_names)
        self.assertIn("mplt_BC_ORA_JobDimension_Source", param_names)

    def test_sil_mtt_target_uses_dbconnection_olap(self) -> None:
        mapping, folder_data, session = self._load("SIL_JobDimension.XML", "SIL_JobDimension")
        mtt = zipfile.ZipFile(
            io.BytesIO(
                _build_mtt_zip(
                    session,
                    "mttGuidSIL123456789012",
                    "dtGuidSIL1234567890123",
                    "agentGuid123456789012",
                    {"DBConnection_OLAP": "connGuid123456789012"},
                    folder_data,
                    "SIL_JobDimension",
                    mapping=mapping,
                )
            )
        )
        task = json.loads(mtt.read("mtTask.json"))[0]
        target = next(p for p in task["parameters"] if p["type"] == "TARGET")
        self.assertEqual("DBConnection_OLAP", target["runtimeParameterData"]["connectionParameterName"])
        user_lookups = [
            p for p in task["parameters"]
            if p["type"] == "LOOKUP" and "Lkp_W_USER_D" in p["name"]
        ]
        for lk in user_lookups:
            self.assertIn(
                "DBConnection_OLAP",
                lk["runtimeParameterData"]["connectionParameterName"],
            )

        dt = zipfile.ZipFile(
            io.BytesIO(_build_dtemplate_zip(mapping, folder_data, "dtGuidSIL1234567890123"))
        )
        binj = json.loads(dt.read("bin/@2.bin"))
        param_names = {p["name"] for p in binj["content"]["parameters"]}
        self.assertIn("DBConnection_OLAP", param_names)
        self.assertIn("mplt_SIL_JobDimension_DBConnection_OLAP", param_names)
        self.assertIn("MPLT_GET_ETL_PROC_WID_DBConnection_OLAP", param_names)

    def _load(self, xml_name: str, mapping_name: str) -> tuple[dict, dict, dict | None]:
        root = ET.parse(Path("input_xml") / xml_name).getroot()
        folder = root.find(".//FOLDER")
        assert folder is not None
        stp = SourceTargetParser()
        mp = MappingParser()
        wp = WorkflowParser()
        sources = [to_plain_dict(item) for item in stp.parse_sources(folder)]
        targets = [to_plain_dict(item) for item in stp.parse_targets(folder)]
        mapplets = [to_plain_dict(item) for item in mp.parse_mapplets(folder)]
        sessions = [to_plain_dict(item) for item in wp.parse_sessions(folder)]
        mapping_el = next(
            m for m in folder.findall("MAPPING") if m.attrib.get("NAME") == mapping_name
        )
        mapping = to_plain_dict(mp.parse_mapping(mapping_el))
        session = next(
            (s for s in sessions if s.get("mapping_name") == mapping_name),
            sessions[0] if sessions else None,
        )
        return mapping, {
            "sources": sources,
            "targets": targets,
            "sessions": sessions,
            "mapplets": mapplets,
            "reusable_transformations": [],
        }, session


if __name__ == "__main__":
    unittest.main()
