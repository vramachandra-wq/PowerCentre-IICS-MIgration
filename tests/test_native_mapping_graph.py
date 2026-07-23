from __future__ import annotations

import unittest
import zipfile
import json
import io
from pathlib import Path

from business.export.idmc_export_package import generate_idmc_export_package
from business.iics.native_mapping_graph import graph_from_xml_file
from common.config.config import AppConfig, DatabaseConfig, LoggingConfig, PathConfig


class NativeMappingGraphTests(unittest.TestCase):
    def test_sde_visual_graph_matches_expected_edges(self) -> None:
        graph = graph_from_xml_file(
            Path("output/remediated_xml/SDE_ORA_JobDimension_remediated.xml"),
            "SDE_ORA_JobDimension",
            visual_overrides=True,
        )
        edges = {(edge.from_node, edge.to_node) for edge in graph.edges}

        self.assertGreaterEqual(len(graph.nodes), 7)
        self.assertIn(("mplt_BC_ORA_JobDimension", "_EXPR_Exp_W_JOB_DS_Integration_Id"), edges)
        self.assertIn(("_EXPR_Exp_W_JOB_DS_Integration_Id", "Exp_W_JOB_DS_Integration_Id"), edges)
        self.assertIn(("Exp_W_JOB_DS_Integration_Id", "_EXPR_Input_mplt_SA_ORA_JobDimension"), edges)
        self.assertIn(("_EXPR_Input_mplt_SA_ORA_JobDimension", "mplt_SA_ORA_JobDimension"), edges)
        self.assertIn(("X_CUSTOM", "W_JOB_DS"), edges)
        self.assertIn(("W_JOB_DS", "mplt_SA_ORA_JobDimension"), edges)

    def test_sil_visual_graph_matches_expected_edges(self) -> None:
        graph = graph_from_xml_file(
            Path("output/remediated_xml/SIL_JobDimension_remediated.xml"),
            "SIL_JobDimension",
            visual_overrides=True,
        )
        node_names = {node.name for node in graph.nodes}
        edges = {(edge.from_node, edge.to_node) for edge in graph.edges}

        self.assertEqual(11, len(graph.nodes))
        self.assertNotIn("W_JOB_DS", node_names)
        self.assertIn("_EXPR_Upd_W_JOB_D_Ins_Upd", node_names)
        self.assertIn(("Sq_W_JOB_DS", "Lkp_W_JOB_D"), edges)
        self.assertIn(("Sq_W_JOB_DS", "mplt_Get_Etl_Proc_Wid"), edges)
        self.assertIn(("Sq_W_JOB_DS", "mplt_SIL_JobDimension_CodeLookup"), edges)
        self.assertIn(("Sq_W_JOB_DS", "Exp_W_JOB_D_Update_Flg"), edges)
        self.assertIn(("Exp_W_JOB_D_Update_Flg", "Fil_W_JOB_D"), edges)
        self.assertIn(("Fil_W_JOB_D", "Exp_Custom"), edges)
        self.assertIn(("Fil_W_JOB_D", "mplt_SIL_JobDimension"), edges)
        self.assertIn(("Exp_Custom", "_EXPR_Upd_W_JOB_D_Ins_Upd"), edges)
        self.assertIn(("mplt_SIL_JobDimension", "_EXPR_Upd_W_JOB_D_Ins_Upd"), edges)
        self.assertIn(("_EXPR_Upd_W_JOB_D_Ins_Upd", "Upd_W_JOB_D_Ins_Upd"), edges)
        self.assertIn(("Upd_W_JOB_D_Ins_Upd", "W_JOB_D"), edges)

    def test_generated_zip_dtemplates_materialize_expected_canvas_graphs(self) -> None:
        config = AppConfig(
            database=DatabaseConfig("", 0, "", "", "", ""),
            paths=PathConfig("input_xml", "output", "output/logs"),
            logging=LoggingConfig("INFO", "test.log", 1000000, 1),
        )
        summary = generate_idmc_export_package(config=config, logger=_NullLogger())
        graphs = _dtemplate_graphs(Path(summary.package_path))

        for mapping_name in ["SDE_ORA_JobDimension", "SIL_JobDimension"]:
            graph = graphs[mapping_name]
            self.assertEqual(
                {"WC_PBCS_BUDGET_ACTUALS_F", "SQ_WC_PBCS_BUDGET_ACTUALS_FS", "EXPTRANS"},
                graph["nodes"],
            )
            self.assertEqual(
                {
                    ("SQ_WC_PBCS_BUDGET_ACTUALS_FS", "EXPTRANS"),
                    ("EXPTRANS", "WC_PBCS_BUDGET_ACTUALS_F"),
                },
                graph["edges"],
            )
            self.assertIsNone(graph["native"])

        mtt_parameters = _mtt_runtime_parameters(Path(summary.package_path))
        for mapping_name in ["SDE_ORA_JobDimension", "SIL_JobDimension"]:
            self.assertEqual(
                [
                    ("$SQ_WC_PBCS_BUDGET_ACTUALS_FS$", "SOURCE", "Source"),
                    ("$WC_PBCS_BUDGET_ACTUALS_F$", "TARGET", "Target"),
                ],
                mtt_parameters[mapping_name],
            )

        images = _mapping_images(Path(summary.package_path))
        self.assertEqual(
            {
                "MappingImages/SDE_ORA_JobDimension_full_transformations.png",
                "MappingImages/SDE_ORA_JobDimension_valid_mapping.png",
                "MappingImages/SIL_JobDimension_full_transformations.png",
                "MappingImages/SIL_JobDimension_valid_mapping.png",
            },
            images,
        )


