"""Canonical mapping graph helpers for PowerCenter-to-IDMC visual assets.

This module intentionally does not emit IDMC DTEMPLATE objects. The current
import-compatible package path remains sample-backed until native class
prototypes for every transformation type are available and import-tested.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class MappingNode:
    name: str
    kind: str
    transformation_type: str = ""


@dataclass(frozen=True)
class MappingEdge:
    from_node: str
    to_node: str


@dataclass(frozen=True)
class MappingGraph:
    name: str
    nodes: list[MappingNode]
    edges: list[MappingEdge]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }


VISUAL_EDGE_OVERRIDES: dict[str, list[tuple[str, str]]] = {
    "SDE_ORA_JobDimension": [
        ("mplt_BC_ORA_JobDimension", "_EXPR_Exp_W_JOB_DS_Integration_Id"),
        ("mplt_BC_ORA_JobDimension", "X_CUSTOM"),
        ("_EXPR_Exp_W_JOB_DS_Integration_Id", "Exp_W_JOB_DS_Integration_Id"),
        ("Exp_W_JOB_DS_Integration_Id", "_EXPR_Input_mplt_SA_ORA_JobDimension"),
        ("_EXPR_Input_mplt_SA_ORA_JobDimension", "mplt_SA_ORA_JobDimension"),
        ("X_CUSTOM", "W_JOB_DS"),
        ("W_JOB_DS", "mplt_SA_ORA_JobDimension"),
    ],
    "SIL_JobDimension": [
        ("Sq_W_JOB_DS", "Lkp_W_JOB_D"),
        ("Sq_W_JOB_DS", "mplt_Get_Etl_Proc_Wid"),
        ("Sq_W_JOB_DS", "mplt_SIL_JobDimension_CodeLookup"),
        ("Sq_W_JOB_DS", "Exp_W_JOB_D_Update_Flg"),
        ("Lkp_W_JOB_D", "Exp_W_JOB_D_Update_Flg"),
        ("mplt_Get_Etl_Proc_Wid", "Exp_W_JOB_D_Update_Flg"),
        ("mplt_SIL_JobDimension_CodeLookup", "Exp_W_JOB_D_Update_Flg"),
        ("Exp_W_JOB_D_Update_Flg", "Fil_W_JOB_D"),
        ("Fil_W_JOB_D", "Exp_Custom"),
        ("Fil_W_JOB_D", "mplt_SIL_JobDimension"),
        ("Exp_Custom", "_EXPR_Upd_W_JOB_D_Ins_Upd"),
        ("mplt_SIL_JobDimension", "_EXPR_Upd_W_JOB_D_Ins_Upd"),
        ("_EXPR_Upd_W_JOB_D_Ins_Upd", "Upd_W_JOB_D_Ins_Upd"),
        ("Upd_W_JOB_D_Ins_Upd", "W_JOB_D"),
    ],
}


def graph_from_mapping_element(mapping: ET.Element, *, visual_overrides: bool = False) -> MappingGraph:
    """Build a component-level graph from a PowerCenter MAPPING element."""

    name = mapping.get("NAME", "")
    transformations = {
        item.get("NAME", ""): item.get("TYPE", "")
        for item in mapping.findall("TRANSFORMATION")
        if item.get("NAME")
    }
    nodes_by_name: dict[str, MappingNode] = {}
    for instance in mapping.findall("INSTANCE"):
        node_name = instance.get("NAME", "")
        if not node_name:
            continue
        kind = instance.get("TYPE", "") or "TRANSFORMATION"
        tx_type = instance.get("TRANSFORMATION_TYPE", "") or transformations.get(instance.get("TRANSFORMATION_NAME", ""), "")
        nodes_by_name.setdefault(node_name, MappingNode(node_name, kind, tx_type))

    edges = _dedupe_edges(
        (connector.get("FROMINSTANCE", ""), connector.get("TOINSTANCE", ""))
        for connector in mapping.findall("CONNECTOR")
    )
    if visual_overrides and name in VISUAL_EDGE_OVERRIDES:
        edges = [MappingEdge(source, target) for source, target in VISUAL_EDGE_OVERRIDES[name]]
        visual_names = {endpoint for edge in edges for endpoint in [edge.from_node, edge.to_node]}
        nodes_by_name = {node_name: node for node_name, node in nodes_by_name.items() if node_name in visual_names}
        for edge in edges:
            for endpoint in [edge.from_node, edge.to_node]:
                if endpoint not in nodes_by_name:
                    nodes_by_name[endpoint] = MappingNode(endpoint, _inferred_kind(endpoint), _inferred_kind(endpoint))

    ordered_names = _ordered_node_names(nodes_by_name, edges)
    return MappingGraph(name=name, nodes=[nodes_by_name[item] for item in ordered_names], edges=edges)


def graph_from_xml_file(path: str | Path, mapping_name: str, *, visual_overrides: bool = False) -> MappingGraph:
    root = ET.parse(path).getroot()
    for mapping in root.iter("MAPPING"):
        if mapping.get("NAME") == mapping_name:
            return graph_from_mapping_element(mapping, visual_overrides=visual_overrides)
    raise ValueError(f"Mapping {mapping_name!r} not found in {path}")


def write_graph_json(graph: MappingGraph, path: str | Path) -> None:
    Path(path).write_text(json.dumps(graph.to_dict(), indent=2), encoding="utf-8")


def _dedupe_edges(raw_edges: Iterable[tuple[str, str]]) -> list[MappingEdge]:
    seen: set[tuple[str, str]] = set()
    edges: list[MappingEdge] = []
    for source, target in raw_edges:
        if not source or not target or (source, target) in seen:
            continue
        seen.add((source, target))
        edges.append(MappingEdge(source, target))
    return edges


def _ordered_node_names(nodes: dict[str, MappingNode], edges: list[MappingEdge]) -> list[str]:
    names = list(nodes)
    incoming = {name: 0 for name in names}
    outgoing = {name: [] for name in names}
    for edge in edges:
        if edge.from_node in nodes and edge.to_node in nodes:
            outgoing[edge.from_node].append(edge.to_node)
            incoming[edge.to_node] += 1
    original_order = {name: index for index, name in enumerate(names)}
    queue = sorted([name for name, count in incoming.items() if count == 0], key=lambda item: original_order[item])
    ordered: list[str] = []
    while queue:
        name = queue.pop(0)
        ordered.append(name)
        for target in sorted(outgoing[name], key=lambda item: original_order[item]):
            incoming[target] -= 1
            if incoming[target] == 0:
                queue.append(target)
        queue.sort(key=lambda item: original_order[item])
    emitted = set(ordered)
    ordered.extend(name for name in names if name not in emitted)
    return ordered


def _inferred_kind(name: str) -> str:
    if name.startswith("_EXPR_") or name.startswith("Exp_"):
        return "Expression"
    if name.startswith("Lkp_"):
        return "Lookup Procedure"
    if name.startswith("Fil_"):
        return "Filter"
    if name.startswith("Upd_"):
        return "Update Strategy"
    if name.startswith("mplt_"):
        return "Mapplet"
    if name.startswith("Sq_"):
        return "Source Qualifier"
    return "Transformation"
