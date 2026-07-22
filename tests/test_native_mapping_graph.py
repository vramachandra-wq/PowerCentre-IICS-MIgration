from __future__ import annotations

import unittest
from pathlib import Path

from business.iics.native_mapping_graph import graph_from_xml_file


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


if __name__ == "__main__":
    unittest.main()