class _NullLogger:
    def info(self, *args, **kwargs) -> None:
        pass

    def warning(self, *args, **kwargs) -> None:
        pass


def _dtemplate_graphs(package_path: Path) -> dict[str, dict[str, set]]:
    graphs: dict[str, dict[str, set]] = {}
    with zipfile.ZipFile(package_path) as package:
        for member in package.namelist():
            if not member.endswith(".DTEMPLATE.zip"):
                continue
            mapping_name = Path(member).name.removesuffix(".DTEMPLATE.zip")
            with zipfile.ZipFile(io.BytesIO(package.read(member))) as dtemplate:
                bin_member = next(
                    item for item in dtemplate.namelist() if item.startswith("bin/") and item.endswith(".bin")
                )
                payload = json.loads(dtemplate.read(bin_member).decode("utf-8"))
            content = payload.get("content", {})
            transformations = content.get("transformations", [])
            refs = {item.get("$$ID"): item.get("name") for item in transformations if isinstance(item, dict)}
            nodes = {name for name in refs.values() if name}
            edges = set()
            for link in content.get("links", []):
                if not isinstance(link, dict):
                    continue
                from_id = (link.get("fromTransformation") or {}).get("##ID")
                to_id = (link.get("toTransformation") or {}).get("##ID")
                if refs.get(from_id) and refs.get(to_id):
                    edges.add((refs[from_id], refs[to_id]))
            graphs[mapping_name] = {"nodes": nodes, "edges": edges, "native": content.get("nativeCdiMapping")}
    return graphs


def _mtt_runtime_parameters(package_path: Path) -> dict[str, list[tuple[str, str, str]]]:
    parameters_by_mapping: dict[str, list[tuple[str, str, str]]] = {}
    with zipfile.ZipFile(package_path) as package:
        for member in package.namelist():
            if not member.endswith(".MTT.zip"):
                continue
            mapping_name = Path(member).name.removesuffix(".MTT.zip")
            with zipfile.ZipFile(io.BytesIO(package.read(member))) as mtt:
                task = json.loads(mtt.read("mtTask.json").decode("utf-8"))[0]
            parameters_by_mapping[mapping_name] = [
                (
                    item.get("name", ""),
                    item.get("type", ""),
                    (item.get("runtimeParameterData") or {}).get("connectionParameterName", ""),
                )
                for item in task.get("parameters", [])
            ]
    return parameters_by_mapping


def _mapping_images(package_path: Path) -> set[str]:
    with zipfile.ZipFile(package_path) as package:
        return {member for member in package.namelist() if member.startswith("MappingImages/") and member.endswith(".png")}


if __name__ == "__main__":
    unittest.main()
