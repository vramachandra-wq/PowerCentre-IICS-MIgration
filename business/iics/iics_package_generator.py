"""
IICS Package Generator
======================
Converts all parsed PowerCenter XML files into a single IICS-importable
export package zip, following exactly the structure of a genuine IICS export.

All internal formats (bin content, JSON schemas, XML) are validated against
a real IICS export package to ensure import compatibility.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
import time
import uuid
import zipfile
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

from business.iics.checksum_utils import build_checksum_file, sha256_hex, validate_zip_checksums
from business.iics.iics_success_benchmark import IICSSuccessBenchmark


# ── ID counter (IICS bin uses sequential integers) ─────────────────────────
class _IdCounter:
    def __init__(self, start: int = 1) -> None:
        self._v = start - 1

    def next(self) -> int:
        self._v += 1
        return self._v


# ── PC → IICS native type ───────────────────────────────────────────────────
_PC_NATIVE: dict[str, str] = {
    "varchar2": "nvarchar", "nvarchar2": "nvarchar", "varchar": "nvarchar",
    "char": "nvarchar", "nchar": "nvarchar", "clob": "nvarchar", "nclob": "nvarchar",
    "string": "nvarchar", "number(p,s)": "decimal", "number": "decimal",
    "decimal": "decimal", "integer": "int", "int": "int", "bigint": "bigint",
    "smallint": "int", "float": "float", "double": "double", "real": "double",
    "date": "date", "datetime": "datetime", "timestamp": "datetime",
    "binary": "binary", "boolean": "boolean",
}

def _native(pc_type: str) -> str:
    return _PC_NATIVE.get(pc_type.lower().split("(")[0].strip(), "nvarchar")


# ── DTEMPLATE bin builder ────────────────────────────────────────────────────

_CLASS_SOURCE = 6
_CLASS_EXPRESSION = 7
_CLASS_TARGET = 8
_CLASS_LOOKUP = 32
_CLASS_LOOKUP_CONDITION = 33
_CLASS_MAPPLET = 34
_CLASS_MAPPLET_ADAPTER = 35
_CLASS_TX_FIELD_GROUP = 36
_CLASS_INPUT = 37
_CLASS_OUTPUT = 38
_CLASS_FILTER = 39

_SOURCE_LIKE_TYPES = {
    "source",
    "source definition",
    "source qualifier",
}
_TARGET_LIKE_TYPES = {
    "target",
    "target definition",
}
_LOOKUP_LIKE_TYPES = {
    "lookup",
    "lookup procedure",
}
_MAPPLET_LIKE_TYPES = {
    "mapplet",
}
_FILTER_LIKE_TYPES = {
    "filter",
}
_INPUT_LIKE_TYPES = {
    "input transformation",
    "input",
}
_OUTPUT_LIKE_TYPES = {
    "output transformation",
    "output",
}

_CLASS_INFO = {
    "1": "com.informatica.metadata.template.common.Template",
    "2": "com.informatica.metadata.common.description.Description",
    "3": "com.informatica.metadata.common.genericannotation.GenericAnnotation",
    "4": "com.informatica.metadata.template.common.TmplLink",
    "5": "com.informatica.metadata.template.common.TmplGroup",
    "6": "com.informatica.metadata.template.tx.tmplsource.TmplSource",
    "7": "com.informatica.metadata.template.tx.tmplexpression.TmplExpression",
    "8": "com.informatica.metadata.template.tx.tmpltarget.TmplTarget",
    "9": "com.informatica.metadata.template.common.param.TmplParam",
    "10": "com.informatica.metadata.common.genericannotation.NameValuePair",
    "11": "com.informatica.metadata.template.common.param.ConnectionParamType",
    "12": "com.informatica.metadata.template.common.TxSessionProperty",
    "13": "com.informatica.metadata.template.ext.da.cloud.common.BaseAdapter",
    "14": "com.informatica.metadata.template.common.field.TxField",
    "15": "com.informatica.metadata.template.ext.da.cloud.common.BaseAdapterField",
    "16": "com.informatica.metadata.common.typesystem.DataType",
    "17": "com.informatica.metadata.template.tx.tmpltarget.FieldMappings",
    "18": "com.informatica.metadata.template.common.TxAdvancedProperty",
    "19": "com.informatica.metadata.template.tx.tmplexpression.TmplExpressionField",
    "20": "com.informatica.metadata.common.types.BooleanValue",
    "21": "com.informatica.metadata.template.common.rule.TmplAllRule",
    "22": "com.informatica.metadata.template.common.rule.TmplNameRule",
    "23": "com.informatica.metadata.template.ext.da.cloud.common.DataObject",
    "24": "com.informatica.metadata.template.ext.da.cloud.common.WriteOptions",
    "25": "com.informatica.metadata.template.tx.tmpltarget.FieldMapping",
    "26": "com.informatica.metadata.template.ext.da.cloud.common.ReadOptions",
    "27": "com.informatica.metadata.template.common.ConflictResolution",
    "28": "com.informatica.metadata.template.common.rule.TmplNameRuleEntry",
    "29": "com.informatica.metadata.template.ext.da.cloud.common.FlatFileAttrs",
    "30": "com.informatica.metadata.template.ext.da.cloud.common.Option",
    "31": "com.informatica.metadata.template.common.BulkRenameOption",
    # ConvTool / IDMC-aligned transformation classes
    "32": "com.informatica.metadata.template.tx.tmpllookup.TmplLookup",
    "33": "com.informatica.metadata.template.tx.tmpllookup.LookupCondition",
    "34": "com.informatica.metadata.template.tx.tmplmapplet.TmplMapplet",
    "35": "com.informatica.metadata.template.ext.da.cloud.common.MappletAdapter",
    "36": "com.informatica.metadata.template.tx.tmplmapplet.TxFieldGroup",
    "37": "com.informatica.metadata.template.tx.tmplinput.TmplInput",
    "38": "com.informatica.metadata.template.tx.tmploutput.TmplOutput",
    "39": "com.informatica.metadata.template.tx.tmplfilter.TmplFilter",
}

# DMAPPLET bins use a different $$class numbering than DTEMPLATE (ConvTool gold).
_DMAPPLET_CLASS_INFO = {
    "1": "com.informatica.metadata.template.common.Template",
    "2": "com.informatica.metadata.common.description.Description",
    "3": "com.informatica.metadata.template.common.layout.LayoutAnnotation",
    "4": "com.informatica.metadata.template.common.TmplLink",
    "5": "com.informatica.metadata.template.common.TmplGroup",
    "6": "com.informatica.metadata.template.tx.tmplinput.TmplInput",
    "7": "com.informatica.metadata.template.tx.tmplexpression.TmplExpression",
    "8": "com.informatica.metadata.template.tx.tmpllookup.TmplLookup",
    "9": "com.informatica.metadata.template.tx.tmploutput.TmplOutput",
    "10": "com.informatica.metadata.template.common.param.TmplParam",
    "11": "com.informatica.metadata.template.common.param.ConnectionParamType",
    "12": "com.informatica.metadata.template.common.TxAdvancedProperty",
    "13": "com.informatica.metadata.template.tx.tmplexpression.TmplExpressionField",
    "14": "com.informatica.metadata.common.typesystem.DataType",
    "15": "com.informatica.metadata.template.ext.da.cloud.common.BaseAdapter",
    "16": "com.informatica.metadata.template.common.field.TxField",
    "17": "com.informatica.metadata.template.ext.da.cloud.common.BaseAdapterField",
    "18": "com.informatica.metadata.template.tx.tmpllookup.LookupCondition",
    "19": "com.informatica.metadata.template.tx.tmploutput.OutputFieldMappings",
    "20": "com.informatica.metadata.template.common.rule.TmplAllRule",
    "21": "com.informatica.metadata.template.common.rule.TmplNameRule",
    "22": "com.informatica.metadata.template.ext.da.cloud.common.DataObject",
    "23": "com.informatica.metadata.template.ext.da.cloud.common.ReadOptions",
    "24": "com.informatica.metadata.template.ext.da.cloud.common.WriteOptions",
    "25": "com.informatica.metadata.template.tx.tmploutput.OutputFieldMapping",
    "26": "com.informatica.metadata.template.common.ConflictResolution",
    "27": "com.informatica.metadata.template.common.rule.TmplNameRuleEntry",
    "28": "com.informatica.metadata.template.ext.da.cloud.common.Option",
    "29": "com.informatica.metadata.template.common.BulkRenameOption",
}

# Remap DTEMPLATE emitter class numbers → DMAPPLET class numbers.
_DTEMPLATE_TO_DMAPPLET_CLASS = {
    1: 1,
    2: 2,
    4: 4,
    5: 5,
    7: 7,   # Expression
    9: 10,  # TmplParam
    11: 11, # ConnectionParamType
    13: 15, # BaseAdapter
    14: 16, # TxField
    15: 17, # BaseAdapterField
    16: 14, # DataType
    17: 19, # FieldMappings → OutputFieldMappings
    18: 12, # TxAdvancedProperty
    19: 13, # ExpressionField
    21: 20, # TmplAllRule
    22: 21, # TmplNameRule
    23: 22, # DataObject
    24: 24, # WriteOptions
    25: 25, # FieldMapping → OutputFieldMapping
    26: 23, # ReadOptions
    27: 26, # ConflictResolution
    28: 27, # TmplNameRuleEntry
    30: 28, # Option
    31: 29, # BulkRenameOption
    32: 8,  # Lookup
    33: 18, # LookupCondition
    37: 6,  # Input
    38: 9,  # Output
}


def _remap_dtemplate_classes_to_dmapplet(obj: Any) -> Any:
    """Rewrite $$class integers from DTEMPLATE scheme to DMAPPLET scheme."""
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            if key == "$$class" and isinstance(value, int):
                out[key] = _DTEMPLATE_TO_DMAPPLET_CLASS.get(value, value)
            else:
                out[key] = _remap_dtemplate_classes_to_dmapplet(value)
        return out
    if isinstance(obj, list):
        return [_remap_dtemplate_classes_to_dmapplet(item) for item in obj]
    return obj


def _pc_kind(instance_type: str, transformation_type: str) -> str:
    """Classify a PC instance into native CDI IMF roles."""
    itype = (instance_type or "").strip().upper()
    ttype = (transformation_type or "").strip().lower()
    if itype == "SOURCE" or ttype in _SOURCE_LIKE_TYPES:
        return "source"
    if itype == "TARGET" or ttype in _TARGET_LIKE_TYPES:
        return "target"
    if itype == "MAPPLET" or ttype in _MAPPLET_LIKE_TYPES:
        return "mapplet"
    if ttype in _LOOKUP_LIKE_TYPES:
        return "lookup"
    if ttype in _FILTER_LIKE_TYPES:
        return "filter"
    if ttype in _INPUT_LIKE_TYPES:
        return "input"
    if ttype in _OUTPUT_LIKE_TYPES:
        return "output"
    return "expression"


def _parse_lookup_conditions(condition: str) -> list[dict[str, str]]:
    """Parse PC 'Lookup condition' text into left/op/right triples."""
    text = (condition or "").strip()
    if not text:
        return []
    # Split on AND (case-insensitive), keep simple binary predicates.
    parts = re.split(r"\s+AND\s+", text, flags=re.IGNORECASE)
    ops = ["<=", ">=", "<>", "!=", "=", "<", ">"]
    parsed: list[dict[str, str]] = []
    for part in parts:
        clause = part.strip()
        if not clause:
            continue
        matched = None
        for op in ops:
            if op in clause:
                left, right = clause.split(op, 1)
                parsed.append({
                    "leftOperand": left.strip(),
                    "operator": "=" if op == "==" else op,
                    "rightOperand": right.strip(),
                })
                matched = op
                break
        if matched is None:
            parsed.append({
                "leftOperand": clause,
                "operator": "=",
                "rightOperand": clause,
            })
    return parsed


def _yes_no_to_bool(value: str | None, default: str = "false") -> str:
    token = (value or "").strip().lower()
    if token in {"yes", "y", "true", "1"}:
        return "true"
    if token in {"no", "n", "false", "0"}:
        return "false"
    return default


def _pc_annotation(pc_type: str, attributes: dict | None) -> str:
    """Preserve original PC type and key attrs for non-native CDI roles."""
    attrs = attributes or {}
    interesting = (
        "Filter Condition",
        "Update Strategy Expression",
        "Lookup Sql Override",
        "Lookup table name",
        "Lookup Source Filter",
        "Lookup condition",
        "Sql Query",
        "Source Filter",
        "User Defined Join",
    )
    parts = [f"PC_TYPE={pc_type or 'Unknown'}"]
    for key in interesting:
        value = attrs.get(key)
        if value:
            parts.append(f"{key}={value}")
    return "; ".join(parts)


def _ports_as_columns(ports: list[dict]) -> list[dict]:
    columns = []
    for port in ports:
        columns.append({
            "column_name": port.get("port_name") or port.get("name") or "FIELD",
            "datatype": port.get("datatype") or "varchar2",
            "precision": port.get("precision") or 50,
            "scale": port.get("scale") or 0,
            "expression": port.get("expression") or "",
            "port_type": port.get("port_type") or "INPUT/OUTPUT",
            "mapplet_group": port.get("mapplet_group") or "",
        })
    return columns


def _lookup_reusable_transformation(folder_data: dict, name: str) -> dict | None:
    """Resolve a folder-level reusable TRANSFORMATION by name."""
    if not name:
        return None
    for item in folder_data.get("reusable_transformations") or []:
        tx_name = item.get("transformation_name") or ""
        if tx_name == name or tx_name.casefold() == name.casefold():
            return item
    return None


def _enrich_graph_transformations(graph: dict, folder_data: dict) -> dict:
    """
    Merge folder-level reusable transformation defs referenced by graph instances.

    Mapplet IMF graphs often INSTANCE reusable Lookups defined at folder scope;
    without these defs lookups emit PASS_THRU shells and DMAPPLET import fails.
    """
    txs = list(graph.get("transformations") or [])
    known = {t.get("transformation_name", ""): t for t in txs}
    known_ci = {k.casefold(): v for k, v in known.items() if k}
    for inst in graph.get("instances") or []:
        tx_name = inst.get("transformation_name") or inst.get("instance_name") or ""
        if not tx_name:
            continue
        if tx_name in known or tx_name.casefold() in known_ci:
            continue
        ref = _lookup_reusable_transformation(folder_data, tx_name)
        if ref:
            txs.append(ref)
            known[tx_name] = ref
            known_ci[tx_name.casefold()] = ref
    enriched = dict(graph)
    enriched["transformations"] = txs
    return enriched


def _lookup_mapplet(folder_data: dict, name: str) -> dict | None:
    """Find a folder-level mapplet definition by name."""
    needle = (name or "").casefold()
    for item in folder_data.get("mapplets") or []:
        if str(item.get("mapplet_name", "")).casefold() == needle:
            return item
    return None


def _mapplet_interface_ports(mapplet: dict | None) -> list[dict]:
    """
    Resolve INPUT/OUTPUT interface ports for a mapplet instance.

    Prefer the TRANSFORMATION TYPE=Mapplet shell (MAPPLETGROUP=Input/Output).
    Fall back to Input/Output Transformation ports.
    """
    if not mapplet:
        return []

    def _normalize_group(raw: str, port_type: str, port_name: str) -> str:
        group = (raw or "").strip().upper()
        if group in {"INPUT", "INPUTS", "IN"}:
            return "INPUT"
        if group in {"OUTPUT", "OUTPUTS", "OUT"}:
            return "OUTPUT"
        pt = (port_type or "").upper()
        if pt == "INPUT" or str(port_name or "").upper().startswith("INP_"):
            return "INPUT"
        if pt == "OUTPUT" or str(port_name or "").upper().startswith("EXT_"):
            return "OUTPUT"
        return group

    txs = list(mapplet.get("transformations") or [])
    shell = next(
        (
            tx for tx in txs
            if (tx.get("transformation_type") or "").strip().lower() == "mapplet"
        ),
        None,
    )
    ports: list[dict] = []
    if shell and shell.get("ports"):
        for port in shell["ports"]:
            group = _normalize_group(
                port.get("mapplet_group") or "",
                port.get("port_type") or "",
                port.get("port_name") or "",
            )
            ports.append({
                **port,
                "port_type": "INPUT" if group == "INPUT" else "OUTPUT" if group == "OUTPUT" else (port.get("port_type") or ""),
                "mapplet_group": group,
            })
        if any(p.get("mapplet_group") in {"INPUT", "OUTPUT"} for p in ports):
            return ports

    for tx in txs:
        ttype = (tx.get("transformation_type") or "").strip().lower()
        if ttype in _INPUT_LIKE_TYPES:
            for port in tx.get("ports") or []:
                ports.append({**port, "port_type": "INPUT", "mapplet_group": "INPUT"})
        elif ttype in _OUTPUT_LIKE_TYPES:
            for port in tx.get("ports") or []:
                ports.append({**port, "port_type": "OUTPUT", "mapplet_group": "OUTPUT"})
    return ports


def _mapplet_saas_id(mapplet_guids: dict[str, str] | None, *names: str) -> str:
    if not mapplet_guids:
        return ""
    for name in names:
        guid = mapplet_guids.get(name or "")
        if guid:
            return f"@{guid}"
        # case-insensitive fallback
        needle = (name or "").casefold()
        for key, value in mapplet_guids.items():
            if key.casefold() == needle:
                return f"@{value}"
    return ""


def _collect_used_mapplet_names(mapping: dict) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for inst in mapping.get("instances") or []:
        pc_type = (inst.get("transformation_type") or "").strip().lower()
        itype = (inst.get("instance_type") or "").strip().upper()
        if itype != "MAPPLET" and pc_type not in _MAPPLET_LIKE_TYPES:
            continue
        name = inst.get("transformation_name") or inst.get("instance_name") or ""
        if not name or name.casefold() in seen:
            continue
        seen.add(name.casefold())
        names.append(name)
    return names


def _lookup_by_name(items: list[dict], name_key: str, name: str) -> dict | None:
    needle = (name or "").casefold()
    for item in items:
        if str(item.get(name_key, "")).casefold() == needle:
            return item
    return None


def _platform_type_sid(datatype: str) -> str:
    token = (datatype or "").lower()
    if "date" in token or "time" in token:
        return "smd:com.informatica.metadata.seed.platform.Platform.typesystem/date/time"
    if any(x in token for x in ("number", "decimal", "int", "float", "double")):
        return "smd:com.informatica.metadata.seed.platform.Platform.typesystem/decimal"
    return "smd:com.informatica.metadata.seed.platform.Platform.typesystem/string"


def _build_bin(
    mapping: dict,
    folder_data: dict,
    mapplet_guids: dict[str, str] | None = None,
) -> bytes:
    """
    Build bin/@2.bin content matching the IICS DTEMPLATE IMF format.

    Prefer PowerCenter INSTANCE + CONNECTOR graph so the mapping canvas
    reflects real structural topology (not a synthetic SQ→Expr→Target chain).
    """
    instances = list(mapping.get("instances") or [])
    connectors = list(mapping.get("connectors") or [])
    if instances and connectors:
        return _build_bin_from_graph(
            mapping, folder_data, instances, connectors, mapplet_guids=mapplet_guids,
        )
    return _build_bin_legacy_linear(mapping, folder_data)


def _finalize_bin(
    *,
    name: str,
    ann1_id: int,
    ann2_id: int,
    ann_kv_id: int,
    links: list[dict],
    parameters: list[dict],
    transformations: list[dict],
    document_type: str = "",
) -> bytes:
    is_dmapplet = (document_type or "").upper() == "DMAPPLET"
    if is_dmapplet:
        # ConvTool DMAPPLETs use Description-only annotations (no GenericAnnotation /
        # BooleanValue TEMPLATE_SETTINGS block used by DTEMPLATE).
        annotations = [{"$$ID": ann1_id, "$$class": 2, "body": ""}]
        class_info = _DMAPPLET_CLASS_INFO
    else:
        annotations = [
            {"$$ID": ann1_id, "$$class": 2, "body": ""},
            {
                "$$ID": ann2_id, "$$class": 3,
                "source": "TEMPLATE_SETTINGS",
                "nameValuePairs": [{
                    "$$ID": ann_kv_id, "$$class": 10,
                    "name": "UNIQUIFY_MAPPLET_TX_NAMES",
                    "value": {"$$class": 20, "value": "true"},
                }],
            },
        ]
        class_info = _CLASS_INFO
    content = {
        "$$IID": "stringIdentity:@2",
        "$$class": 1,
        "annotations": annotations,
        "allowMaxFieldLength": "false",
        "bigIntConvertType": "",
        "documentType": document_type,
        "ecoSystem": "",
        "name": name,
        "specialCharacterSupport": "true",
        "templateOrigin": "",
        "links": links,
        "parameters": parameters,
        "transformations": transformations,
    }
    payload: dict[str, Any] = {
        "content": content,
        "metadata": {"$$classInfo": class_info},
    }
    if is_dmapplet:
        payload = _remap_dtemplate_classes_to_dmapplet(payload)
        # Remap also rewrote classInfo keys incorrectly if they were ints; keep gold map.
        payload["metadata"] = {"$$classInfo": _DMAPPLET_CLASS_INFO}
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def _make_passthrough_expr_node(
    c: _IdCounter,
    name: str,
    columns: list[dict],
    *,
    pc_type: str = "Expression",
) -> dict[str, Any]:
    """Build a ConvTool-style passthrough Expression node (EXPR_* wrapper)."""
    cols = list(columns) or [{
        "column_name": "PASS_THRU",
        "datatype": "varchar2",
        "precision": 50,
        "scale": 0,
        "expression": "PASS_THRU",
        "port_type": "INPUT/OUTPUT",
    }]
    # Normalize to passthrough expressions.
    norm_cols = []
    for col in cols:
        item = dict(col)
        item["expression"] = item.get("column_name") or "PASS_THRU"
        item["port_type"] = item.get("port_type") or "INPUT/OUTPUT"
        norm_cols.append(item)
    col_ids = []
    for col in norm_cols:
        col_ids.append({
            "fld_id": c.next(),
            "adapt_id": c.next(),
            "ann_id": c.next(),
            "col": col,
        })
    return {
        "name": name,
        "kind": "expression",
        "pc_type": pc_type,
        "tx_id": c.next(),
        "grp_id": c.next(),
        "da_id": c.next(),
        "obj_id": c.next(),
        "imf_class": _CLASS_EXPRESSION,
        "columns": norm_cols,
        "object_name": name,
        "attributes": {},
        "ports": [],
        "tx_name": name,
        "saas_mapplet_id": "",
        "col_ids": col_ids,
    }


def _insert_convtool_expr_wrappers(
    c: _IdCounter,
    node_meta: dict[str, dict],
    edge_list: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """
    Insert ConvTool-like EXPR_* wrappers so canvases match Valid IDMC mappings.

    Patterns (from Valid SDE/SIL + ConvTool gold):
      - Mapplet → Expression → Mapplet  ⇒  Mapplet → _EXPR_<Exp> → Exp → _EXPR_Input_<Mp> → Mapplet
      - * → Update Strategy            ⇒  * → _EXPR_Upd_<Upd> → Update Strategy
    """
    edges = list(edge_list)

    def _preds(name: str) -> list[str]:
        return [a for a, b in edges if b == name]

    def _succs(name: str) -> list[str]:
        return [b for a, b in edges if a == name]

    def _rewire(old: tuple[str, str], new_edges: list[tuple[str, str]]) -> None:
        nonlocal edges
        edges = [e for e in edges if e != old]
        for ne in new_edges:
            if ne not in edges:
                edges.append(ne)

    # Update Strategy wrappers: _EXPR_<UpdName> (e.g. _EXPR_Upd_W_JOB_D_Ins_Upd)
    for name, node in list(node_meta.items()):
        if "update strategy" not in (node.get("pc_type") or "").lower():
            continue
        wrapper = f"_EXPR_{name}"
        if wrapper in node_meta:
            continue
        node_meta[wrapper] = _make_passthrough_expr_node(c, wrapper, node["columns"])
        for pred in _preds(name):
            _rewire((pred, name), [(pred, wrapper)])
        if (wrapper, name) not in edges:
            edges.append((wrapper, name))

    # Mapplet → Expression → Mapplet wrappers
    for name, node in list(node_meta.items()):
        if node.get("kind") != "expression":
            continue
        if name.startswith("_EXPR_"):
            continue
        mapplet_preds = [
            p for p in _preds(name) if node_meta.get(p, {}).get("kind") == "mapplet"
        ]
        mapplet_succs = [
            s for s in _succs(name) if node_meta.get(s, {}).get("kind") == "mapplet"
        ]
        if not mapplet_preds or not mapplet_succs:
            continue

        pre_wrap = f"_EXPR_{name}"
        if pre_wrap not in node_meta:
            node_meta[pre_wrap] = _make_passthrough_expr_node(c, pre_wrap, node["columns"])
        for pred in mapplet_preds:
            _rewire((pred, name), [(pred, pre_wrap)])
        if (pre_wrap, name) not in edges:
            edges.append((pre_wrap, name))

        for mp in mapplet_succs:
            post_wrap = f"_EXPR_Input_{mp}"
            if post_wrap not in node_meta:
                mp_cols = [
                    col for col in node_meta[mp].get("columns") or []
                    if "OUTPUT" not in str(col.get("port_type") or "").upper()
                    or "INPUT" in str(col.get("port_type") or "").upper()
                ] or list(node_meta[mp].get("columns") or [])
                node_meta[post_wrap] = _make_passthrough_expr_node(
                    c, post_wrap, mp_cols or node["columns"],
                )
            _rewire((name, mp), [(name, post_wrap), (post_wrap, mp)])

    return edges


def _normalize_sde_mapping_topology(
    c: _IdCounter,
    node_meta: dict[str, dict],
    edge_list: list[tuple[str, str]],
    mapping: dict,
) -> list[tuple[str, str]]:
    """
    Align SDE mapping graphs with valid ConvTool/reference topology.

    SDE BC mapplets are output-only sources at mapping level; targets must be
    reached through _EXPR_Input_* / _EXPR_<Target> wrappers, not direct links.
    """
    if not (mapping.get("mapping_name") or "").startswith("SDE_"):
        return edge_list

    edges = list(edge_list)

    def _preds(name: str) -> list[str]:
        return [a for a, b in edges if b == name]

    def _succs(name: str) -> list[str]:
        return [b for a, b in edges if a == name]

    def _rewire(old: tuple[str, str], new_edges: list[tuple[str, str]]) -> None:
        nonlocal edges
        edges = [e for e in edges if e != old]
        for ne in new_edges:
            if ne not in edges:
                edges.append(ne)

    # Drop mapplet→expression pre-wrappers; reference keeps BC→Exp direct.
    for name, node in list(node_meta.items()):
        if node.get("kind") != "expression" or name.startswith("_EXPR_"):
            continue
        pre_wrap = f"_EXPR_{name}"
        if pre_wrap not in node_meta:
            continue
        has_input_wrapper_succ = any(
            succ.startswith("_EXPR_Input_") for succ in _succs(name)
        )
        has_mapplet_pred = any(
            node_meta.get(pred, {}).get("kind") == "mapplet" for pred in _preds(name)
        )
        if not (has_input_wrapper_succ and has_mapplet_pred):
            # After ConvTool the mapplet may only connect to the pre-wrapper.
            has_mapplet_pred = any(
                node_meta.get(pred, {}).get("kind") == "mapplet" for pred in _preds(pre_wrap)
            )
        if not (has_input_wrapper_succ and has_mapplet_pred):
            continue
        for pred in set(_preds(name) + _preds(pre_wrap)):
            if node_meta.get(pred, {}).get("kind") == "mapplet":
                _rewire((pred, pre_wrap), [(pred, name)])
        edges = [(a, b) for a, b in edges if pre_wrap not in {a, b}]
        node_meta.pop(pre_wrap, None)

    sa_mapplets = [
        name for name, node in node_meta.items()
        if node.get("kind") == "mapplet" and not node.get("output_only")
    ]
    bc_mapplets = [
        name for name, node in node_meta.items()
        if node.get("kind") == "mapplet" and node.get("output_only")
    ]
    targets = [name for name, node in node_meta.items() if node.get("kind") == "target"]

    for sa in sa_mapplets:
        post_wrap = f"_EXPR_Input_{sa}"
        if post_wrap not in node_meta:
            mp_cols = [
                col for col in node_meta[sa].get("columns") or []
                if "OUTPUT" not in str(col.get("port_type") or "").upper()
                or "INPUT" in str(col.get("port_type") or "").upper()
            ] or list(node_meta[sa].get("columns") or [])
            node_meta[post_wrap] = _make_passthrough_expr_node(c, post_wrap, mp_cols)
        for bc in bc_mapplets:
            if (bc, post_wrap) not in edges:
                edges.append((bc, post_wrap))
        for tgt in targets:
            if ("X_CUSTOM", tgt) in edges:
                _rewire(("X_CUSTOM", tgt), [("X_CUSTOM", post_wrap)])

    for tgt in targets:
        wrapper = f"_EXPR_{tgt}"
        if wrapper not in node_meta:
            node_meta[wrapper] = _make_passthrough_expr_node(
                c, wrapper, node_meta[tgt].get("columns") or [],
            )
        for pred in list(_preds(tgt)):
            if pred == wrapper:
                continue
            _rewire((pred, tgt), [(pred, wrapper)])
        if (wrapper, tgt) not in edges:
            edges.append((wrapper, tgt))

    return edges


def _build_bin_from_graph(
    mapping: dict,
    folder_data: dict,
    instances: list[dict],
    connectors: list[dict],
    mapplet_guids: dict[str, str] | None = None,
    *,
    document_type: str = "",
    graph_name: str | None = None,
    skip_mapplet_shell: bool = False,
) -> bytes:
    """Build IMF from PC instances + connector topology."""
    c = _IdCounter()
    name = graph_name or mapping.get("mapping_name") or mapping.get("mapplet_name") or "Mapping"
    sources = folder_data.get("sources", [])
    targets = folder_data.get("targets", [])
    txs = {tx.get("transformation_name", ""): tx for tx in mapping.get("transformations", [])}
    txs_ci = {k.casefold(): v for k, v in txs.items()}

    sess = next(
        (s for s in folder_data.get("sessions", []) if s.get("mapping_name") == name),
        folder_data.get("sessions", [{}])[0] if folder_data.get("sessions") else {},
    )
    sess_attrs = sess.get("attributes", {}) if sess else {}

    ann1_id = c.next()
    ann2_id = c.next()
    ann_kv_id = c.next()

    node_meta: dict[str, dict] = {}
    # Collect Source Qualifier instance names so Source Definitions can be omitted
    # (IDMC CDI uses SQ as the Source adapter — dual Source Definition+SQ causes MTT
    # to require $SourceDef$/EXTENDED_SOURCE and breaks import).
    sq_instance_names = {
        (inst.get("instance_name") or "")
        for inst in instances
        if (inst.get("transformation_type") or "").strip().lower() == "source qualifier"
    }
    skipped_source_defs: set[str] = set()

    for inst in instances:
        inst_name = inst.get("instance_name") or ""
        if not inst_name or inst_name in node_meta:
            continue
        tx_name = inst.get("transformation_name") or inst_name
        pc_type = inst.get("transformation_type") or inst.get("instance_type") or ""
        kind = _pc_kind(inst.get("instance_type", ""), pc_type)

        # Skip Mapplet shell TRANSFORM mirrored as an instance inside DMAPPLET graphs.
        if skip_mapplet_shell and kind == "mapplet":
            continue

        # Prefer Source Qualifier over Source Definition for CDI Source adapters.
        if (
            kind == "source"
            and (pc_type or "").strip().lower() == "source definition"
            and sq_instance_names
        ):
            skipped_source_defs.add(inst_name)
            continue

        tx_def = txs.get(tx_name) or txs_ci.get(tx_name.casefold()) or {}
        if not tx_def.get("ports"):
            tx_def = _lookup_reusable_transformation(folder_data, tx_name) or tx_def
        ports = list(tx_def.get("ports") or [])
        attributes = dict(tx_def.get("attributes") or {})
        output_only = False

        if kind == "source":
            src = _lookup_by_name(sources, "source_name", tx_name) or _lookup_by_name(
                sources, "source_name", inst_name
            )
            # For SQ, also try stripping Sq_ prefix to find folder source columns.
            if src is None and inst_name.lower().startswith("sq_"):
                src = _lookup_by_name(sources, "source_name", inst_name[3:])
            columns = list(src.get("columns", [])) if src else _ports_as_columns(ports)
            object_name = (src or {}).get("source_name") or tx_name
            if not attributes.get("Sql Query"):
                attributes["Sql Query"] = sess_attrs.get("Sql Query", "")
        elif kind == "target":
            tgt = _lookup_by_name(targets, "target_name", tx_name) or _lookup_by_name(
                targets, "target_name", inst_name
            )
            columns = list(tgt.get("columns", [])) if tgt else _ports_as_columns(ports)
            object_name = (tgt or {}).get("target_name") or tx_name
        elif kind == "mapplet":
            mapplet_def = _lookup_mapplet(folder_data, tx_name) or _lookup_mapplet(
                folder_data, inst_name
            )
            iface_ports = _mapplet_interface_ports(mapplet_def)
            output_only = bool(iface_ports) and not any(
                p.get("mapplet_group") == "INPUT" for p in iface_ports
            )
            columns = _ports_as_columns(iface_ports) if iface_ports else (
                _ports_as_columns(ports) if ports else [
                    {"column_name": "PASS_THRU", "datatype": "varchar2", "precision": 50,
                     "scale": 0, "expression": "PASS_THRU", "port_type": "INPUT/OUTPUT"}
                ]
            )
            object_name = tx_name
            attributes = dict((mapplet_def or {}).get("attributes") or {}) if mapplet_def else attributes
        elif kind == "lookup":
            columns = _ports_as_columns(ports) if ports else [
                {"column_name": "PASS_THRU", "datatype": "varchar2", "precision": 50, "scale": 0,
                 "expression": "PASS_THRU", "port_type": "INPUT/OUTPUT"}
            ]
            object_name = attributes.get("Lookup table name") or tx_name
        else:
            columns = _ports_as_columns(ports) if ports else [
                {"column_name": "PASS_THRU", "datatype": "varchar2", "precision": 50, "scale": 0,
                 "expression": "PASS_THRU", "port_type": "INPUT/OUTPUT"}
            ]
            object_name = inst_name

        imf_class = {
            "source": _CLASS_SOURCE,
            "target": _CLASS_TARGET,
            "expression": _CLASS_EXPRESSION,
            "lookup": _CLASS_LOOKUP,
            "mapplet": _CLASS_MAPPLET,
            "filter": _CLASS_FILTER,
            "input": _CLASS_INPUT,
            "output": _CLASS_OUTPUT,
        }[kind]
        node: dict[str, Any] = {
            "name": inst_name,
            "kind": kind,
            "pc_type": pc_type,
            "tx_id": c.next(),
            "grp_id": c.next(),
            "da_id": c.next(),
            "obj_id": c.next(),
            "imf_class": imf_class,
            "columns": columns,
            "object_name": object_name,
            "attributes": attributes,
            "ports": ports,
            "tx_name": tx_name,
            "saas_mapplet_id": _mapplet_saas_id(mapplet_guids, tx_name, inst_name)
            if kind == "mapplet" else "",
        }
        if kind == "mapplet":
            node["out_grp_id"] = c.next()
            if output_only:
                node["output_only"] = True
        node_meta[inst_name] = node

    param_names = _collect_mapping_connection_param_names(name, mapping, sess or None)
    flat_file_params = {
        pname for pname in param_names if _is_flat_file_lookup_connection_label(pname)
    }
    param_ids, parameters = _build_imf_connection_parameters(
        c, param_names, flat_file_params=flat_file_params,
    )
    default_param_id = param_ids.get("DBConnection_OLAP") or param_ids.get("Target") or next(iter(param_ids.values()))

    # Pre-allocate field IDs so links can be emitted before full objects.
    for node in node_meta.values():
        col_ids = []
        for col in node["columns"]:
            col_ids.append({
                "fld_id": c.next(),
                "adapt_id": c.next(),
                "ann_id": c.next(),
                "col": col,
            })
        node["col_ids"] = col_ids

    # Instance-level edges from PC connectors (skip omitted Source Definitions).
    edge_list: list[tuple[str, str]] = []
    seen_edges: set[tuple[str, str]] = set()
    for conn in connectors:
        frm = conn.get("from_instance") or ""
        to = conn.get("to_instance") or ""
        if not frm or not to or frm == to:
            continue
        if frm in skipped_source_defs or to in skipped_source_defs:
            continue
        if frm not in node_meta or to not in node_meta:
            continue
        edge = (frm, to)
        if edge in seen_edges:
            continue
        seen_edges.add(edge)
        edge_list.append(edge)

    # ConvTool inserts EXPR_* passthrough wrappers around mapplet / update boundaries
    # so the designer canvas matches Valid Conversion-Tool mappings.
    if (document_type or "").upper() != "DMAPPLET":
        edge_list = _insert_convtool_expr_wrappers(c, node_meta, edge_list)
        edge_list = _normalize_sde_mapping_topology(c, node_meta, edge_list, mapping)

    def _link_group_id(node: dict, role: str) -> int:
        """Mapplet links use Output (from) / Input (to); others use DefaultGroup."""
        if node["kind"] == "mapplet":
            if node.get("output_only"):
                return node["out_grp_id"]
            return node["out_grp_id"] if role == "from" else node["grp_id"]
        return node["grp_id"]

    def _group_name(node: dict, role: str) -> str:
        if node["kind"] == "mapplet":
            if node.get("output_only"):
                return "Output"
            return "Output" if role == "from" else "Input"
        return "DefaultGroup"

    def _make_link(from_node: dict, to_node: dict) -> dict:
        lid = c.next()
        from_grp = _link_group_id(from_node, "from")
        to_grp = _link_group_id(to_node, "to")
        return {
            "$$ID": lid, "$$class": 4,
            "name": (
                f"{from_node['name']}.{_group_name(from_node, 'from')}"
                f"_to_{to_node['name']}.{_group_name(to_node, 'to')}"
            ),
            "fromGroup": {"##ID": from_grp, "$$class": 5},
            "fromTransformation": {"##ID": from_node["tx_id"], "$$class": from_node["imf_class"]},
            "toGroup": {"##ID": to_grp, "$$class": 5},
            "toTransformation": {"##ID": to_node["tx_id"], "$$class": to_node["imf_class"]},
        }

    links: list[dict] = []
    for frm, to in edge_list:
        if frm not in node_meta or to not in node_meta:
            continue
        links.append(_make_link(node_meta[frm], node_meta[to]))

    transformations: list[dict] = []

    # Emit targets → mapplets → lookups → filters → expressions → inputs/outputs → sources
    kind_order = (
        "target", "mapplet", "lookup", "filter", "expression", "output", "input", "source",
    )
    ordered_nodes = [
        n for kind in kind_order for n in node_meta.values() if n["kind"] == kind
    ]

    for node in ordered_nodes:
        node_param = param_ids.get(
            _resolve_node_connection_param_name(node, name, mapping),
            default_param_id,
        )
        if node["kind"] == "target":
            transformations.append(_emit_target_tx(c, node, node_param))
        elif node["kind"] == "source":
            transformations.append(_emit_source_tx(c, node, node_param))
        elif node["kind"] == "lookup":
            transformations.append(_emit_lookup_tx(c, node, node_param))
        elif node["kind"] == "mapplet":
            transformations.append(_emit_mapplet_tx(c, node))
        elif node["kind"] == "filter":
            transformations.append(_emit_filter_tx(c, node))
        elif node["kind"] == "input":
            transformations.append(_emit_input_tx(c, node))
        elif node["kind"] == "output":
            transformations.append(_emit_output_tx(c, node))
        else:
            transformations.append(_emit_expression_tx(c, node))

    return _finalize_bin(
        name=name,
        ann1_id=ann1_id,
        ann2_id=ann2_id,
        ann_kv_id=ann_kv_id,
        links=links,
        parameters=parameters,
        transformations=transformations,
        document_type=document_type,
    )


def _emit_target_tx(
    c: _IdCounter,
    node: dict,
    param_id: int,
) -> dict:
    tgt_name = node["object_name"]
    reject_dir_id = c.next()
    reject_file_id = c.next()
    rules = [{"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"}]
    names_list = []
    for cinfo in node["col_ids"]:
        names_list.append({
            "$$ID": c.next(), "$$class": 28,
            "inputName": cinfo["col"]["column_name"],
            "outputName": str(cinfo["col"]["column_name"]).upper(),
        })
    rules.append({
        "$$ID": c.next(), "$$class": 22,
        "bulkRename": "false", "include": "true",
        "fieldNamesStr": "", "names": names_list,
    })

    fields = []
    obj_fields = []
    for cinfo in node["col_ids"]:
        col = cinfo["col"]
        fields.append({
            "$$ID": cinfo["fld_id"], "$$class": 14,
            "annotations": [{"$$ID": cinfo["ann_id"], "$$class": 2, "body": ""}],
            "adapterField": {"##ID": cinfo["adapt_id"], "$$class": 15},
            "defaultValue": "",
            "ignoreComparison": "false", "ignoreNullInputs": "false",
            "isDefaultValueUpdated": "false",
            "name": str(col["column_name"]).upper(),
            "platformType": {
                "##SID": "smd:com.informatica.metadata.seed.platform.Platform.typesystem/string",
                "$$class": 16,
            },
            "precision": int(col.get("precision") or 60),
            "scale": int(col.get("scale") or 0),
        })
        obj_fields.append({
            "$$ID": cinfo["adapt_id"], "$$class": 15,
            "name": str(col["column_name"]).upper(),
            "createable": "false", "externalId": "false",
            "fieldStatus": "UNDEFINED", "fieldType": "UNDEFINED",
            "filterable": "true", "foreignKey": "false", "generated": "false",
            "javaType": "", "key": "false", "label": "", "nativeName": "",
            "nativeType": _native(str(col.get("datatype", "varchar2"))),
            "newField": "false", "nullable": "true", "original": "false",
            "passthroughPort": "false",
            "precision": int(col.get("precision") or 60),
            "scale": int(col.get("scale") or 0),
            "sfIdLookup": "false", "unique": "false", "updateable": "false",
            "properties": [
                {"$$ID": c.next(), "$$class": 30, "name": "parentObjectLabel", "value": tgt_name},
                {"$$ID": c.next(), "$$class": 30, "name": "parentLabel", "value": tgt_name},
            ],
        })

    return {
        "$$ID": node["tx_id"], "$$class": _CLASS_TARGET,
        "annotations": [{
            "$$ID": c.next(), "$$class": 2,
            "body": _pc_annotation(node["pc_type"], node.get("attributes")),
        }],
        "augmented": "false", "createTime": "",
        "name": node["name"],
        "groups": [{
            "$$ID": node["grp_id"], "$$class": 5,
            "input": "true", "name": "DefaultGroup", "output": "false",
            "rules": rules,
        }],
        "sessionProperties": [
            {"$$ID": reject_dir_id, "$$class": 12,
             "name": "Reject file directory", "value": "$PMBadFileDir\\"},
            {"$$ID": reject_file_id, "$$class": 12,
             "name": "Reject filename", "value": f"{str(tgt_name).lower()}.bad"},
        ],
        "createTarget": "false", "fieldMappingMode": "MANUAL",
        "inputSorted": "false", "schemaProviderType": "SELECTED_OBJECT",
        "targetFieldsOrdered": "false",
        "updateColumns": [], "useLabels": "false", "useSequenceFields": "false",
        "fields": fields,
        "dataAdapter": {
            "$$ID": node["da_id"], "$$class": 13,
            "name": "", "codePage": "", "compatibleEngine": "",
            "connectionId": "",
            "connectionId$": {"##ID": param_id, "$$class": 9},
            "connectionSelectionType": "",
            "excludeDynamicFileNameField": "false",
            "fwConfigId": "", "multipleObject": "false",
            "objectType": "SINGLE", "typeSystem": "Oracle",
            "useDynamicFileName": "false",
            # Required by IICS MTT import — null writeOptions causes:
            # WriteOptions.getOperations() NPE
            "writeOptions": {
                "$$ID": c.next(), "$$class": 24,
                "batchSize": 0,
                "bulkApi": "false",
                "errorFileDirectory": "",
                "errorFilePrefix": "",
                "handleDecimalRoundOff": "false",
                "handleSpecialChars": "false",
                "operations": ["Insert", "Insert"],
                "setFieldsToNull": "false",
                "successFileDirectory": "",
                "successFilePrefix": "",
                "truncate": "false",
                "updateStrategyExpression": (
                    (node.get("attributes") or {}).get("Update Strategy Expression", "")
                ),
                "useErrorFile": "false",
                "useExactSrcNames": "false",
                "useSuccessFile": "false",
            },
            "object": {
                "$$ID": node["obj_id"], "$$class": 23,
                "name": tgt_name, "customQuery": "",
                "dbSchema": "", "label": tgt_name,
                "objectName": "", "objectType": "", "parentPath": "",
                "path": tgt_name, "retainMetadata": "false",
                "fields": obj_fields,
            },
        },
    }


def _emit_source_tx(c: _IdCounter, node: dict, param_id: int) -> dict:
    object_name = node["object_name"]
    custom_query = (node.get("attributes") or {}).get("Sql Query", "")
    sq_fields = []
    obj_fields = []
    for cinfo in node["col_ids"]:
        col = cinfo["col"]
        sq_fields.append({
            "$$ID": cinfo["fld_id"], "$$class": 14,
            "annotations": [{"$$ID": cinfo["ann_id"], "$$class": 2, "body": ""}],
            "businessLabel": "", "datatype": "string",
            "description": "", "label": col["column_name"],
            "name": col["column_name"],
            "nullable": "true", "portType": "OUTPUT",
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
        })
        obj_fields.append({
            "$$ID": cinfo["adapt_id"], "$$class": 15,
            "name": col["column_name"],
            "createable": "false", "externalId": "false",
            "fieldStatus": "UNDEFINED", "fieldType": "UNDEFINED",
            "filterable": "true", "foreignKey": "false", "generated": "false",
            "javaType": "", "key": "false", "label": "", "nativeName": "",
            "nativeType": _native(str(col.get("datatype", "varchar2"))),
            "newField": "false", "nullable": "true", "original": "false",
            "passthroughPort": "false",
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
            "sfIdLookup": "false", "unique": "false", "updateable": "false",
            "properties": [
                {"$$ID": c.next(), "$$class": 30, "name": "parentObjectLabel", "value": object_name},
                {"$$ID": c.next(), "$$class": 30, "name": "parentLabel", "value": object_name},
            ],
        })

    return {
        "$$ID": node["tx_id"], "$$class": _CLASS_SOURCE,
        "annotations": [{
            "$$ID": c.next(), "$$class": 2,
            "body": _pc_annotation(node["pc_type"], node.get("attributes")),
        }],
        "augmented": "false", "createTime": "",
        "name": node["name"],
        "groups": [{
            "$$ID": node["grp_id"], "$$class": 5,
            "input": "false", "name": "DefaultGroup", "output": "true",
            "rules": [{"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"}],
            "fields": sq_fields,
        }],
        "dataAdapter": {
            "$$ID": node["da_id"], "$$class": 13,
            "name": "", "codePage": "", "compatibleEngine": "",
            "connectionId": "",
            "connectionId$": {"##ID": param_id, "$$class": 9},
            "connectionSelectionType": "",
            "excludeDynamicFileNameField": "false",
            "fwConfigId": "", "multipleObject": "false",
            "objectType": "SINGLE", "typeSystem": "Oracle",
            "useDynamicFileName": "false",
            "customQuery": custom_query,
            # Required by IICS MTT import for source adapters — null readOptions causes:
            # ReadOptions.isSelectDistinct() NPE
            "readOptions": {
                "$$ID": c.next(), "$$class": 26,
                "commandType": 0,
                "descending": "false",
                "filterCondition": str((node.get("attributes") or {}).get("Source Filter", "")),
                "flatFileCommand": "",
                "queryAll": "false",
                "rowLimit": 0,
                "selectDistinct": "false",
                "userDefinedJoin": str((node.get("attributes") or {}).get("User Defined Join", "")),
                "advancedFilterCondition": "",
                "requestXml": "",
                "sortFieldValues": "",
            },
            "object": {
                "$$ID": node["obj_id"], "$$class": 23,
                "name": object_name, "customQuery": custom_query,
                "dbSchema": "", "label": object_name,
                "objectName": "", "objectType": "", "parentPath": "",
                "path": object_name, "retainMetadata": "false",
                "fields": obj_fields,
            },
        },
    }


def _emit_expression_tx(c: _IdCounter, node: dict) -> dict:
    """Expression / Update Strategy (Filter and Lookup have dedicated emitters)."""
    attrs = node.get("attributes") or {}
    ports_out = []
    for cinfo in node["col_ids"]:
        col = cinfo["col"]
        expression = col.get("expression") or col["column_name"]
        # Update Strategy keeps ports as pass-through expressions.
        ports_out.append({
            "$$ID": cinfo["fld_id"], "$$class": 19,
            "annotations": [{"$$ID": cinfo["ann_id"], "$$class": 2, "body": ""}],
            "businessLabel": "", "datatype": "string",
            "description": "", "expression": expression,
            "expressionType": "EXPRESSION_RETURN",
            "label": col["column_name"],
            "name": col["column_name"],
            "nullable": "true",
            "portType": "INPUT_OUTPUT",
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
        })

    advanced = [
        {"$$ID": c.next(), "$$class": 18, "name": "Tracing Level",
         "value": attrs.get("Tracing Level") or "Normal"},
    ]
    pc_type = (node.get("pc_type") or "").lower()
    if "update strategy" in pc_type and attrs.get("Update Strategy Expression"):
        advanced.append({
            "$$ID": c.next(), "$$class": 18,
            "name": "Update Strategy Expression",
            "value": attrs.get("Update Strategy Expression", ""),
        })
        advanced.append({
            "$$ID": c.next(), "$$class": 18,
            "name": "Forward Rejected Rows",
            "value": _yes_no_to_bool(attrs.get("Forward Rejected Rows"), "true"),
        })

    return {
        "$$ID": node["tx_id"], "$$class": _CLASS_EXPRESSION,
        "annotations": [{
            "$$ID": c.next(), "$$class": 2,
            "body": _pc_annotation(node["pc_type"], attrs),
        }],
        "augmented": "false", "createTime": "",
        "name": node["name"],
        "advancedProperties": advanced,
        "groups": [{
            "$$ID": node["grp_id"], "$$class": 5,
            "input": "true", "name": "DefaultGroup", "output": "true",
            "rules": [{"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"}],
            "fields": ports_out,
        }],
    }


def _emit_filter_tx(c: _IdCounter, node: dict) -> dict:
    """Native CDI Filter (TmplFilter) with filterCondition from PC attributes."""
    attrs = node.get("attributes") or {}
    condition = attrs.get("Filter Condition") or ""
    fields = []
    for cinfo in node["col_ids"]:
        col = cinfo["col"]
        fields.append({
            "$$ID": cinfo["fld_id"], "$$class": 14,
            "annotations": [{"$$ID": cinfo["ann_id"], "$$class": 2, "body": ""}],
            "defaultValue": "",
            "ignoreComparison": "false",
            "ignoreNullInputs": "false",
            "isDefaultValueUpdated": "false",
            "name": col["column_name"],
            "platformType": {
                "##SID": _platform_type_sid(str(col.get("datatype", "varchar2"))),
                "$$class": 16,
            },
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
        })
    return {
        "$$ID": node["tx_id"], "$$class": _CLASS_FILTER,
        "annotations": [{
            "$$ID": c.next(), "$$class": 2,
            "body": _pc_annotation(node["pc_type"], attrs),
        }],
        "augmented": "false", "createTime": "",
        "name": node["name"],
        "filterCondition": condition,
        "advancedProperties": [
            {"$$ID": c.next(), "$$class": 18, "name": "Tracing Level",
             "value": attrs.get("Tracing Level") or "Normal"},
            {"$$ID": c.next(), "$$class": 18, "name": "Filter Condition", "value": condition},
        ],
        "groups": [{
            "$$ID": node["grp_id"], "$$class": 5,
            "input": "true", "name": "DefaultGroup", "output": "true",
            "rules": [{"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"}],
        }],
        "fields": fields,
    }


def _emit_input_tx(c: _IdCounter, node: dict) -> dict:
    """DMAPPLET Input transformation (TmplInput)."""
    attrs = node.get("attributes") or {}
    fields = []
    for cinfo in node["col_ids"]:
        col = cinfo["col"]
        fields.append({
            "$$ID": cinfo["fld_id"], "$$class": 14,
            "defaultValue": "",
            "ignoreComparison": "false",
            "ignoreNullInputs": "false",
            "isDefaultValueUpdated": "false",
            "name": col["column_name"],
            "platformType": {
                "##SID": _platform_type_sid(str(col.get("datatype", "varchar2"))),
                "$$class": 16,
            },
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
        })
    return {
        "$$ID": node["tx_id"], "$$class": _CLASS_INPUT,
        "annotations": [{
            "$$ID": c.next(), "$$class": 2,
            "body": _pc_annotation(node["pc_type"], attrs),
        }],
        "augmented": "false", "createTime": "",
        "name": "INPUT" if str(node["name"]).strip().lower() == "input" else node["name"],
        "advancedProperties": [
            {"$$ID": c.next(), "$$class": 18, "name": "Optional", "value": "true"},
        ],
        "fields": fields,
        "groups": [{
            "$$ID": node["grp_id"], "$$class": 5,
            "input": "false", "name": "DefaultGroup", "output": "true",
            "fields": [],
        }],
    }


def _emit_output_tx(c: _IdCounter, node: dict) -> dict:
    """DMAPPLET Output transformation (TmplOutput) — ConvTool-aligned shape."""
    attrs = node.get("attributes") or {}
    fields = []
    name_rules = []
    for cinfo in node["col_ids"]:
        col = cinfo["col"]
        fields.append({
            "$$ID": cinfo["fld_id"], "$$class": 14,
            "defaultValue": "",
            "ignoreComparison": "false",
            "ignoreNullInputs": "false",
            "isDefaultValueUpdated": "false",
            "name": col["column_name"],
            "platformType": {
                "##SID": _platform_type_sid(str(col.get("datatype", "varchar2"))),
                "$$class": 16,
            },
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
        })
        name_rules.append({
            "$$ID": c.next(), "$$class": 28,
            "inputName": col["column_name"],
            "outputName": col["column_name"],
        })
    return {
        "$$ID": node["tx_id"], "$$class": _CLASS_OUTPUT,
        "annotations": [{
            "$$ID": c.next(), "$$class": 2,
            "body": _pc_annotation(node["pc_type"], attrs),
        }],
        "augmented": "false", "createTime": "",
        "name": "OUTPUT" if str(node["name"]).strip().lower() == "output" else node["name"],
        "advancedProperties": [
            {"$$ID": c.next(), "$$class": 18, "name": "Optional", "value": "true"},
        ],
        "fields": fields,
        "groups": [{
            "$$ID": node["grp_id"], "$$class": 5,
            "input": "true", "name": "DefaultGroup", "output": "false",
            "rules": [
                {"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"},
                {
                    "$$ID": c.next(), "$$class": 22,
                    "bulkRename": "false", "include": "true",
                    "fieldNamesStr": "", "names": name_rules,
                },
            ],
        }],
    }


def _emit_lookup_tx(c: _IdCounter, node: dict, param_id: int) -> dict:
    """Native CDI Lookup (TmplLookup) aligned to Informatica ConvTool IMF shape."""
    attrs = node.get("attributes") or {}
    table_name = attrs.get("Lookup table name") or node.get("object_name") or node["name"]
    conditions = _parse_lookup_conditions(attrs.get("Lookup condition", ""))
    lookup_conditions = [
        {
            "$$ID": c.next(), "$$class": _CLASS_LOOKUP_CONDITION,
            "leftOperand": item["leftOperand"],
            "operator": item["operator"],
            "rightOperand": item["rightOperand"],
        }
        for item in conditions
    ]

    input_port_names = []
    return_port_name = ""
    fields = []
    obj_fields = []
    for cinfo in node["col_ids"]:
        col = cinfo["col"]
        port_type = str(col.get("port_type") or "").upper()
        name = str(col["column_name"])
        if "INPUT" in port_type and "LOOKUP" not in port_type:
            input_port_names.append(name)
        if not return_port_name and ("OUTPUT" in port_type or "LOOKUP" in port_type):
            return_port_name = name
        fields.append({
            "$$ID": cinfo["fld_id"], "$$class": 14,
            "annotations": [{"$$ID": cinfo["ann_id"], "$$class": 2, "body": ""}],
            "adapterField": {"##ID": cinfo["adapt_id"], "$$class": 15},
            "defaultValue": "",
            "ignoreComparison": "false",
            "ignoreNullInputs": "false",
            "isDefaultValueUpdated": "false",
            "name": name,
            "platformType": {
                "##SID": _platform_type_sid(str(col.get("datatype", "varchar2"))),
                "$$class": 16,
            },
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
        })
        obj_fields.append({
            "$$ID": cinfo["adapt_id"], "$$class": 15,
            "name": name,
            "createable": "false", "externalId": "false",
            "fieldStatus": "UNDEFINED", "fieldType": "UNDEFINED",
            "filterable": "true", "foreignKey": "false", "generated": "false",
            "javaType": "", "key": "false", "label": name, "nativeName": name,
            "nativeType": _native(str(col.get("datatype", "varchar2"))),
            "newField": "false", "nullable": "true", "original": "false",
            "passthroughPort": "false",
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
            "sfIdLookup": "false", "unique": "false", "updateable": "false",
            "properties": [
                {"$$ID": c.next(), "$$class": 30, "name": "parentObjectLabel", "value": table_name},
                {"$$ID": c.next(), "$$class": 30, "name": "parentLabel", "value": table_name},
            ],
        })

    if not return_port_name and fields:
        return_port_name = fields[0]["name"]

    multi_policy = attrs.get("Lookup policy on multiple match") or "Use First Value"
    if "last" in multi_policy.lower():
        multiple_match_policy = "USE_LAST_VALUE"
    elif "error" in multi_policy.lower() or "report" in multi_policy.lower():
        multiple_match_policy = "REPORT_ERROR"
    else:
        multiple_match_policy = "USE_FIRST_VALUE"

    custom_query = attrs.get("Lookup Sql Override") or ""
    advanced = [
        {"$$ID": c.next(), "$$class": 18, "name": "Tracing Level",
         "value": attrs.get("Tracing Level") or "Normal"},
        {"$$ID": c.next(), "$$class": 18, "name": "Optional", "value": "true"},
        {"$$ID": c.next(), "$$class": 18, "name": "Lookup source is static",
         "value": _yes_no_to_bool(attrs.get("Lookup source is static"))},
        {"$$ID": c.next(), "$$class": 18, "name": "Lookup caching enabled",
         "value": _yes_no_to_bool(attrs.get("Lookup caching enabled"), "true")},
        {"$$ID": c.next(), "$$class": 18, "name": "Lookup Source Filter",
         "value": attrs.get("Lookup Source Filter") or ""},
        {"$$ID": c.next(), "$$class": 18, "name": "Lookup Data Cache Size",
         "value": attrs.get("Lookup Data Cache Size") or "AUTO"},
        {"$$ID": c.next(), "$$class": 18, "name": "Lookup Index Cache Size",
         "value": attrs.get("Lookup Index Cache Size") or "AUTO"},
    ]

    return {
        "$$ID": node["tx_id"], "$$class": _CLASS_LOOKUP,
        "annotations": [{
            "$$ID": c.next(), "$$class": 2,
            "body": _pc_annotation(node["pc_type"], attrs),
        }],
        "augmented": "false", "createTime": "",
        "name": node["name"],
        "advancedProperties": advanced,
        "unconnected": "false",
        "useLabels": "false",
        "multipleMatchPolicy": multiple_match_policy,
        "returnPortName": return_port_name,
        "inputPortNames": input_port_names,
        "advancedInputPortNames": [],
        "associatedFields": [],
        "lookupCondition": "",
        "lookupConditions": lookup_conditions,
        "groups": [{
            "$$ID": node["grp_id"], "$$class": 5,
            "input": "true", "name": "DefaultGroup", "output": "true",
            "rules": [{"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"}],
        }],
        "fields": fields,
        "dataAdapter": {
            "$$ID": node["da_id"], "$$class": 13,
            "name": "", "codePage": "", "compatibleEngine": "",
            "connectionId": "",
            "connectionId$": {"##ID": param_id, "$$class": 9},
            "connectionSelectionType": "",
            "excludeDynamicFileNameField": "false",
            "fwConfigId": "", "multipleObject": "false",
            "objectType": "SINGLE", "typeSystem": "Oracle",
            "useDynamicFileName": "false",
            "customQuery": custom_query,
            "readOptions": {
                "$$ID": c.next(), "$$class": 26,
                "commandType": 0, "descending": "false",
                "filterCondition": attrs.get("Lookup Source Filter") or "",
                "flatFileCommand": "", "queryAll": "false", "rowLimit": 0,
                "selectDistinct": "false", "userDefinedJoin": "",
                "advancedFilterCondition": "", "requestXml": "", "sortFieldValues": "",
            },
            "writeOptions": {
                "$$ID": c.next(), "$$class": 24,
                "batchSize": 0, "bulkApi": "false",
                "errorFileDirectory": "", "errorFilePrefix": "",
                "handleDecimalRoundOff": "false", "handleSpecialChars": "false",
                "operations": ["Insert", "Insert"],
                "setFieldsToNull": "false",
                "successFileDirectory": "", "successFilePrefix": "",
                "truncate": "false", "updateStrategyExpression": "",
                "useErrorFile": "false", "useExactSrcNames": "false",
                "useSuccessFile": "false",
            },
            "object": {
                "$$ID": node["obj_id"], "$$class": 23,
                "name": table_name, "customQuery": custom_query,
                "dbSchema": "", "label": table_name,
                "objectName": table_name, "objectType": "", "parentPath": "",
                "path": table_name, "retainMetadata": "false",
                "fields": obj_fields,
            },
        },
    }


def _emit_mapplet_tx(c: _IdCounter, node: dict) -> dict:
    """
    Native CDI Mapplet shell (TmplMapplet).

    saasMappletId must reference a companion DMAPPLET asset guid (@{guid}).
    INPUT/OUTPUT groups are built from the folder MAPPLET interface ports.
    """
    attrs = node.get("attributes") or {}
    input_fields = []
    output_fields = []
    for cinfo in node["col_ids"]:
        col = cinfo["col"]
        port_type = str(col.get("port_type") or "INPUT/OUTPUT").upper()
        group = str(col.get("mapplet_group") or "").upper()
        field = {
            "$$ID": cinfo["fld_id"], "$$class": 14,
            "annotations": [{"$$ID": cinfo["ann_id"], "$$class": 2, "body": ""}],
            "defaultValue": "",
            "ignoreComparison": "false",
            "ignoreNullInputs": "false",
            "isDefaultValueUpdated": "false",
            "name": col["column_name"],
            "platformType": {
                "##SID": _platform_type_sid(str(col.get("datatype", "varchar2"))),
                "$$class": 16,
            },
            "precision": int(col.get("precision") or 50),
            "scale": int(col.get("scale") or 0),
        }
        if group == "OUTPUT" or ("OUTPUT" in port_type and "INPUT" not in port_type):
            output_fields.append(field)
        else:
            input_fields.append(field)

    if not input_fields and not output_fields and node["col_ids"]:
        # Fallback: treat all ports as input when PC port types are absent.
        input_fields = [
            {
                "$$ID": cinfo["fld_id"], "$$class": 14,
                "annotations": [{"$$ID": cinfo["ann_id"], "$$class": 2, "body": ""}],
                "defaultValue": "",
                "ignoreComparison": "false",
                "ignoreNullInputs": "false",
                "isDefaultValueUpdated": "false",
                "name": cinfo["col"]["column_name"],
                "platformType": {
                    "##SID": _platform_type_sid(str(cinfo["col"].get("datatype", "varchar2"))),
                    "$$class": 16,
                },
                "precision": int(cinfo["col"].get("precision") or 50),
                "scale": int(cinfo["col"].get("scale") or 0),
            }
            for cinfo in node["col_ids"]
        ]

    out_grp_id = node.get("out_grp_id") or c.next()
    saas_id = node.get("saas_mapplet_id") or ""
    output_only = bool(node.get("output_only"))
    result: dict[str, Any] = {
        "$$ID": node["tx_id"], "$$class": _CLASS_MAPPLET,
        "annotations": [{
            "$$ID": c.next(), "$$class": 2,
            "body": _pc_annotation(node["pc_type"], attrs),
        }],
        "augmented": "false", "createTime": "",
        "name": node["name"],
        "advancedProperties": [
            {"$$ID": c.next(), "$$class": 18, "name": "Tracing Level",
             "value": attrs.get("Tracing Level") or "Normal"},
            {"$$ID": c.next(), "$$class": 18, "name": "Optional", "value": "true"},
        ],
        "active": "false",
        "fieldMappingMode": "BY_NAME",
        "hasFixedReferences": "false",
        "saasMappletId": saas_id,
        "type": "NATIVE",
        "validForEngines": ["CDI", "CDI_E"],
        "parameterBindings": [],
        "outputGroups": [{
            "$$ID": c.next(), "$$class": _CLASS_TX_FIELD_GROUP,
            "name": "Output" if output_only else "OUTPUT",
            "fields": output_fields,
        }],
        "dataAdapter": {
            "$$ID": node["da_id"], "$$class": _CLASS_MAPPLET_ADAPTER,
            "name": node["name"],
        },
    }
    if output_only:
        result["groups"] = [{
            "$$ID": out_grp_id, "$$class": 5,
            "input": "false", "name": "Output", "output": "true",
        }]
    else:
        result["inputGroups"] = [{
            "$$ID": c.next(), "$$class": _CLASS_TX_FIELD_GROUP,
            "name": "Input",
            "fields": input_fields,
        }]
        result["groups"] = [
            {
                "$$ID": node["grp_id"], "$$class": 5,
                "input": "true", "name": "Input", "output": "false",
                "rules": [{"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"}],
            },
            {
                "$$ID": out_grp_id, "$$class": 5,
                "input": "false", "name": "Output", "output": "true",
            },
        ]
    return result


def _build_bin_legacy_linear(mapping: dict, folder_data: dict) -> bytes:
    """Legacy SQ → Expression → Target chain for mappings without instance graph."""
    c = _IdCounter()
    name = mapping["mapping_name"]

    sources = folder_data.get("sources", [])
    targets = folder_data.get("targets", [])
    txs = mapping.get("transformations", [])
    sess = next(
        (s for s in folder_data.get("sessions", []) if s.get("mapping_name") == name),
        folder_data.get("sessions", [{}])[0] if folder_data.get("sessions") else {},
    )
    attrs = sess.get("attributes", {}) if sess else {}

    ann1_id = c.next()
    ann2_id = c.next()
    ann_kv_id = c.next()

    target_defs = []
    for tgt in targets:
        tgt_tx_id = c.next()
        tgt_grp_id = c.next()
        tgt_da_id = c.next()
        col_data = []
        for col in tgt.get("columns", []):
            col_data.append({
                "fld_id": c.next(), "adapt_id": c.next(), "ann_id": c.next(), "col": col,
            })
        target_defs.append({
            "name": tgt["target_name"], "tx_id": tgt_tx_id,
            "grp_id": tgt_grp_id, "da_id": tgt_da_id, "cols": col_data,
            "object_name": tgt["target_name"], "pc_type": "Target Definition",
            "attributes": {},
        })

    expr_defs = []
    for tx in txs:
        port_data = []
        for p in tx.get("ports", []):
            port_data.append({"fld_id": c.next(), "ann_id": c.next(), "col": {
                "column_name": p.get("port_name", "FIELD"),
                "datatype": p.get("datatype", "varchar2"),
                "precision": p.get("precision") or 50,
                "scale": p.get("scale") or 0,
                "expression": p.get("expression") or p.get("port_name", ""),
            }})
        expr_defs.append({
            "name": tx["transformation_name"],
            "pc_type": tx.get("transformation_type", "Expression"),
            "tx_id": c.next(), "grp_id": c.next(),
            "col_ids": port_data,
            "attributes": tx.get("attributes") or {},
        })

    src_defs = []
    for src in sources:
        col_data = []
        for col in src.get("columns", []):
            col_data.append({
                "fld_id": c.next(), "adapt_id": c.next(), "ann_id": c.next(), "col": col,
            })
        src_defs.append({
            "name": f"SQ_{src['source_name']}",
            "object_name": src["source_name"],
            "pc_type": "Source Qualifier",
            "tx_id": c.next(), "grp_id": c.next(), "da_id": c.next(), "obj_id": c.next(),
            "col_ids": col_data,
            "attributes": {"Sql Query": attrs.get("Sql Query", "")},
        })

    param_id = c.next()
    anon_id = c.next()

    links = []
    if src_defs:
        sq = src_defs[0]
        if expr_defs:
            links.append({
                "$$ID": c.next(), "$$class": 4,
                "name": f"{sq['name']}.DefaultGroup_to_{expr_defs[0]['name']}.DefaultGroup",
                "fromGroup": {"##ID": sq["grp_id"], "$$class": 5},
                "fromTransformation": {"##ID": sq["tx_id"], "$$class": _CLASS_SOURCE},
                "toGroup": {"##ID": expr_defs[0]["grp_id"], "$$class": 5},
                "toTransformation": {"##ID": expr_defs[0]["tx_id"], "$$class": _CLASS_EXPRESSION},
            })
            for i in range(len(expr_defs) - 1):
                links.append({
                    "$$ID": c.next(), "$$class": 4,
                    "name": (
                        f"{expr_defs[i]['name']}.DefaultGroup_to_"
                        f"{expr_defs[i + 1]['name']}.DefaultGroup"
                    ),
                    "fromGroup": {"##ID": expr_defs[i]["grp_id"], "$$class": 5},
                    "fromTransformation": {
                        "##ID": expr_defs[i]["tx_id"], "$$class": _CLASS_EXPRESSION,
                    },
                    "toGroup": {"##ID": expr_defs[i + 1]["grp_id"], "$$class": 5},
                    "toTransformation": {
                        "##ID": expr_defs[i + 1]["tx_id"], "$$class": _CLASS_EXPRESSION,
                    },
                })
            if target_defs:
                links.append({
                    "$$ID": c.next(), "$$class": 4,
                    "name": (
                        f"{expr_defs[-1]['name']}.DefaultGroup_to_"
                        f"{target_defs[0]['name']}.DefaultGroup"
                    ),
                    "fromGroup": {"##ID": expr_defs[-1]["grp_id"], "$$class": 5},
                    "fromTransformation": {
                        "##ID": expr_defs[-1]["tx_id"], "$$class": _CLASS_EXPRESSION,
                    },
                    "toGroup": {"##ID": target_defs[0]["grp_id"], "$$class": 5},
                    "toTransformation": {
                        "##ID": target_defs[0]["tx_id"], "$$class": _CLASS_TARGET,
                    },
                })
        elif target_defs:
            links.append({
                "$$ID": c.next(), "$$class": 4,
                "name": f"{sq['name']}.DefaultGroup_to_{target_defs[0]['name']}.DefaultGroup",
                "fromGroup": {"##ID": sq["grp_id"], "$$class": 5},
                "fromTransformation": {"##ID": sq["tx_id"], "$$class": _CLASS_SOURCE},
                "toGroup": {"##ID": target_defs[0]["grp_id"], "$$class": 5},
                "toTransformation": {
                    "##ID": target_defs[0]["tx_id"], "$$class": _CLASS_TARGET,
                },
            })

    parameters = [{
        "$$ID": param_id, "$$class": 9,
        "input": "true", "output": "false",
        "precision": 0, "scale": 0,
        "allowRuntimeOverride": "true",
        "expressionVariable": "false",
        "label": "",
        "name": "DBConnection_OLAP",
        "anonymousType": {
            "$$ID": anon_id, "$$class": 11,
            "name": "", "isVisible": "false",
            "subType": "", "typeSystem": "Oracle", "connectionType": "Oracle",
        },
    }]

    transformations: list[dict] = []
    for tdef in target_defs:
        node = {
            "name": tdef["name"], "object_name": tdef["object_name"], "pc_type": tdef["pc_type"],
            "tx_id": tdef["tx_id"], "grp_id": tdef["grp_id"], "da_id": tdef["da_id"],
            "obj_id": c.next(), "col_ids": tdef["cols"], "attributes": {},
        }
        transformations.append(_emit_target_tx(c, node, param_id))
    for edef in expr_defs:
        node = {
            "name": edef["name"], "pc_type": edef["pc_type"],
            "tx_id": edef["tx_id"], "grp_id": edef["grp_id"],
            "col_ids": edef["col_ids"], "attributes": edef["attributes"],
        }
        transformations.append(_emit_expression_tx(c, node))
    for sdef in src_defs:
        node = {
            "name": sdef["name"], "object_name": sdef["object_name"], "pc_type": sdef["pc_type"],
            "tx_id": sdef["tx_id"], "grp_id": sdef["grp_id"], "da_id": sdef["da_id"],
            "obj_id": sdef["obj_id"], "col_ids": sdef["col_ids"], "attributes": sdef["attributes"],
        }
        transformations.append(_emit_source_tx(c, node, param_id))

    return _finalize_bin(
        name=name,
        ann1_id=ann1_id,
        ann2_id=ann2_id,
        ann_kv_id=ann_kv_id,
        links=links,
        parameters=parameters,
        transformations=transformations,
    )


# ── PowerCenter XML Task builders (matches IICS import validation model) ────

def _resolve_remediated_xml(
    remediated_dir: Path, json_stem: str, mapping_name: str,
) -> tuple[Path, str]:
    for candidate in (f"{mapping_name}_remediated.xml", f"{json_stem}_remediated.xml"):
        path = remediated_dir / candidate
        if path.exists():
            return path, candidate
    raise FileNotFoundError(
        f"No remediated XML for mapping '{mapping_name}' (source={json_stem}) in {remediated_dir}"
    )


def _ensure_reusable_transformations(
    folder_data: dict,
    json_file_name: str,
    remediated_xml_dir: Path,
) -> None:
    """Backfill folder-level reusable TRANSFORMATION defs when parsed JSON lacks them."""
    if folder_data.get("reusable_transformations"):
        return
    from xml.etree import ElementTree as ET

    from business.parser.mapping_parser import MappingParser
    from data.models.mapping_model import to_plain_dict

    stem = Path(json_file_name).stem
    parser = MappingParser()
    for candidate in (
        remediated_xml_dir / f"{stem}.XML",
        remediated_xml_dir / f"{stem}.xml",
        remediated_xml_dir / f"{stem}_remediated.xml",
        Path("input_xml") / f"{stem}.XML",
        Path("input_xml") / f"{stem}.xml",
    ):
        if not candidate.exists():
            continue
        folder_el = ET.parse(candidate).getroot().find(".//FOLDER")
        if folder_el is None:
            continue
        folder_data["reusable_transformations"] = [
            to_plain_dict(item)
            for item in parser.parse_reusable_transformations(folder_el)
        ]
        return


def _build_pcxml_template_bin(
    mapping: dict, folder_data: dict, parsed: dict, xml_filename: str,
    conn_param_name: str = "DBConnection_OLAP",
) -> bytes:
    name = mapping["mapping_name"]
    content = {
        "$$IID": "stringIdentity:@3",
        "$$class": 1,
        "name": name,
        "description": (
            f"Packaged remediated PowerCenter XML {xml_filename} "
            f"for task/conversion execution."
        ),
        "sourceXml": xml_filename,
        "sourceXmlFileRecordId": "@4",
        "nativeCdiMapping": False,
        "executionStrategy": "POWERCENTER_XML_TASK",
        "supportedExecutionPaths": [
            "Run as PowerCenter XML task payload",
            "Convert remediated PowerCenter XML to cloud-native CDI objects",
            "Deploy remediated PowerCenter XML through IICS APIs",
        ],
        "conversionNote": (
            "Modified PowerCenter XML cannot be uploaded directly as a native CDI mapping. "
            "This package preserves the remediated XML and extracted metadata for supported "
            "task, conversion, or API workflows."
        ),
        "repository": parsed.get("repository", {}),
        "folder": folder_data.get("folder_name", ""),
        "parameters": [{
            "$$class": 10,
            "input": "true",
            "output": "false",
            "name": conn_param_name,
            "anonymousType": {
                "$$class": 12,
                "typeSystem": "Oracle",
                "connectionType": "Oracle",
            },
        }],
        "sources": folder_data.get("sources", []),
        "targets": folder_data.get("targets", []),
        "transformations": mapping.get("transformations", []),
        "connectors": mapping.get("connectors", []),
        "instances": mapping.get("instances", []),
        "sqlOverrides": mapping.get("sql_overrides", []),
    }
    return json.dumps({"content": content}, separators=(",", ":")).encode("utf-8")


def _build_dtemplate_zip_pcxml(
    mapping: dict,
    folder_data: dict,
    parsed: dict,
    remediated_path: Path,
    xml_filename: str,
    guid: str,
    conn_param_name: str = "DBConnection_OLAP",
) -> bytes:
    name = mapping["mapping_name"]
    now = int(time.time() * 1000)
    preview = f"Generated preview placeholder for {name}\n".encode("utf-8")
    template_bin = _build_pcxml_template_bin(
        mapping, folder_data, parsed, xml_filename, conn_param_name,
    )
    xml_bytes = remediated_path.read_bytes()

    mapping_template = [{
        "@type": "mappingTemplate",
        "id": "@1",
        "name": name,
        "description": f"Remediated PowerCenter XML source for task/conversion : {name}",
        "autoExpireObject": False,
        "bundleVersion": "0",
        "assetFrsGuid": guid,
        "templateId": "@3",
        "remediatedPowerCenterXmlFileRecordId": "@4",
        "executionStrategy": "POWERCENTER_XML_TASK",
        "nativeCdiMapping": False,
        "deployTime": now,
        "hasParameters": True,
        "valid": True,
        "fixedConnection": False,
        "hasParametersDeployed": True,
        "fixedConnectionDeployed": False,
        "isSchemaValidationEnabled": False,
        "tasks": 1,
        "mappingPreviewFileRecordId": "@2",
        "documentType": "",
        "allowMaxFieldLength": False,
        "specialCharacterSupport": True,
        "references": [],
    }]
    file_record = [
        {
            "@type": "fileRecord", "id": "@3", "name": name,
            "type": "IMFOBJECT", "size": len(template_bin),
            "attachTime": now,
            "additionalInfo": "com.informatica.metadata.template.common.Template",
        },
        {
            "@type": "fileRecord", "id": "@2",
            "name": f"{name}_preview.jpeg", "type": "IMAGE",
            "size": len(preview), "attachTime": now,
        },
        {
            "@type": "fileRecord", "id": "@4",
            "name": xml_filename, "type": "POWERCENTER_XML",
            "size": len(xml_bytes), "attachTime": now,
            "additionalInfo": (
                "Remediated PowerCenter XML. Use as PowerCenter task input, "
                "conversion source, or IICS API payload."
            ),
        },
    ]
    metadata_meta = [{"@type": "objectRef", "id": "@1", "type": "mappingTemplate"}]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mappingTemplate.json", json.dumps(mapping_template, separators=(",", ":")))
        zf.writestr("fileRecord.json", json.dumps(file_record, separators=(",", ":")))
        zf.writestr("bin/@2.bin", preview)
        zf.writestr("bin/@3.bin", template_bin.decode("utf-8"))
        zf.writestr("bin/@4.bin", xml_bytes)
        zf.writestr("metadata.meta", json.dumps(metadata_meta, separators=(",", ":")))
    return buf.getvalue()


_STANDARD_SESSION_PROPS = [
    "Allow Temporary Sequence for Pushdown",
    "Allow Temporary View for Pushdown",
    "Data Column Delimiter",
    "DTM buffer size",
    "Error Log File Name",
    "Pushdown Optimization",
]


def _build_session_properties_list(session: dict | None) -> list[dict]:
    attrs = session.get("attributes", {}) if session else {}
    props: list[dict] = []
    seen: set[str] = set()
    for key in _STANDARD_SESSION_PROPS:
        if key in attrs:
            props.append({"name": key, "value": str(attrs[key]), "recommended": False})
            seen.add(key)
    for key, val in attrs.items():
        if key not in seen and val is not None:
            props.append({"name": key, "value": str(val), "recommended": False})
    if not any(p["name"] == "Data Column Delimiter" for p in props):
        props.insert(2, {"name": "Data Column Delimiter", "value": "|", "recommended": False})
    if not any(p["name"] == "Error Log File Name" for p in props):
        props.append({"name": "Error Log File Name", "value": "PMError.log", "recommended": False})
    return props


def _build_mtt_parameters(
    folder_data: dict,
    conn_guid: str,
    conn_param_name: str = "DBConnection_OLAP",
) -> list[dict]:
    """Build MTT connection parameters — one TARGET entry per target table."""
    parameters: list[dict] = []
    for idx, tgt in enumerate(folder_data.get("targets", []), start=1):
        obj_name = tgt.get("target_name") or tgt.get("name", "")
        if not obj_name:
            continue
        parameters.append({
            "@type": "mtTaskParameter",
            "id": idx,
            "name": f"${obj_name}$",
            "type": "TARGET",
            "label": conn_param_name,
            "targetConnectionId": f"@{conn_guid}",
            "targetObject": obj_name,
            "targetObjectLabel": obj_name,
            "operationType": "Insert",
            "truncateTarget": False,
            "runtimeParameterData": {
                "@type": "mtTaskRuntimeParameterData",
                "isConnectionRuntimeParameter": True,
                "isObjectRuntimeParameter": False,
                "connectionParameterName": conn_param_name,
            },
        })
    return parameters


def _build_mtt_zip_pcxml(
    session: dict | None,
    mapping: dict,
    folder_data: dict,
    mtt_frs_guid: str,
    dtemplate_guid: str,
    agent_group_guid: str,
    conn_guid: str,
    xml_filename: str,
    conn_param_name: str = "DBConnection_OLAP",
) -> bytes:
    name = session.get("session_name", mapping["mapping_name"]) if session else mapping["mapping_name"]
    short_desc = f"PC XML task wrapper : {name}"
    if len(short_desc) > 70:
        short_desc = short_desc[:67] + "..."

    mt_task = [{
        "@type": "mtTask",
        "id": "@1",
        "name": name,
        "description": f"PowerCenter XML task wrapper for remediated XML : {name}",
        "autoExpireObject": False,
        "runtimeEnvironmentId": f"@{agent_group_guid}",
        "maxLogs": 10,
        "verbose": False,
        "mappingId": f"@{dtemplate_guid}",
        "frsGuid": mtt_frs_guid,
        "shortDescription": short_desc,
        "executionStrategy": "POWERCENTER_XML_TASK",
        "nativeCdiMapping": False,
        "remediatedPowerCenterXml": {
            "fileName": xml_filename,
            "fileRecordId": "@4",
            "usage": (
                "Use this payload as a PowerCenter XML task input, "
                "cloud-native conversion source, or IICS API deployment payload."
            ),
        },
        "sourceXml": xml_filename,
        "paramFileType": "PARAM_FILE_LOCAL",
        "parameters": _build_mtt_parameters(folder_data, conn_guid, conn_param_name),
        "inOutParameters": [],
        "connRuntimeAttrs": [],
        "sequences": [],
        "mappingSummary": {
            "transformationCount": mapping.get(
                "transformation_count", len(mapping.get("transformations", [])),
            ),
            "sourceCount": mapping.get("source_count", 0),
            "targetCount": mapping.get("target_count", 0),
        },
        "sessionPropertiesList": _build_session_properties_list(session),
        "valid": True,
        "schemaValidationErrorCount": -1,
        "hidden": False,
        "enableCrossSchemaPushdown": False,
        "enableParallelRun": False,
        "schemaMode": "async",
        "optimizationPlan": "NONE",
        "taskProperties": [
            {"@type": "taskProperty", "name": "parameterFileDir", "currentValue": "",
             "type": "STRING", "required": False},
            {"@type": "taskProperty", "name": "parameterFileName", "currentValue": "",
             "type": "STRING", "required": False},
        ],
    }]
    metadata_meta = [{"@type": "objectRef", "id": "@1", "type": "mtTask"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mtTask.json", json.dumps(mt_task, separators=(",", ":")))
        zf.writestr("metadata.meta", json.dumps(metadata_meta, separators=(",", ":")))
    return buf.getvalue()


def _build_dtemplate_zip(
    mapping: dict,
    folder_data: dict,
    guid: str,
    mapplet_guids: dict[str, str] | None = None,
) -> bytes:
    name = mapping["mapping_name"]
    bin_bytes = _build_bin(mapping, folder_data, mapplet_guids=mapplet_guids)

    references = []
    for mp_name in _collect_used_mapplet_names(mapping):
        saas = _mapplet_saas_id(mapplet_guids, mp_name)
        if not saas:
            continue
        references.append({
            "@type": "reference",
            "refObjectId": saas,
            "refType": "mappletTemplate",
            "refObjInSync": "false",
        })

    mapping_template = [{
        "@type": "mappingTemplate",
        "id": "@1", "name": name,
        "description": f"Mapping pushed from PC to ICS : {name}",
        "autoExpireObject": False,
        "bundleVersion": "0",
        "assetFrsGuid": guid,
        "templateId": "@2",
        "deployTime": int(time.time() * 1000),
        "hasParameters": True,
        "valid": True,
        "fixedConnection": False,
        "hasParametersDeployed": True,
        "fixedConnectionDeployed": False,
        "isSchemaValidationEnabled": False,
        "tasks": 1,
        "allowMaxFieldLength": False,
        "specialCharacterSupport": False,
        "references": references,
    }]
    file_record = [{
        "@type": "fileRecord",
        "id": "@2", "name": name,
        "type": "IMFOBJECT",
        "size": len(bin_bytes),
        "attachTime": int(time.time() * 1000),
        "additionalInfo": "com.informatica.metadata.template.common.Template",
    }]
    metadata_meta = [{"@type": "objectRef", "id": "@1", "type": "mappingTemplate"}]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mappingTemplate.json", json.dumps(mapping_template, separators=(",", ":")))
        zf.writestr("fileRecord.json",      json.dumps(file_record, separators=(",", ":")))
        zf.writestr("bin/@2.bin",           bin_bytes)
        zf.writestr("metadata.meta",        json.dumps(metadata_meta, separators=(",", ":")))
    return buf.getvalue()


def _build_dmapplet_bin(mapplet: dict, folder_data: dict) -> bytes:
    """Build DMAPPLET IMF from a folder-level PC MAPPLET graph."""
    graph = _enrich_graph_transformations(mapplet, folder_data)
    instances = list(graph.get("instances") or [])
    connectors = list(graph.get("connectors") or [])
    # Reuse graph builder with mapplet as the "mapping" payload.
    payload = {
        "mapping_name": graph.get("mapplet_name") or "Mapplet",
        "transformations": graph.get("transformations") or [],
        "instances": instances,
        "connectors": connectors,
    }
    return _build_bin_from_graph(
        payload,
        folder_data,
        instances,
        connectors,
        mapplet_guids=None,
        document_type="DMAPPLET",
        graph_name=graph.get("mapplet_name") or "Mapplet",
        skip_mapplet_shell=True,
    )


def _build_dmapplet_zip(mapplet: dict, folder_data: dict, guid: str) -> bytes:
    """Build a .DMAPPLET.zip asset (mappletTemplate + IMF bin)."""
    name = mapplet.get("mapplet_name") or "Mapplet"
    bin_bytes = _build_dmapplet_bin(mapplet, folder_data)
    now = int(time.time() * 1000)
    mapplet_template = [{
        "@type": "mappletTemplate",
        "id": "@1",
        "name": name,
        "description": f"Mapplet pushed from PC to ICS : {name}",
        "autoExpireObject": False,
        "documentType": "DMAPPLET",
        "valid": True,
        "validForEngines": ["CDI", "CDI_E"],
        "active": False,
        "hasFixedReferences": False,
        "assetFrsGuid": guid,
        "templateId": "@2",
        "references": [],
    }]
    file_record = [{
        "@type": "fileRecord",
        "id": "@2",
        "name": name,
        "type": "IMFOBJECT",
        "size": len(bin_bytes),
        "attachTime": now,
        "additionalInfo": "com.informatica.metadata.template.common.Template",
    }]
    metadata_meta = [{"@type": "objectRef", "id": "@1", "type": "mappletTemplate"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mappletTemplate.json", json.dumps(mapplet_template, separators=(",", ":")))
        zf.writestr("fileRecord.json", json.dumps(file_record, separators=(",", ":")))
        zf.writestr("bin/@2.bin", bin_bytes)
        zf.writestr("metadata.meta", json.dumps(metadata_meta, separators=(",", ":")))
    return buf.getvalue()


# ── MTT builder ──────────────────────────────────────────────────────────────

def _mtt_lookup_conditions_for_param(attrs: dict | None) -> list[dict[str, str]]:
    """Gold MTT lookupConditions use left/operator/right keys."""
    parsed = _parse_lookup_conditions((attrs or {}).get("Lookup condition", ""))
    return [
        {
            "left": item["leftOperand"],
            "operator": item["operator"],
            "right": item["rightOperand"],
        }
        for item in parsed
    ]


def _mtt_mapplet_prefix(sinstance: str, mapping: dict) -> str | None:
    if "." not in sinstance:
        return None
    mapplet_inst = sinstance.split(".", 1)[0]
    for inst in mapping.get("instances") or []:
        if (inst.get("instance_name") or "") == mapplet_inst:
            return inst.get("transformation_name") or mapplet_inst
    return mapplet_inst


def _mtt_param_name_from_sinstance(sinstance: str, mapping: dict) -> str:
    if "." not in sinstance:
        return f"${sinstance}$"
    prefix = _mtt_mapplet_prefix(sinstance, mapping) or sinstance.split(".", 1)[0]
    tx_name = sinstance.split(".", 1)[1]
    return f"${prefix}_{tx_name}$"


def _resolve_tx_def_for_sinstance(
    sinstance: str, mapping: dict, folder_data: dict,
) -> dict | None:
    if "." not in sinstance:
        tx_name = sinstance
        for tx in mapping.get("transformations") or []:
            if (tx.get("transformation_name") or "") == tx_name:
                return tx
        return _lookup_reusable_transformation(folder_data, tx_name)

    mapplet_inst, inner_tx = sinstance.split(".", 1)
    mapplet_def_name = _mtt_mapplet_prefix(sinstance, mapping) or mapplet_inst
    mapplet = _lookup_mapplet(folder_data, mapplet_def_name)
    if not mapplet:
        return _lookup_reusable_transformation(folder_data, inner_tx)

    for tx in mapplet.get("transformations") or []:
        if (tx.get("transformation_name") or "") == inner_tx:
            return tx
    for inst in mapplet.get("instances") or []:
        if (inst.get("instance_name") or "") == inner_tx:
            tx_name = inst.get("transformation_name") or inner_tx
            for tx in mapplet.get("transformations") or []:
                if (tx.get("transformation_name") or "") == tx_name:
                    return tx
            return _lookup_reusable_transformation(folder_data, tx_name)
    return _lookup_reusable_transformation(folder_data, inner_tx)


def _mtt_should_emit_session_param(sinstance: str, tx_type: str) -> bool:
    if "_CodeLookup." in sinstance:
        return False
    ttype = (tx_type or "").strip().lower()
    return ttype in {"lookup procedure", "sequence"}


def _mtt_should_emit_session_source_param(sinstance: str, tx_type: str) -> bool:
    """Gold SDE exports mapplet nested Source Qualifiers as MTT SOURCE params."""
    if "_CodeLookup." in sinstance:
        return False
    if (tx_type or "").strip().lower() != "source qualifier":
        return False
    return "." in sinstance


def _mtt_mapplet_source_connection_label(sinstance: str, mapping: dict) -> str:
    prefix = _mtt_mapplet_prefix(sinstance, mapping) or sinstance.split(".", 1)[0]
    return f"{prefix}_Source"


def _mtt_lookup_connection_label(sinstance: str, mapping: dict, conn_name: str) -> str:
    prefix = _mtt_mapplet_prefix(sinstance, mapping)
    if not prefix:
        return conn_name
    lookup_part = sinstance.split(".", 1)[-1]
    mapping_name = mapping.get("mapping_name") or ""
    if "CodeLookup" in lookup_part:
        return f"{prefix}_{lookup_part}LookupParameter"
    if lookup_part == "LKPTRANS":
        return f"{prefix}_LKPTRANSLookupParameter"
    # SDE mapplet flat-file / code lookups use LookupParameter suffix (gold IICS).
    if mapping_name.startswith("SDE_") and lookup_part.startswith("Lkp_"):
        return f"{prefix}_{lookup_part}LookupParameter"
    return f"{prefix}_{conn_name}"


def _is_flat_file_lookup_connection_label(conn_label: str) -> bool:
    """SDE mapplet code lookups (LookupParameter suffix) use flat-file connection."""
    return (
        conn_label.endswith("LookupParameter")
        and "_Lkp_" in conn_label
        and "LKPTRANS" not in conn_label
    )


def _collect_mapping_connection_param_names(
    mapping_name: str,
    mapping: dict,
    session: dict | None,
) -> list[str]:
    """Connection parameter names that must exist in DTEMPLATE and MTT (gold IICS)."""
    ordered: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name and name not in seen:
            seen.add(name)
            ordered.append(name)

    if mapping_name.startswith("SDE_"):
        add("Target")
    else:
        add("DBConnection_OLAP")

    if not session:
        return ordered

    for inst in session.get("transformation_instances") or []:
        sinstance = inst.get("SINSTANCENAME") or inst.get("TRANSFORMATIONNAME") or ""
        tx_type = inst.get("TRANSFORMATIONTYPE") or ""
        if not sinstance:
            continue
        if _mtt_should_emit_session_source_param(sinstance, tx_type):
            add(_mtt_mapplet_source_connection_label(sinstance, mapping))
        elif _mtt_should_emit_session_param(sinstance, tx_type):
            if (tx_type or "").strip().lower() == "sequence":
                continue
            add(_mtt_lookup_connection_label(sinstance, mapping, "DBConnection_OLAP"))
    return ordered


def _build_imf_connection_parameters(
    c: _IdCounter,
    param_names: list[str],
    *,
    flat_file_params: set[str] | None = None,
) -> tuple[dict[str, int], list[dict]]:
    flat_file_params = flat_file_params or set()
    param_ids: dict[str, int] = {}
    parameters: list[dict] = []
    for pname in param_names:
        pid = c.next()
        anon_id = c.next()
        param_ids[pname] = pid
        if pname in flat_file_params or _is_flat_file_lookup_connection_label(pname):
            type_system = "Flat File"
            connection_type = "Flat File"
        else:
            type_system = "Oracle"
            connection_type = "Oracle"
        parameters.append({
            "$$ID": pid, "$$class": 9,
            "input": "true", "output": "false",
            "precision": 0, "scale": 0,
            "allowRuntimeOverride": "true",
            "expressionVariable": "false",
            "label": "",
            "name": pname,
            "anonymousType": {
                "$$ID": anon_id, "$$class": 11,
                "name": "", "isVisible": "false",
                "subType": "", "typeSystem": type_system, "connectionType": connection_type,
            },
        })
    return param_ids, parameters


def _resolve_node_connection_param_name(
    node: dict,
    mapping_name: str,
    mapping: dict,
) -> str:
    kind = node.get("kind") or ""
    node_name = node.get("name") or ""
    if kind == "target":
        return "Target" if mapping_name.startswith("SDE_") else "DBConnection_OLAP"
    if kind == "lookup" and "." in node_name:
        return _mtt_lookup_connection_label(node_name, mapping, "DBConnection_OLAP")
    return "DBConnection_OLAP"


def _mtt_lookup_object_name(
    sinstance: str, tx_def: dict | None, param_key: str,
) -> tuple[str, str | None]:
    attrs = (tx_def or {}).get("attributes") or {}
    table = (attrs.get("Lookup table name") or "").strip()
    if table and "/" in table:
        return table, table.split("/")[-1]
    if table:
        return table, table
    dummy = f"DUMMY_{param_key.replace('$', '').replace('.', '_')}"
    return dummy, None


def _build_lookup_mtt_parameter(
    *,
    param_id: int,
    param_name: str,
    sinstance: str,
    mapping: dict,
    tx_def: dict | None,
    conn_guid: str,
    conn_name: str,
    flat_file_conn_guid: str | None = None,
) -> dict:
    conn_label = _mtt_lookup_connection_label(sinstance, mapping, conn_name)
    is_flat_file = _is_flat_file_lookup_connection_label(conn_label)
    lookup_conn_guid = (flat_file_conn_guid or conn_guid) if is_flat_file else conn_guid
    param_key = param_name.strip("$")
    lookup_object, lookup_label = _mtt_lookup_object_name(sinstance, tx_def, param_key)
    attrs = (tx_def or {}).get("attributes") or {}
    multiple_match = attrs.get("Lookup policy on multiple match") or "Use Last Value"
    ui_props: dict[str, str] = {
        "cnxtype": "CSVFile" if is_flat_file else "Oracle",
        "connectionParameterized": "true",
        "paramName": conn_label,
        "paramLabel": "",
        "paramType-mapping": "Connection",
        "logcnx": conn_label,
        "isCachedLookup": "true",
        "multipleMatchPolicy": multiple_match,
        "objectParameterized": "false",
        "visible": "false",
        "flags": "SUPPORTS_MULTI_SCHEMA",
        "originalPath": sinstance,
    }
    if lookup_label and lookup_object != f"DUMMY_{param_key.replace('.', '_')}":
        ui_props["default"] = lookup_object

    return {
        "@type": "mtTaskParameter",
        "id": param_id,
        "name": param_name,
        "type": "LOOKUP",
        "label": conn_label if _mtt_mapplet_prefix(sinstance, mapping) else conn_name,
        "description": "",
        "uiProperties": ui_props,
        "lookupConnectionId": f"@{lookup_conn_guid}",
        "lookupObject": lookup_object,
        **({"lookupObjectLabel": lookup_label} if lookup_label else {}),
        "newFlatFile": False,
        "newObject": False,
        "showBusinessNames": True,
        "naturalOrder": True,
        "truncateTarget": False,
        "bulkApiDBTarget": False,
        "customFuncCfg": {
            "@type": "customFuncConfig", "id": -1,
            "connections": [], "inputMap": [], "outputFields": [],
        },
        "targetRefsV2": {},
        "targetUpdateColumns": [],
        "fieldOrderList": [],
        "lookupConditions": _mtt_lookup_conditions_for_param(attrs),
        "runtimeAttrs": {
            "Lookup source is static": "false",
            "Case Sensitive String Comparison": "false",
            "Lookup Data Cache Size": attrs.get("Lookup Data Cache Size") or "AUTO",
            "Output Old Value On Update": _yes_no_to_bool(
                attrs.get("Output Old Value On Update"), "false",
            ),
            "Lookup Source Filter": attrs.get("Lookup Source Filter") or "",
            "Pre-build lookup cache": "AUTO",
            "Synchronize dynamic cache": _yes_no_to_bool(
                attrs.get("Synchronize Dynamic Cache"), "false",
            ),
            "Null ordering": "Null Is Highest Value",
            "Thousand Separator": attrs.get("Thousand Separator") or "None",
            "Cache File Name Prefix": attrs.get("Cache File Name Prefix") or "",
            "Lookup Index Cache Size": attrs.get("Lookup Index Cache Size") or "AUTO",
            "Optional": "true",
            "Lookup cache persistent": _yes_no_to_bool(
                attrs.get("Lookup cache persistent"), "false",
            ),
            "Update Dynamic Cache Condition": attrs.get("Update Dynamic Cache Condition") or "TRUE",
            "Decimal Separator": attrs.get("Decimal Separator") or ".",
            "Re-cache from lookup source": _yes_no_to_bool(
                attrs.get("Re-cache from lookup source"), "false",
            ),
        },
        "runtimeParameterData": {
            "@type": "mtTaskRuntimeParameterData",
            "isConnectionRuntimeParameter": True,
            "isObjectRuntimeParameter": False,
            "connectionParameterName": conn_label,
        },
    }


def _build_generator_mtt_parameter(
    *,
    param_id: int,
    param_name: str,
    sinstance: str,
    seq_guid: str,
) -> dict:
    return {
        "@type": "mtTaskParameter",
        "id": param_id,
        "name": param_name,
        "type": "GENERATOR",
        "label": param_name.strip("$"),
        "uiProperties": {
            "visible": "false",
            "originalPath": sinstance,
        },
        "newFlatFile": False,
        "newObject": False,
        "showBusinessNames": True,
        "naturalOrder": True,
        "truncateTarget": False,
        "bulkApiDBTarget": False,
        "customFuncCfg": {
            "@type": "customFuncConfig", "id": -1,
            "connections": [], "inputMap": [], "outputFields": [],
        },
        "targetRefsV2": {},
        "targetUpdateColumns": [],
        "fieldOrderList": [],
        "runtimeAttrs": {},
        "isRESTModernSource": True,
        "commandType": 0,
        "isFileList": False,
        "handleSpecialChars": False,
        "handleDecimalRoundOff": False,
        "frsAsset": False,
        "dynamicFileName": False,
        "excludeDynamicFileNameField": False,
        "currentlyProcessedFileName": False,
        "retainFieldMetadata": False,
        "useExactSrcNames": False,
        "userUpdated": True,
        "sequenceGeneratorData": {
            "@type": "sequenceGeneratorData",
            "sequenceGeneratorId": f"@{seq_guid}",
        },
        "fetchMode": "ORIGINAL",
        "tgtObjectAttributes": {},
        "runtimeParameterData": {
            "@type": "mtTaskRuntimeParameterData",
            "isConnectionRuntimeParameter": False,
            "isObjectRuntimeParameter": False,
        },
        "overridableProperties": [],
        "overriddenFields": [],
    }


def _build_mapplet_source_mtt_parameter(
    *,
    param_id: int,
    param_name: str,
    sinstance: str,
    mapping: dict,
    conn_guid: str,
    sq_query: str = "",
) -> dict:
    conn_label = _mtt_mapplet_source_connection_label(sinstance, mapping)
    tx_key = param_name.strip("$")
    src_param: dict[str, Any] = {
        "@type": "mtTaskParameter",
        "id": param_id,
        "name": param_name,
        "type": "SOURCE",
        "label": conn_label,
        "description": "",
        "uiProperties": {
            "cnxtype": "Oracle",
            "connectionParameterized": "true",
            "paramName": conn_label,
            "paramLabel": "",
            "paramType-mapping": "Connection",
            "logcnx": conn_label,
            "isSelectDistinct": "false",
            "objectParameterized": "false",
            "visible": "false",
            "flags": "SUPPORTS_MULTI_SCHEMA",
            "originalPath": sinstance,
        },
        "sourceConnectionId": f"@{conn_guid}",
        "sourceObject": f"DUMMY_{tx_key.replace('.', '_')}",
        "newFlatFile": False,
        "newObject": False,
        "showBusinessNames": True,
        "naturalOrder": True,
        "truncateTarget": False,
        "bulkApiDBTarget": False,
        "customFuncCfg": {
            "@type": "customFuncConfig", "id": -1,
            "connections": [], "inputMap": [], "outputFields": [],
        },
        "targetRefsV2": {},
        "targetUpdateColumns": [],
        "fieldOrderList": [],
        "runtimeAttrs": {},
        "isRESTModernSource": True,
        "commandType": 0,
        "isFileList": False,
        "handleSpecialChars": False,
        "handleDecimalRoundOff": False,
        "frsAsset": False,
        "dynamicFileName": False,
        "excludeDynamicFileNameField": False,
        "currentlyProcessedFileName": False,
        "retainFieldMetadata": False,
        "objectName": f"DUMMY_{tx_key.replace('.', '_')}",
        "useExactSrcNames": False,
        "userUpdated": True,
        "fetchMode": "ORIGINAL",
        "tgtObjectAttributes": {},
        "runtimeParameterData": {
            "@type": "mtTaskRuntimeParameterData",
            "isConnectionRuntimeParameter": True,
            "isObjectRuntimeParameter": False,
            "connectionParameterName": conn_label,
        },
        "overridableProperties": [],
        "overriddenFields": [],
    }
    if sq_query:
        src_param["customQuery"] = sq_query
    return src_param


def _collect_session_source_mtt_params(
    session: dict | None,
    mapping: dict,
    conn_guid: str,
) -> list[dict]:
    if not session:
        return []
    mtt_name = session.get("session_name") or mapping.get("mapping_name") or ""
    params: list[dict] = []
    for inst in session.get("transformation_instances") or []:
        sinstance = inst.get("SINSTANCENAME") or inst.get("TRANSFORMATIONNAME") or ""
        tx_type = inst.get("TRANSFORMATIONTYPE") or ""
        if not sinstance or not _mtt_should_emit_session_source_param(sinstance, tx_type):
            continue
        param_name = _mtt_param_name_from_sinstance(sinstance, mapping)
        param_id = abs(hash(f"{mtt_name}_{param_name}")) % (2 ** 31)
        sq_query = inst.get("Sql Query") or inst.get("SQL Query") or ""
        params.append(_build_mapplet_source_mtt_parameter(
            param_id=param_id,
            param_name=param_name,
            sinstance=sinstance,
            mapping=mapping,
            conn_guid=conn_guid,
            sq_query=sq_query,
        ))
    return params


def _collect_session_mtt_params(
    session: dict | None,
    mapping: dict,
    folder_data: dict,
    conn_guid: str,
    conn_name: str,
    seq_guids: dict[str, str] | None = None,
    flat_file_conn_guid: str | None = None,
) -> list[dict]:
    """LOOKUP + GENERATOR MTT params from SESSTRANSFORMATIONINST (gold IICS pattern)."""
    if not session:
        return []
    seq_guids = seq_guids or {}
    mtt_name = session.get("session_name") or mapping.get("mapping_name") or ""
    params: list[dict] = []
    for inst in session.get("transformation_instances") or []:
        sinstance = inst.get("SINSTANCENAME") or inst.get("TRANSFORMATIONNAME") or ""
        tx_type = inst.get("TRANSFORMATIONTYPE") or ""
        if not sinstance or not _mtt_should_emit_session_param(sinstance, tx_type):
            continue
        param_name = _mtt_param_name_from_sinstance(sinstance, mapping)
        param_id = abs(hash(f"{mtt_name}_{param_name}")) % (2 ** 31)
        if (tx_type or "").strip().lower() == "sequence":
            inner = sinstance.split(".", 1)[-1]
            seq_guid = seq_guids.get(inner) or seq_guids.get(sinstance) or _new_guid()
            params.append(_build_generator_mtt_parameter(
                param_id=param_id,
                param_name=param_name,
                sinstance=sinstance,
                seq_guid=seq_guid,
            ))
            continue
        tx_def = _resolve_tx_def_for_sinstance(sinstance, mapping, folder_data)
        params.append(_build_lookup_mtt_parameter(
            param_id=param_id,
            param_name=param_name,
            sinstance=sinstance,
            mapping=mapping,
            tx_def=tx_def,
            conn_guid=conn_guid,
            conn_name=conn_name,
            flat_file_conn_guid=flat_file_conn_guid,
        ))
    return params


def _sequence_reusable_name_from_sinstance(sinstance: str) -> str:
    return sinstance.split(".", 1)[-1]


def _build_sequence_generator_zip(
    seq_name: str,
    seq_guid: str,
    reusable_tx: dict | None = None,
) -> bytes:
    attrs = (reusable_tx or {}).get("attributes") or {}
    start = attrs.get("Start Value") or attrs.get("Start value") or "1"
    end = attrs.get("End Value") or attrs.get("End value") or "2147483647"
    increment = attrs.get("Increment By") or attrs.get("Increment by") or "1"
    cached = attrs.get("Number of Cached Values") or attrs.get("Cached Values") or "1000"
    sequence_gen = [{
        "@type": "sequenceGen",
        "id": "@1",
        "name": seq_name,
        "description": "Re-usable Sequence Generator pushed from PC to ICS",
        "autoExpireObject": False,
        "startValue": str(start),
        "endValue": str(end),
        "currentValue": str(start),
        "initialValue": str(start),
        "incrementBy": str(increment),
        "cachedValues": str(cached),
        "cyclic": False,
        "resetToInitial": False,
    }]
    metadata_meta = [{"@type": "objectRef", "id": "@1", "type": "sequenceGen"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("sequenceGen.json", json.dumps(sequence_gen, separators=(",", ":")))
        zf.writestr("metadata.meta", json.dumps(metadata_meta, separators=(",", ":")))
    return buf.getvalue()


def _collect_sequence_generators_for_session(
    session: dict | None,
    folder_data: dict,
) -> list[tuple[str, dict | None]]:
    """Return (reusable_seq_name, tx_def) for each GENERATOR in session insts."""
    if not session:
        return []
    found: list[tuple[str, dict | None]] = []
    seen: set[str] = set()
    for inst in session.get("transformation_instances") or []:
        sinstance = inst.get("SINSTANCENAME") or ""
        tx_type = (inst.get("TRANSFORMATIONTYPE") or "").strip().lower()
        if tx_type != "sequence":
            continue
        seq_name = _sequence_reusable_name_from_sinstance(sinstance)
        if seq_name in seen:
            continue
        seen.add(seq_name)
        tx_def = _lookup_reusable_transformation(folder_data, seq_name)
        found.append((seq_name, tx_def))
    return found

def _build_mtt_zip(
    session: dict | None,
    mtt_frs_guid: str,
    dtemplate_guid: str,
    agent_group_guid: str,
    conn_guids: dict[str, str],
    folder_data: dict,
    mapping_name: str,
    mapping: dict | None = None,
    seq_guids: dict[str, str] | None = None,
) -> bytes:
    if session is None:
        session = {"session_name": mapping_name, "mapping_name": mapping_name, "attributes": {}}
    name = session.get("session_name", mapping_name)
    attrs = session.get("attributes", {})
    mapping = mapping or {}
    instances = list(mapping.get("instances") or [])

    conn_name = "DBConnection_OLAP"
    conn_guid = (
        conn_guids.get("Orcl_BI_Jacobs_HR_PC2CDI")
        or conn_guids.get(conn_name)
        or conn_guids.get("DataWarehouse_PA")
        or conn_guids.get("Oracle_Connection")
        or conn_guids.get("DBConnection_OLAP_Oracle")
        or next(iter(conn_guids.values()), "")
    )
    target_conn_param = "Target" if mapping_name.startswith("SDE_") else conn_name
    flat_file_conn_guid = conn_guids.get(SDE_FLAT_FILE_CONNECTION)

    # Build MTT parameters from actual mapping instances (IDMC requires
    # $TransformName$ / SOURCE|TARGET|EXTENDED_SOURCE for each Source/Target tx).
    source_names: list[tuple[str, str, dict]] = []  # (param_name, object_name, columns_src)
    target_names: list[tuple[str, str]] = []

    sq_names = {
        (i.get("instance_name") or "")
        for i in instances
        if (i.get("transformation_type") or "").strip().lower() == "source qualifier"
    }

    if instances:
        for inst in instances:
            inst_name = inst.get("instance_name") or ""
            pc_type = (inst.get("transformation_type") or "").strip().lower()
            itype = (inst.get("instance_type") or "").strip().upper()
            if not inst_name:
                continue
            if itype == "SOURCE" or pc_type in _SOURCE_LIKE_TYPES:
                # Skip Source Definition when SQ exists (matches native CDI bin).
                if pc_type == "source definition" and sq_names:
                    continue
                object_name = inst.get("transformation_name") or inst_name
                if inst_name.lower().startswith("sq_") and object_name == inst_name:
                    object_name = inst_name[3:]
                src = _lookup_by_name(folder_data.get("sources", []), "source_name", object_name)
                source_names.append((inst_name, object_name, src or {}))
            elif itype == "TARGET" or pc_type in _TARGET_LIKE_TYPES:
                object_name = inst.get("transformation_name") or inst_name
                target_names.append((inst_name, object_name))
    else:
        # Legacy fallback: folder sources/targets
        for src in folder_data.get("sources", []):
            src_name = src.get("source_name") or ""
            if src_name:
                source_names.append((f"SQ_{src_name}", src_name, src))
        for tgt in folder_data.get("targets", []):
            tgt_name = tgt.get("target_name") or ""
            if tgt_name:
                target_names.append((tgt_name, tgt_name))

    parameters: list[dict] = []
    parameters.extend(_collect_session_source_mtt_params(session, mapping, conn_guid))

    for tx_name, object_name, src in source_names:
        param_id = abs(hash(f"{name}_SRC_{tx_name}")) % (2 ** 31)
        sq_query = ""
        if session:
            for inst in session.get("transformation_instances") or []:
                if (inst.get("SINSTANCENAME") or "") == tx_name:
                    sq_query = inst.get("Sql Query") or inst.get("SQL Query") or ""
                    break
        src_param: dict[str, Any] = {
            "@type": "mtTaskParameter",
            "id": param_id,
            "name": f"${tx_name}$",
            "type": "SOURCE",
            "label": conn_name,
            "description": "",
            "uiProperties": {
                "cnxtype": "Oracle",
                "connectionParameterized": "true",
                "paramName": conn_name,
                "paramLabel": "",
                "paramType-mapping": "Connection",
                "logcnx": conn_name,
                "isSelectDistinct": "false",
                "objectParameterized": "false",
                "visible": "false",
                "flags": "SUPPORTS_MULTI_SCHEMA",
                "originalPath": tx_name,
            },
            "sourceConnectionId": f"@{conn_guid}",
            "sourceObject": f"DUMMY_{tx_name}",
            "newFlatFile": False,
            "newObject": False,
            "showBusinessNames": True,
            "naturalOrder": True,
            "truncateTarget": False,
            "bulkApiDBTarget": False,
            "customFuncCfg": {
                "@type": "customFuncConfig", "id": -1,
                "connections": [], "inputMap": [], "outputFields": [],
            },
            "targetRefsV2": {},
            "targetUpdateColumns": [],
            "fieldOrderList": [],
            "runtimeAttrs": {},
            "isRESTModernSource": True,
            "commandType": 0,
            "isFileList": False,
            "handleSpecialChars": False,
            "handleDecimalRoundOff": False,
            "frsAsset": False,
            "dynamicFileName": False,
            "excludeDynamicFileNameField": False,
            "currentlyProcessedFileName": False,
            "retainFieldMetadata": False,
            "objectName": f"DUMMY_{tx_name}",
            "useExactSrcNames": False,
            "userUpdated": True,
            "fetchMode": "ORIGINAL",
            "tgtObjectAttributes": {},
            "runtimeParameterData": {
                "@type": "mtTaskRuntimeParameterData",
                "isConnectionRuntimeParameter": True,
                "isObjectRuntimeParameter": False,
                "connectionParameterName": conn_name,
            },
            "overridableProperties": [],
            "overriddenFields": [],
        }
        if sq_query:
            src_param["customQuery"] = sq_query
        parameters.append(src_param)

    for tx_name, object_name in target_names:
        param_id = abs(hash(f"{name}_TGT_{tx_name}")) % (2 ** 31)
        parameters.append({
            "@type": "mtTaskParameter",
            "id": param_id,
            "name": f"${tx_name}$",
            "type": "TARGET",
            "label": tx_name,
            "objectName": object_name,
            "objectLabel": object_name,
            "operationType": "Insert",
            "truncateTarget": False,
            "bulkApiDBTarget": True,
            "newFlatFile": False,
            "newObject": False,
            "naturalOrder": True,
            "showBusinessNames": True,
            "targetConnectionId": f"@{conn_guid}",
            "targetObject": object_name,
            "targetObjectLabel": object_name,
            "runtimeParameterData": {
                "@type": "mtTaskRuntimeParameterData",
                "isConnectionRuntimeParameter": True,
                "isObjectRuntimeParameter": False,
                "connectionParameterName": target_conn_param,
            },
            "targetRefsV2": {},
        })

    parameters.extend(_collect_session_mtt_params(
        session, mapping, folder_data, conn_guid, conn_name,
        seq_guids=seq_guids, flat_file_conn_guid=flat_file_conn_guid,
    ))

    session_props = [
        {"name": "Allow Temporary Sequence for Pushdown",
         "value": attrs.get("Allow Temporary Sequence for Pushdown", "NO"), "recommended": False},
        {"name": "Allow Temporary View for Pushdown",
         "value": attrs.get("Allow Temporary View for Pushdown", "NO"), "recommended": False},
        {"name": "Data Column Delimiter", "value": "|", "recommended": False},
        {"name": "DTM buffer size",
         "value": str(attrs.get("DTM buffer size", "24000000")), "recommended": False},
        {"name": "Error Log File Name", "value": "PMError.log", "recommended": False},
        {"name": "Pushdown Optimization",
         "value": attrs.get("Pushdown Optimization", "None"), "recommended": False},
    ]

    task_properties = [
        {"@type": "taskProperty", "name": "parameterFileDir", "currentValue": "",
         "type": "STRING", "label": "label.parameterFileDir", "required": False},
        {"@type": "taskProperty", "name": "parameterFileName", "currentValue": "",
         "type": "STRING", "label": "label.parameterFileName", "required": False},
        {"@type": "taskProperty", "name": "outboundMessageUrlQueueTime", "currentValue": "",
         "type": "NUMBER", "label": "label.outboundMessageUrlQueueTime", "required": False},
        {"@type": "taskProperty", "name": "outboundMessageUrlToken", "currentValue": "",
         "type": "STRING", "label": "label.outboundMessageUrlToken", "required": False},
    ]

    short_desc = f"Session pushed from PC to ICS : {name}"
    if len(short_desc) > 70:
        short_desc = short_desc[:67] + "..."

    mt_task = [{
        "@type": "mtTask",
        "id": "@1",
        "name": name,
        "description": f"Session pushed from PC to ICS : {name}",
        "autoExpireObject": False,
        "runtimeEnvironmentId": f"@{agent_group_guid}",
        "maxLogs": 10,
        "verbose": False,
        "mappingId": f"@{dtemplate_guid}",
        "frsGuid": mtt_frs_guid,
        "shortDescription": short_desc,
        "sessionPropertiesList": session_props,
        "hidden": False,
        "enableCrossSchemaPushdown": False,
        "enableParallelRun": False,
        "autoTunedApplied": False,
        "autoTunedAppliedType": "NONE",
        "schemaMode": "async",
        "valid": True,
        "schemaValidationErrorCount": -1,
        "serverlessProperties": {},
        "taskProperties": task_properties,
        "optimizationPlan": "NONE",
        "isMidstreamPreview": False,
        "allowMaxFieldLength": False,
        "specialCharacterSupport": True,
        "useUserDefinedOrder": False,
        "paramFileType": "PARAM_FILE_LOCAL",
        "inOutParameters": [],
        "connRuntimeAttrs": [],
        "sequences": [],
        "parameters": parameters,
    }]

    metadata_meta = [{"@type": "objectRef", "id": "@1", "type": "mtTask"}]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mtTask.json", json.dumps(mt_task, separators=(",", ":")))
        zf.writestr("metadata.meta", json.dumps(metadata_meta, separators=(",", ":")))
    return buf.getvalue()


# ── TASKFLOW XML builder (full CDI workflow — matches teammate export) ───────

_PM_VARS = [
    "PMBadFileDir", "PMCacheDir", "PMExtProcDir", "PMFailureEmailUser",
    "PMFolderName", "PMIntegrationServiceName", "PMLookupFileDir",
    "PMRepositoryServiceName", "PMRepositoryUserName", "PMRootDir",
    "PMSessionLogDir", "PMSessionRunMode", "PMSourceFileDir", "PMStorageDir",
    "PMSuccessEmailUser", "PMTargetFileDir", "PMTempDir", "PMWorkflowLogDir",
    "PMWorkflowName", "PMWorkflowRunId", "PMWorkflowRunInstanceName",
    "SYSDATE", "WORKFLOWSTARTTIME",
]

_PM_FORMULAS = {
    "PMFolderName":           "util:getAssetLocation()",
    "PMRepositoryUserName":   "util:getUserName()",
    "PMWorkflowName":         "util:getAssetName()",
    "PMWorkflowRunId":        "util:getProcessId()",
    "SYSDATE":                "fn:current-date()",
    "WORKFLOWSTARTTIME":      "util:getInstanceStartTime()",
}

_PM_TYPES = {"PMWorkflowRunId": "int", "SYSDATE": "datetime", "WORKFLOWSTARTTIME": "datetime"}


def _hyphenate(name: str) -> str:
    """Convert underscore-based task names to hyphen form for processObject."""
    return name.replace("_", "-")


def _h() -> str:
    return uuid.uuid4().hex[:8]


def _repo_handle() -> str:
    """20-char uppercase hex repoHandle matching IICS export format."""
    return (_h() + _h() + _h()[:4]).upper()


def _build_taskflow_xml(
    workflow: dict,
    mtt_frs_guid: str,
    mtt_name: str,
    tf_guid: str,
    repo_handle: str,
) -> str:
    wf_name = workflow.get("workflow_name", mtt_name)
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    mtt_hyphen = _hyphenate(mtt_name)

    tempFields_xml = ""
    for var in [mtt_name] + _PM_VARS:
        vtype = _PM_TYPES.get(var, "string")
        if var == mtt_name:
            vtype = "reference"
            opts = (
                f'<option name="failOnNotRun">false</option>'
                f'<option name="failOnFault">true</option>'
                f'<option name="referenceTo">$po:{mtt_hyphen}</option>'
                f'<option name="required">false</option>'
                f'<option name="isCopy">true</option>'
            )
        else:
            formula = _PM_FORMULAS.get(var)
            if formula:
                opts = f'<option name="required">false</option><option name="initialvalue">{formula}</option>'
            else:
                opts = f'<option name="required">false</option><option name="initialvalue"/>'
        tempFields_xml += f'\n               <field description="" name="{var}" type="{vtype}"><options>{opts}</options></field>'

    assign_ops = ""
    for var in _PM_VARS:
        formula = _PM_FORMULAS.get(var)
        if formula:
            assign_ops += f'\n                  <operation source="formula" to="temp.{var}"><expression language="XQuery">{formula}</expression></operation>'
        else:
            assign_ops += f'\n                  <operation source="constant" to="temp.{var}"/>'

    sid_cont = _h()
    sid_svc  = _h()
    sid_link = _h()
    sid_cerr = _h()
    sid_cwrn = _h()

    service_xml = f"""
               <eventContainer id="{sid_cont}">
                  <service id="{sid_svc}">
                     <title>{mtt_name}</title>
                     <serviceName>ICSExecuteDataTask</serviceName>
                     <serviceGUID/>
                     <serviceInput>
                        <parameter name="Task Name" source="constant" updatable="true">{mtt_name}</parameter>
                        <parameter name="Wait for Task to Complete" source="constant" updatable="true">true</parameter>
                        <parameter name="Max Wait" source="constant" updatable="true">86400</parameter>
                        <parameter name="GUID" source="constant" updatable="true">{mtt_frs_guid}</parameter>
                        <parameter name="Has Inout Parameters" source="constant" updatable="true">false</parameter>
                        <parameter name="Task Type" source="constant" updatable="true">MCT</parameter>
                        <parameter name="taskField" source="nested">
                           <operation source="field" to="{mtt_hyphen}">temp.{mtt_name}</operation>
                           <operation source="field" to="{mtt_hyphen}/taskProperties[1]/parameterFileDir">input.InputMappingTaskParameterFileDir</operation>
                           <operation source="field" to="temp.{mtt_name}[1]/taskProperties[1]/parameterFileDir">input.InputMappingTaskParameterFileDir</operation>
                           <operation source="field" to="{mtt_hyphen}/taskProperties[1]/parameterFileName">input.InputMappingTaskParameterFileName</operation>
                           <operation source="field" to="temp.{mtt_name}[1]/taskProperties[1]/parameterFileName">input.InputMappingTaskParameterFileName</operation>
                        </parameter>
                     </serviceInput>
                     <serviceOutput>
                        <operation source="field" to="temp.{mtt_name}/output/Run_Id">Run Id</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Start_Time">Start Time</operation>
                        <operation source="field" to="temp.{mtt_name}/output/End_Time">End Time</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Object_Name">Object Name</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Log_Id">Log Id</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Task_Id">Task Id</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Task_Status">Task Status</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Success_Source_Rows">Success Source Rows</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Failed_Source_Rows">Failed Source Rows</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Success_Target_Rows">Success Target Rows</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Failed_Target_Rows">Failed Target Rows</operation>
                        <operation source="field" to="temp.{mtt_name}/output/Error_Message">Error Message</operation>
                        <operation source="field" to="temp.{mtt_name}/output/TotalTransErrors">Total Transformation Errors</operation>
                        <operation source="field" to="temp.{mtt_name}/output/FirstErrorCode">First Error Code</operation>
                     </serviceOutput>
                  </service>
                  <link id="{sid_link}" targetId="end_node"/>
                  <events>
                     <catch faultField="temp.{mtt_name}/fault" id="{sid_cerr}" interrupting="true" name="error"/>
                     <catch faultField="temp.{mtt_name}/fault" id="{sid_cwrn}" interrupting="true" name="warning"/>
                  </events>
               </eventContainer>"""

    start_link = _h()
    asgn1_id   = _h()
    asgn2_link = _h()
    asgn2_id   = _h()
    asgn3_link = _h()

    xml = f"""<aetgt:getResponse xmlns:aetgt="http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd"
                   xmlns:types1="http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd">
   <types1:Item>
      <types1:EntryId>{repo_handle}</types1:EntryId>
      <types1:Name>{wf_name}</types1:Name>
      <types1:MimeType>application/xml+taskflow</types1:MimeType>
      <types1:Description>These workflows are created from the Workflow Generation Wizard.</types1:Description>
      <types1:AppliesTo/>
      <types1:Tags/>
      <types1:VersionLabel>1.0</types1:VersionLabel>
      <types1:State>CURRENT</types1:State>
      <types1:ProcessGroup/>
      <types1:CreatedBy>PC2IICS-Migration</types1:CreatedBy>
      <types1:CreationDate>{now_iso}</types1:CreationDate>
      <types1:ModifiedBy/>
      <types1:PublicationStatus>unpublished</types1:PublicationStatus>
      <types1:Entry>
         <taskflow xmlns="http://schemas.active-endpoints.com/appmodules/screenflow/2010/10/avosScreenflow.xsd"
                   xmlns:tfm="http://schemas.active-endpoints.com/appmodules/screenflow/2021/04/taskflowModel.xsd"
                   xmlns:list="urn:activevos:spi:list:functions"
                   xmlns:ns2="http://informatica.com/HumanTask/2022/12/schema/model/humanTaskCommon.xsd"
                   GUID="{tf_guid}"
                   displayName="{wf_name}"
                   name="{wf_name}"
                   overrideAPIName="false">
            <appliesTo/>
            <description>These workflows are created from the Workflow Generation Wizard.</description>
            <tags/>
            <generator>PC2Cloud Workflow Converter v1</generator>
            <input>
               <parameter name="InputMappingTaskParameterFileDir" type="string">
                  <options><option name="required">false</option></options>
               </parameter>
               <parameter name="InputMappingTaskParameterFileName" type="string">
                  <options><option name="required">false</option></options>
               </parameter>
            </input>
            <tempFields>{tempFields_xml}
            </tempFields>
            <notes/>
            <deployment suspendOnFault="false" tracingLevel="verbose">
               <rest>
                  <allowedGroups><group>CDI_TFlow_API_group</group></allowedGroups>
               </rest>
            </deployment>
            <flow id="a">
               <start id="b">
                  <title>Start</title>
                  <link id="{start_link}" targetId="{asgn1_id}"/>
               </start>
               <assignment id="{asgn1_id}">
                  <title>Assignment_PC_Variables</title>
                  {assign_ops}
                  <link id="{asgn2_link}" targetId="{asgn2_id}"/>
               </assignment>
               <assignment id="{asgn2_id}">
                  <title>Assignment_PC_Workflow_Parameter_File</title>
                  <operation source="formula" to="input.InputMappingTaskParameterFileDir">
                     <expression language="XQuery">if (fn:empty($input.InputMappingTaskParameterFileDir)) then '' else $input.InputMappingTaskParameterFileDir</expression>
                  </operation>
                  <operation source="formula" to="input.InputMappingTaskParameterFileName">
                     <expression language="XQuery">if (fn:empty($input.InputMappingTaskParameterFileName)) then '' else $input.InputMappingTaskParameterFileName</expression>
                  </operation>
                  <link id="{asgn3_link}" targetId="{sid_cont}"/>
               </assignment>
               {service_xml}
               <end id="end_node"/>
            </flow>
            <dependencies>
               <processObject xmlns="http://schemas.active-endpoints.com/appmodules/screenflow/2011/06/avosHostEnvironment.xsd"
                              xmlns:processObject="http://schemas.active-endpoints.com/appmodules/screenflow/2011/06/avosHostEnvironment.xsd"
                              displayName="{mtt_hyphen}"
                              isByCopy="true"
                              name="{mtt_hyphen}">
                  <description/>
                  <tags/>
                  <detail>
                     <field label="Input Parameters"           name="input"          type="reference"/>
                     <field label="InOut Parameters"           name="inout"          type="reference"/>
                     <field label="TaskProperties Parameters"  name="taskProperties" type="reference"/>
                     <field label="Output Parameters"          name="output"         type="reference"/>
                     <field label="Fault"                      name="fault"          type="reference"/>
                  </detail>
               </processObject>
            </dependencies>
         </taskflow>
      </types1:Entry>
      <types1:GUID>{tf_guid}</types1:GUID>
      <types1:DisplayName>{wf_name}</types1:DisplayName>
   </types1:Item>
   <types1:CurrentServerDateTime>{now_iso}</types1:CurrentServerDateTime>
</aetgt:getResponse>"""
    return xml.replace("\n", "\r\n")


# ── Connection builder ───────────────────────────────────────────────────────

def _build_workflow_taskflow_xml(
    workflow: dict,
    tasks: list[tuple[str, str]],
    tf_guid: str,
    repo_handle: str,
) -> str:
    if len(tasks) == 1:
        mtt_name, mtt_frs_guid = tasks[0]
        return _build_taskflow_xml(workflow, mtt_frs_guid, mtt_name, tf_guid, repo_handle)

    wf_name = workflow.get("workflow_name") or tasks[0][0]
    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    temp_fields = ""
    for mtt_name, _ in tasks:
        mtt_hyphen = _hyphenate(mtt_name)
        temp_fields += (
            f'\n               <field description="" name="{mtt_name}" type="reference"><options>'
            f'<option name="failOnNotRun">false</option>'
            f'<option name="failOnFault">true</option>'
            f'<option name="referenceTo">$po:{mtt_hyphen}</option>'
            f'<option name="required">false</option>'
            f'<option name="isCopy">true</option>'
            f'</options></field>'
        )
    for var in _PM_VARS:
        vtype = _PM_TYPES.get(var, "string")
        formula = _PM_FORMULAS.get(var)
        if formula:
            opts = f'<option name="required">false</option><option name="initialvalue">{formula}</option>'
        else:
            opts = f'<option name="required">false</option><option name="initialvalue"/>'
        temp_fields += f'\n               <field description="" name="{var}" type="{vtype}"><options>{opts}</options></field>'

    assign_ops = ""
    for var in _PM_VARS:
        formula = _PM_FORMULAS.get(var)
        if formula:
            assign_ops += (
                f'\n                  <operation source="formula" to="temp.{var}">'
                f'<expression language="XQuery">{formula}</expression></operation>'
            )
        else:
            assign_ops += f'\n                  <operation source="constant" to="temp.{var}"/>'

    dependencies = ""
    branch_xml = ""
    for mtt_name, mtt_frs_guid in tasks:
        mtt_hyphen = _hyphenate(mtt_name)
        sid_cont = _h()
        sid_svc = _h()
        sid_link = _h()
        sid_cerr = _h()
        sid_cwrn = _h()
        exclusive_id = _h()
        branch_xml += f"""
                     <container id="{exclusive_id}" type="exclusive">
                        <eventContainer id="{sid_cont}">
                           <service id="{sid_svc}">
                              <title>{mtt_name}</title>
                              <serviceName>ICSExecuteDataTask</serviceName>
                              <serviceGUID/>
                              <serviceInput>
                                 <parameter name="Task Name" source="constant" updatable="true">{mtt_name}</parameter>
                                 <parameter name="Wait for Task to Complete" source="constant" updatable="true">true</parameter>
                                 <parameter name="Max Wait" source="constant" updatable="true">86400</parameter>
                                 <parameter name="GUID" source="constant" updatable="true">{mtt_frs_guid}</parameter>
                                 <parameter name="Has Inout Parameters" source="constant" updatable="true">false</parameter>
                                 <parameter name="Task Type" source="constant" updatable="true">MCT</parameter>
                                 <parameter name="taskField" source="nested">
                                    <operation source="field" to="{mtt_hyphen}">temp.{mtt_name}</operation>
                                    <operation source="field" to="{mtt_hyphen}/taskProperties[1]/parameterFileDir">input.InputMappingTaskParameterFileDir</operation>
                                    <operation source="field" to="temp.{mtt_name}[1]/taskProperties[1]/parameterFileDir">input.InputMappingTaskParameterFileDir</operation>
                                    <operation source="field" to="{mtt_hyphen}/taskProperties[1]/parameterFileName">input.InputMappingTaskParameterFileName</operation>
                                    <operation source="field" to="temp.{mtt_name}[1]/taskProperties[1]/parameterFileName">input.InputMappingTaskParameterFileName</operation>
                                 </parameter>
                              </serviceInput>
                              <serviceOutput>
                                 <operation source="field" to="temp.{mtt_name}/output/Run_Id">Run Id</operation>
                                 <operation source="field" to="temp.{mtt_name}/output/Start_Time">Start Time</operation>
                                 <operation source="field" to="temp.{mtt_name}/output/End_Time">End Time</operation>
                                 <operation source="field" to="temp.{mtt_name}/output/Object_Name">Object Name</operation>
                                 <operation source="field" to="temp.{mtt_name}/output/Log_Id">Log Id</operation>
                                 <operation source="field" to="temp.{mtt_name}/output/Task_Id">Task Id</operation>
                                 <operation source="field" to="temp.{mtt_name}/output/Task_Status">Task Status</operation>
                              </serviceOutput>
                           </service>
                           <link id="{sid_link}" targetId="end_node"/>
                           <events>
                              <catch faultField="temp.{mtt_name}/fault" id="{sid_cerr}" interrupting="true" name="error"/>
                              <catch faultField="temp.{mtt_name}/fault" id="{sid_cwrn}" interrupting="true" name="warning"/>
                           </events>
                        </eventContainer>
                     </container>"""
        dependencies += f"""
               <processObject xmlns="http://schemas.active-endpoints.com/appmodules/screenflow/2011/06/avosHostEnvironment.xsd"
                              xmlns:processObject="http://schemas.active-endpoints.com/appmodules/screenflow/2011/06/avosHostEnvironment.xsd"
                              displayName="{mtt_hyphen}"
                              isByCopy="true"
                              name="{mtt_hyphen}">
                  <description/>
                  <tags/>
                  <detail>
                     <field label="Input Parameters"           name="input"          type="reference"/>
                     <field label="InOut Parameters"           name="inout"          type="reference"/>
                     <field label="TaskProperties Parameters"  name="taskProperties" type="reference"/>
                     <field label="Output Parameters"          name="output"         type="reference"/>
                     <field label="Fault"                      name="fault"          type="reference"/>
                  </detail>
               </processObject>"""

    start_link = _h()
    asgn1_id = _h()
    asgn2_link = _h()
    asgn2_id = _h()
    asgn3_link = _h()
    parallel_id = _h()
    xml = f"""<aetgt:getResponse xmlns:aetgt="http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd"
                   xmlns:types1="http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd">
   <types1:Item>
      <types1:EntryId>{repo_handle}</types1:EntryId>
      <types1:Name>{wf_name}</types1:Name>
      <types1:MimeType>application/xml+taskflow</types1:MimeType>
      <types1:Description>These workflows are created from the Workflow Generation Wizard.</types1:Description>
      <types1:VersionLabel>1.0</types1:VersionLabel>
      <types1:State>CURRENT</types1:State>
      <types1:CreatedBy>PC2IICS-Migration</types1:CreatedBy>
      <types1:CreationDate>{now_iso}</types1:CreationDate>
      <types1:PublicationStatus>unpublished</types1:PublicationStatus>
      <types1:Entry>
         <taskflow xmlns="http://schemas.active-endpoints.com/appmodules/screenflow/2010/10/avosScreenflow.xsd"
                   GUID="{tf_guid}"
                   displayName="{wf_name}"
                   name="{wf_name}"
                   overrideAPIName="false">
            <input>
               <parameter name="InputMappingTaskParameterFileDir" type="string">
                  <options><option name="required">false</option></options>
               </parameter>
               <parameter name="InputMappingTaskParameterFileName" type="string">
                  <options><option name="required">false</option></options>
               </parameter>
            </input>
            <tempFields>{temp_fields}
            </tempFields>
            <flow id="a">
               <start id="b">
                  <title>Start</title>
                  <link id="{start_link}" targetId="{asgn1_id}"/>
               </start>
               <assignment id="{asgn1_id}">
                  <title>Assignment_PC_Variables</title>{assign_ops}
                  <link id="{asgn2_link}" targetId="{asgn2_id}"/>
               </assignment>
               <assignment id="{asgn2_id}">
                  <title>Assignment_PC_Workflow_Parameter_File</title>
                  <operation source="formula" to="input.InputMappingTaskParameterFileDir">
                     <expression language="XQuery">if (fn:empty($input.InputMappingTaskParameterFileDir)) then '' else $input.InputMappingTaskParameterFileDir</expression>
                  </operation>
                  <operation source="formula" to="input.InputMappingTaskParameterFileName">
                     <expression language="XQuery">if (fn:empty($input.InputMappingTaskParameterFileName)) then '' else $input.InputMappingTaskParameterFileName</expression>
                  </operation>
                  <link id="{asgn3_link}" targetId="{parallel_id}"/>
               </assignment>
               <container id="{parallel_id}" type="parallel">
{branch_xml}
               </container>
               <end id="end_node"/>
            </flow>
            <dependencies>{dependencies}
            </dependencies>
         </taskflow>
      </types1:Entry>
      <types1:GUID>{tf_guid}</types1:GUID>
      <types1:DisplayName>{wf_name}</types1:DisplayName>
   </types1:Item>
   <types1:CurrentServerDateTime>{now_iso}</types1:CurrentServerDateTime>
</aetgt:getResponse>"""
    return xml.replace("\n", "\r\n")


def _combined_workflow_name(mtt_names: list[str]) -> str:
    if not mtt_names:
        return "Combined_Workflow"
    if all("JobDimension" in name for name in mtt_names):
        return "JobDimension"
    common = mtt_names[0].rsplit("_", 1)[0]
    if all(name.startswith(common) for name in mtt_names):
        return common
    return "Combined_Workflow"


def _interleave_dtemplate_mtt(
    dtemplate_objects: list[dict],
    mtt_objects: list[dict],
) -> list[dict]:
    mtt_by_name = {obj["objectName"]: obj for obj in mtt_objects}
    ordered: list[dict] = []
    seen_mtt: set[str] = set()
    for dt in dtemplate_objects:
        ordered.append(dt)
        mtt = mtt_by_name.get(dt["objectName"])
        if mtt:
            ordered.append(mtt)
            seen_mtt.add(mtt["objectName"])
    for mtt in mtt_objects:
        if mtt["objectName"] not in seen_mtt:
            ordered.append(mtt)
    return ordered


def _build_connection_zip(
    conn_name: str, conn_guid: str,
    agent_group_guid: str, org_id: str, agent_id: str,
) -> bytes:
    conn_json = [{
        "@type": "connection",
        "id": "@1",
        "name": conn_name,
        "runtimeEnvironmentId": f"@{agent_group_guid}",
        "instanceDisplayName": "Oracle",
        "host": "default-host",
        "database": "orcl",
        "codepage": "UTF-8",
        "adjustedJdbcHostName": "default-host",
        "type": "Oracle",
        "baseType": "Oracle",
        "port": 1521,
        "password": "********",
        "username": "default-username",
        "majorUpdateTime": "2025-12-11T00:51:01.000Z",
        "timeout": 60,
        "connParams": {
            "agentId": agent_id,
            "oracleSubType": "oracleonpremise",
            "agentGroupId": agent_group_guid,
            "orgId": "010CW7",
        },
        "internal": False,
        "federatedId": conn_guid,
        "retryNetworkError": False,
        "supportsCCIMultiGroup": False,
        "metadataBrowsable": True,
        "supportLabels": False,
        "vaultEnabled": False,
        "vaultEnabledParams": [],
        "isRtAttrsRefreshRequired": False,
        "connectorStatus": "ACTIVE",
    }]
    meta = [{"@type": "objectRef", "id": "@1", "type": "connection"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("connection.json", json.dumps(conn_json, separators=(",", ":")))
        zf.writestr("metadata.meta",   json.dumps(meta, separators=(",", ":")))
    return buf.getvalue()


def _build_agent_group_zip(group_name: str, group_guid: str) -> bytes:
    ag_json = [{
        "@type": "runtimeEnvironment",
        "id": "@1",
        "name": group_name,
        "isSystemAgentGroup": False,
        "isShared": False,
        "federatedId": group_guid,
        "createTimeUTC": "2025-09-09T11:52:30.000Z",
        "updateTimeUTC": "2025-09-09T11:53:44.000Z",
    }]
    meta = [{"@type": "objectRef", "id": "@1", "type": "runtimeEnvironment"}]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("runtimeEnvironment.json", json.dumps(ag_json, separators=(",", ":")))
        zf.writestr("metadata.meta",   json.dumps(meta, separators=(",", ":")))
    return buf.getvalue()


# ── Project / Folder builders ────────────────────────────────────────────────

def _odata_property(name: str, value: Any) -> dict[str, Any]:
    return {
        "annotations": [],
        "valueType": "PRIMITIVE",
        "value": value,
        "type": None,
        "name": name,
        "operations": [],
        "null": value is None,
        "primitive": value is not None,
        "enum": False,
        "collection": False,
        "geospatial": False,
        "complex": False,
    }


def _parent_info(parent_id: str, parent_name: str, parent_type: str) -> dict[str, Any]:
    return {
        "annotations": [],
        "baseURI": None,
        "id": None,
        "title": None,
        "associationLinks": [],
        "navigationLinks": [],
        "value": [
            _odata_property("parentId", parent_id),
            _odata_property("parentName", parent_name),
            _odata_property("parentType", parent_type),
        ],
        "typeName": None,
        "navigationBindings": [],
    }


def _build_folder_json(
    folder_name: str,
    folder_guid: str,
    project_name: str | None = None,
    project_guid: str | None = None,
) -> str:
    obj = {
        "annotations": [], "baseURI": None,
        "id": f"Folders({folder_guid})",
        "title": None, "associationLinks": [], "navigationLinks": [],
        "type": "OData.frs.Folder", "editLink": None,
        "mediaEditLinks": [], "operations": [],
        "properties": [
            _odata_property("id", folder_guid),
            _odata_property("name", folder_name),
            _odata_property("description", ""),
            _odata_property("owner", "eviB4AQL3UHcL6imixfmoN"),
            _odata_property("createdBy", "eviB4AQL3UHcL6imixfmoN"),
            _odata_property("lastUpdatedBy", "eviB4AQL3UHcL6imixfmoN"),
            _odata_property("lastAccessedBy", "eviB4AQL3UHcL6imixfmoN"),
            _odata_property("createdTime", "2026-07-08T03:02:15.000Z"),
            _odata_property("lastUpdatedTime", "2026-07-08T03:02:15.000Z"),
            _odata_property("lastAccessedTime", "2026-07-08T03:02:15.000Z"),
            _odata_property("expiresBy", "2038-01-18T00:00:00.000Z"),
            _odata_property("documentType", "Folder"),
            _odata_property("contentType", "Binary"),
            _odata_property("documentState", "COMPLETE"),
            _odata_property("aclRule", "org"),
            _odata_property("subcontainerCount", 0),
            _odata_property("customAttributes", None),
            _odata_property("repoInfo", None),
            _odata_property(
                "parentInfo",
                [
                    _parent_info("7cCn5thwWFLhiZoSosphKL", "REG", "Space"),
                    _parent_info(project_guid or "", project_name or "", "Project"),
                ],
            ),
        ],
        "mediaContentSource": None, "mediaContentType": None,
    }
    return json.dumps(obj)


def _build_project_json(project_name: str, project_guid: str) -> str:
    obj = {
        "annotations": [], "baseURI": None,
        "id": f"Projects({project_guid})",
        "title": None, "associationLinks": [], "navigationLinks": [],
        "type": "OData.frs.Project", "editLink": None,
        "mediaEditLinks": [], "operations": [],
        "properties": [
            _odata_property("id", project_guid),
            _odata_property("name", project_name),
            _odata_property("description", "Migrated project"),
            _odata_property("owner", "8xG29b4cYgGidbFjQDSFad"),
            _odata_property("createdBy", "8xG29b4cYgGidbFjQDSFad"),
            _odata_property("lastUpdatedBy", "8xG29b4cYgGidbFjQDSFad"),
            _odata_property("lastAccessedBy", "3ZkD2hs22mSjfAAUpb2i4U"),
            _odata_property("createdTime", "2025-12-05T11:57:41.000Z"),
            _odata_property("lastUpdatedTime", "2025-12-05T11:57:41.000Z"),
            _odata_property("lastAccessedTime", "2026-07-08T14:46:58.000Z"),
            _odata_property("expiresBy", "2038-01-18T00:00:00.000Z"),
            _odata_property("documentType", "Project"),
            _odata_property("contentType", "Binary"),
            _odata_property("documentState", "COMPLETE"),
            _odata_property("aclRule", "org"),
            _odata_property("subcontainerCount", 21),
            _odata_property("customAttributes", None),
            _odata_property("repoInfo", None),
            _odata_property("parentInfo", [_parent_info("7cCn5thwWFLhiZoSosphKL", "REG", "Space")]),
        ],
        "mediaContentSource": None, "mediaContentType": None,
    }
    return json.dumps(obj)


# ── Metadata helpers ─────────────────────────────────────────────────────────

_CONTEXT_ATTR = [{"name": "id", "value": "@1"}]

def _meta_with_ctx(
    repo_handle: str | None,
    object_refs: list[str],
    description: str | None,
    content_type: str,
    doc_state: str,
    context_attrs,  # list | None | []
    model_version: dict | None = None,
) -> dict:
    return {
        "modelVersion": model_version or {"major": 0, "minor": 0},
        "repoInfo": {"repoHandle": repo_handle} if repo_handle else None,
        "objectRefs": object_refs,
        "contextAttributes": context_attrs,
        "additionalInfo": {
            "description": description,
            "contentType": content_type,
            "documentState": doc_state,
        },
    }


# ── GUID helpers ─────────────────────────────────────────────────────────────

def _new_guid() -> str:
    import base64
    raw = uuid.uuid4().bytes
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")[:22]


def _sha256_bytes(data: bytes) -> str:
    return sha256_hex(data)


# ── Client reference-shell (single-session gold exports) ─────────────────────

SINGLE_SESSION_REFERENCE_SHELLS: dict[str, dict[str, Any]] = {
    "SDE_ORA_JobDimension": {
        "reference_zip_names": [
            "SDE_ORA_EmployeeDimension-1784818706860.zip",
        ],
        "skip_dmapplets": {"MPLT_EMPLOYEE_INS_REJ"},
        "dmapplet_name_map": {
            "mplt_SA_ORA_EmployeeDimension": "mplt_SA_ORA_JobDimension",
            "mplt_BC_ORA_EmployeeDimension": "mplt_BC_ORA_JobDimension",
        },
        "text_replacements": [
            ("mplt_BC_ORA_EmployeeDimension_Sq_Employees", "mplt_BC_ORA_JobDimension_Sq_Jobs"),
            ("mplt_BC_ORA_EmployeeDimension", "mplt_BC_ORA_JobDimension"),
            ("mplt_SA_ORA_EmployeeDimension", "mplt_SA_ORA_JobDimension"),
            ("mplt_Employee_Ins_Rej_Lkp_W_EMPLOYEE_DS", "mplt_Employee_Ins_Rej_Lkp_W_JOB_DS"),
            ("W_EMPLOYEE_DS", "W_JOB_DS"),
            ("Sq_Employees", "Sq_Jobs"),
        ],
        "native_graph_mapplets": True,
        "native_graph_dtemplate": True,
    },
    "SIL_JobDimension": {
        "reference_zip_names": [
            "SIL_EmployeeDimension-1784818567598.zip",
        ],
        "skip_dmapplets": set(),
        "dmapplet_name_map": {
            "mplt_SIL_EmployeeDimension_CodeLookup": "mplt_SIL_JobDimension_CodeLookup",
            "mplt_SIL_EmployeeDimension": "mplt_SIL_JobDimension",
            "MPLT_GET_ETL_PROC_WID": "MPLT_GET_ETL_PROC_WID",
        },
        "text_replacements": [
            ("mplt_SIL_EmployeeDimension_CodeLookup", "mplt_SIL_JobDimension_CodeLookup"),
            ("Exp_W_Employee_D_Defaults", "Exp_W_JOB_D_Defaults"),
            ("Exp_W_EMPLOYEE_D_Transform", "Exp_W_JOB_D_Transform"),
            ("Exp_W_EMPLOYEE_D_Validate", "Exp_W_JOB_D_Validate"),
            ("W_Employee_D_Defaults", "W_JOB_D_Defaults"),
            ("W_EMPLOYEE_D_Transform", "W_JOB_D_Transform"),
            ("W_EMPLOYEE_D_Validate", "W_JOB_D_Validate"),
            ("Seq_W_EMPLOYEE_D_Wid", "Seq_W_JOB_D_Wid"),
            ("W_EMPLOYEE_D_Wid", "W_JOB_D_Wid"),
            ("W_EMPLOYEE_DS", "W_JOB_DS"),
            ("W_EMPLOYEE_D", "W_JOB_D"),
            ("mplt_SIL_EmployeeDimension", "mplt_SIL_JobDimension"),
            ("SIL_EmployeeDimension", "SIL_JobDimension"),
        ],
        "native_graph_mapplets": False,
        "native_graph_dtemplate": True,
    },
}


def _shell_text_replacement_dict(shell_config: dict[str, Any] | None) -> dict[str, str]:
    if not shell_config:
        return {}
    return {old: new for old, new in shell_config.get("text_replacements") or []}


def _resolve_reference_shell_path(
    shell_cfg: dict[str, Any],
    project_root: Path,
) -> Path | None:
    """Resolve client reference zip from Downloads or repo reference_packages."""
    names = shell_cfg.get("reference_zip_names") or []
    search_dirs = [
        Path(r"d:\Downloads"),
        project_root / "reference_packages" / "iics_success" / "single_session",
    ]
    for name in names:
        for base in search_dirs:
            candidate = base / name
            if candidate.exists():
                return candidate
    return None


PRIMARY_REFERENCE_CONNECTION = "Orcl_BI_Jacobs_HR_PC2CDI"
PRIMARY_REFERENCE_AGENT_GROUP = "PC Secure Agent Group"
SDE_FLAT_FILE_CONNECTION = "default-connection-name_Flat_File_PC2CDI"


def _ordered_replacement_items(replacements: dict[str, str]) -> list[tuple[str, str]]:
    """Apply longest keys first so partial substring replacements do not corrupt GUIDs."""
    return sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True)


def _patch_manifest_object_refs(
    obj: dict,
    *,
    agent_group_guid: str,
    dropped_agent_guids: set[str],
    remapped_connection_guids: dict[str, str],
) -> dict:
    patched = dict(obj)
    meta = dict(patched.get("metadata") or {})
    refs = list(meta.get("objectRefs") or [])
    new_refs: list[str] = []
    for ref in refs:
        if ref in dropped_agent_guids:
            new_refs.append(agent_group_guid)
        elif ref in remapped_connection_guids:
            new_refs.append(remapped_connection_guids[ref])
        else:
            new_refs.append(ref)
    meta["objectRefs"] = new_refs
    patched["metadata"] = meta
    return patched


def _rewrite_sys_entries_agent_refs(
    sys_entries: dict[str, bytes],
    *,
    target_agent_guid: str,
    dropped_agent_guids: set[str],
) -> dict[str, bytes]:
    if not dropped_agent_guids:
        return sys_entries
    rewritten: dict[str, bytes] = {}
    for path, raw in sys_entries.items():
        if not path.endswith(".Connection.zip"):
            rewritten[path] = raw
            continue
        with zipfile.ZipFile(io.BytesIO(raw)) as zin:
            members = {name: zin.read(name) for name in zin.namelist()}
        for name, data in list(members.items()):
            if not name.endswith(".json"):
                continue
            text = data.decode("utf-8")
            for old_guid in dropped_agent_guids:
                text = text.replace(f"@{old_guid}", f"@{target_agent_guid}")
            members[name] = text.encode("utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for member, payload in members.items():
                zout.writestr(member, payload)
        rewritten[path] = buf.getvalue()
    return rewritten


def _slim_reference_shell(shell: dict[str, Any], mapping_name: str) -> dict[str, Any]:
    """Keep only runtime SYS deps importers need (matches successful JEG single-session pattern)."""
    keep_connections = {PRIMARY_REFERENCE_CONNECTION}
    if mapping_name.startswith("SDE_"):
        keep_connections.add(SDE_FLAT_FILE_CONNECTION)
    keep_agents = {PRIMARY_REFERENCE_AGENT_GROUP}

    slim_sys: dict[str, bytes] = {}
    for path, data in shell.get("sys_entries", {}).items():
        base = Path(path).name
        if base.endswith(".Connection.zip"):
            conn_name = base[: -len(".Connection.zip")]
            if conn_name in keep_connections:
                slim_sys[path] = data
        elif base.endswith(".AgentGroup.zip"):
            agent_name = base[: -len(".AgentGroup.zip")]
            if agent_name in keep_agents:
                slim_sys[path] = data

    slim_objects: list[dict] = []
    remapped_connection_guids: dict[str, str] = {}
    dropped_agent_guids: set[str] = set()
    primary_guid = ""
    for obj in shell.get("exported_objects") or []:
        if obj.get("objectType") == "Connection" and obj.get("objectName") == PRIMARY_REFERENCE_CONNECTION:
            primary_guid = obj["objectGuid"]
            break

    for obj in shell.get("exported_objects") or []:
        otype = obj.get("objectType") or ""
        oname = obj.get("objectName") or ""
        if otype == "Connection":
            if oname not in keep_connections:
                if primary_guid:
                    remapped_connection_guids[obj["objectGuid"]] = primary_guid
                continue
        if otype == "AgentGroup":
            if oname not in keep_agents:
                dropped_agent_guids.add(obj["objectGuid"])
                continue
        slim_objects.append(obj)

    agent_group_guid = by_name[PRIMARY_REFERENCE_AGENT_GROUP]["objectGuid"] if (by_name := {obj["objectName"]: obj for obj in slim_objects}) else ""
    if agent_group_guid:
        slim_objects = [
            _patch_manifest_object_refs(
                obj,
                agent_group_guid=agent_group_guid,
                dropped_agent_guids=dropped_agent_guids,
                remapped_connection_guids=remapped_connection_guids,
            )
            if obj.get("metadata")
            else obj
            for obj in slim_objects
        ]
        slim_sys = _rewrite_sys_entries_agent_refs(
            slim_sys,
            target_agent_guid=agent_group_guid,
            dropped_agent_guids=dropped_agent_guids,
        )

    by_name = {obj["objectName"]: obj for obj in slim_objects}
    return {
        **shell,
        "sys_entries": slim_sys,
        "exported_objects": slim_objects,
        "remapped_connection_guids": remapped_connection_guids,
        "dropped_agent_guids": dropped_agent_guids,
        "primary_conn_guid": by_name[PRIMARY_REFERENCE_CONNECTION]["objectGuid"],
        "agent_group_guid": by_name[PRIMARY_REFERENCE_AGENT_GROUP]["objectGuid"],
    }


def _sync_imf_file_records(rewritten: dict[str, bytes]) -> dict[str, bytes]:
    """Align fileRecord.json sizes with bin/@N.bin payloads (IICS IMF import requirement)."""
    if "fileRecord.json" not in rewritten:
        return rewritten
    payload = json.loads(rewritten["fileRecord.json"].decode("utf-8"))
    if not isinstance(payload, list):
        return rewritten
    bin_members = {
        member: rewritten[member]
        for member in rewritten
        if member.startswith("bin/") and member.endswith(".bin")
    }
    attach_time = int(time.time() * 1000)
    for record in payload:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("id", "")).lstrip("@")
        bin_member = next(
            (member for member in bin_members if member.endswith(f"/@{record_id}.bin")),
            None,
        )
        if not bin_member:
            continue
        record["size"] = len(bin_members[bin_member])
        record["attachTime"] = attach_time
    rewritten["fileRecord.json"] = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return rewritten


_sync_dmapplet_file_records = _sync_imf_file_records


def _rewrite_reference_asset_zip(
    source_bytes: bytes,
    *,
    replacements: dict[str, str],
    sync_file_records: bool = False,
) -> bytes:
    """Rewrite JSON/text members inside a reference IICS asset zip."""
    rewritten: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as zin:
        for member in zin.namelist():
            data = zin.read(member)
            if member.endswith((".json", ".meta", ".xml")):
                text = data.decode("utf-8")
                for old, new in _ordered_replacement_items(replacements):
                    text = text.replace(old, new)
                data = text.encode("utf-8")
            elif member.startswith("bin/") and member.endswith(".bin"):
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    rewritten[member] = data
                    continue
                for old, new in _ordered_replacement_items(replacements):
                    text = text.replace(old, new)
                data = text.encode("utf-8")
            rewritten[member] = data
    if sync_file_records:
        rewritten = _sync_imf_file_records(rewritten)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for member, data in rewritten.items():
            zout.writestr(member, data)
    return buf.getvalue()


def _reference_dtemplate_mapplet_names(shell: dict[str, Any]) -> set[str]:
    """Mapplet object names referenced by the reference DTEMPLATE shell."""
    entry = shell.get("dtemplate_entry")
    if not entry:
        return set()
    ref_by_guid = {
        obj["objectGuid"]: obj["objectName"]
        for obj in shell.get("exported_objects") or []
        if obj.get("objectType") == "DMAPPLET"
    }
    with zipfile.ZipFile(io.BytesIO(entry)) as zin:
        template = json.loads(zin.read("mappingTemplate.json"))
    refs = template[0].get("references") if isinstance(template, list) and template else []
    names: set[str] = set()
    for ref in refs or []:
        guid = str(ref.get("refObjectId") or "").lstrip("@")
        name = ref_by_guid.get(guid)
        if name:
            names.add(name)
    return names


def _po_process_object_name(mapping_name: str) -> str:
    """Convert mapping name to IICS TASKFLOW ``$po:`` process object id (hyphenated)."""
    parts = mapping_name.split("_", 2)
    if len(parts) == 3:
        return f"{parts[0]}-{parts[1]}-{parts[2]}"
    return mapping_name.replace("_", "-")


def _map_reference_dmapplet_names(
    ref_names: set[str],
    dmapplet_name_map: dict[str, str],
) -> set[str]:
    """Map reference-shell mapplet names to generated target names."""
    return {dmapplet_name_map.get(name, name) for name in ref_names}


def _reference_dtemplate_mapplet_ref_guids(
    shell: dict[str, Any],
    *,
    dmapplet_name_map: dict[str, str],
    mapplet_guids: dict[str, str],
) -> list[str]:
    """Resolve DTEMPLATE mapplet references in reference order using manifest guids."""
    entry = shell.get("dtemplate_entry")
    if not entry:
        return []
    ref_by_guid = {
        obj["objectGuid"]: obj["objectName"]
        for obj in shell.get("exported_objects") or []
        if obj.get("objectType") == "DMAPPLET"
    }
    with zipfile.ZipFile(io.BytesIO(entry)) as zin:
        template = json.loads(zin.read("mappingTemplate.json"))
    refs = template[0].get("references") if isinstance(template, list) and template else []
    guids: list[str] = []
    for ref in refs or []:
        old_guid = str(ref.get("refObjectId") or "").lstrip("@")
        ref_name = ref_by_guid.get(old_guid)
        if not ref_name:
            continue
        target_name = dmapplet_name_map.get(ref_name, ref_name)
        new_guid = mapplet_guids.get(target_name)
        if new_guid:
            guids.append(new_guid)
    return guids


def _build_reference_text_replacements(
    reference_shell: dict[str, Any],
    shell_config: dict[str, Any],
    *,
    target_mapping_name: str,
    project_name: str,
    folder_name: str,
    dtemplate_guid: str,
    mtt_frs_guid: str,
    mapplet_guids: dict[str, str],
    taskflow_guid: str | None,
    seq_guids: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build ordered text replacements for reference DTEMPLATE/MTT/TASKFLOW shells."""
    ref_mapping = reference_shell.get("reference_mapping_name") or target_mapping_name
    ref_objects = reference_shell.get("exported_objects") or []
    by_name = {obj["objectName"]: obj for obj in ref_objects}
    replacements: dict[str, str] = {}

    if ref_mapping != target_mapping_name:
        replacements[ref_mapping] = target_mapping_name
        replacements[f"{ref_mapping}_preview"] = f"{target_mapping_name}_preview"
        ref_po = _po_process_object_name(ref_mapping)
        target_po = _po_process_object_name(target_mapping_name)
        if ref_po != target_po:
            replacements[ref_po] = target_po

    ref_project = next((o for o in ref_objects if o.get("objectType") == "Project"), None)
    ref_folder = next((o for o in ref_objects if o.get("objectType") == "Folder"), None)
    if ref_project and ref_project["objectName"] != project_name:
        replacements[ref_project["objectName"]] = project_name
    if ref_folder and ref_folder["objectName"] != folder_name:
        replacements[ref_folder["objectName"]] = folder_name

    for obj in ref_objects:
        if obj.get("objectName") != ref_mapping:
            continue
        old_guid = obj["objectGuid"]
        otype = obj.get("objectType") or ""
        if otype == "DTEMPLATE":
            replacements[old_guid] = dtemplate_guid
            replacements[f"@{old_guid}"] = f"@{dtemplate_guid}"
        elif otype == "MTT":
            replacements[old_guid] = mtt_frs_guid
            replacements[f"@{old_guid}"] = f"@{mtt_frs_guid}"
        elif otype == "TASKFLOW" and taskflow_guid:
            replacements[old_guid] = taskflow_guid
            replacements[f"@{old_guid}"] = f"@{taskflow_guid}"

    dmapplet_name_map = dict(shell_config.get("dmapplet_name_map") or {})
    mapped_ref_targets = set(dmapplet_name_map.values())
    for ref_name, target_name in dmapplet_name_map.items():
        ref_obj = by_name.get(ref_name)
        new_guid = mapplet_guids.get(target_name)
        if ref_obj and new_guid:
            old_guid = ref_obj["objectGuid"]
            replacements[old_guid] = new_guid
            replacements[f"@{old_guid}"] = f"@{new_guid}"

    for target_name, new_guid in mapplet_guids.items():
        if target_name in mapped_ref_targets:
            continue
        ref_obj = by_name.get(target_name)
        if ref_obj:
            old_guid = ref_obj["objectGuid"]
            replacements[old_guid] = new_guid
            replacements[f"@{old_guid}"] = f"@{new_guid}"

    keep_connections = {PRIMARY_REFERENCE_CONNECTION, SDE_FLAT_FILE_CONNECTION}
    primary = reference_shell.get("primary_conn_guid") or ""
    for old_guid, new_guid in (reference_shell.get("remapped_connection_guids") or {}).items():
        replacements[old_guid] = new_guid
        replacements[f"@{old_guid}"] = f"@{new_guid}"
    for obj in ref_objects:
        if obj.get("objectType") != "Connection":
            continue
        if obj.get("objectName") in keep_connections or not primary:
            continue
        old_guid = obj["objectGuid"]
        replacements[old_guid] = primary
        replacements[f"@{old_guid}"] = f"@{primary}"

    for old, new in shell_config.get("text_replacements") or []:
        replacements[old] = new

    replacements.update(
        _sequence_guid_replacements(
            reference_shell,
            shell_config,
            seq_guids or {},
        )
    )

    return replacements


def _rewrite_reference_dtemplate_zip(
    source_bytes: bytes,
    *,
    replacements: dict[str, str],
    target_name: str,
    dtemplate_guid: str,
    mapplet_ref_guids: list[str],
) -> bytes:
    data = _rewrite_reference_asset_zip(
        source_bytes, replacements=replacements, sync_file_records=True,
    )
    with zipfile.ZipFile(io.BytesIO(data)) as zin:
        members = {name: zin.read(name) for name in zin.namelist()}
    if "mappingTemplate.json" in members:
        template = json.loads(members["mappingTemplate.json"].decode("utf-8"))
        if isinstance(template, list) and template:
            template[0]["name"] = target_name
            template[0]["assetFrsGuid"] = dtemplate_guid
            template[0]["references"] = [
                {
                    "@type": "reference",
                    "refObjectId": f"@{guid}",
                    "refType": "mappletTemplate",
                    "refObjInSync": "false",
                }
                for guid in mapplet_ref_guids
            ]
            members["mappingTemplate.json"] = json.dumps(
                template, separators=(",", ":"),
            ).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for member, payload in members.items():
            zout.writestr(member, payload)
    return buf.getvalue()


def _rewrite_reference_mtt_zip(
    source_bytes: bytes,
    *,
    replacements: dict[str, str],
    target_name: str,
    mtt_frs_guid: str,
    dtemplate_guid: str,
) -> bytes:
    data = _rewrite_reference_asset_zip(source_bytes, replacements=replacements)
    with zipfile.ZipFile(io.BytesIO(data)) as zin:
        members = {name: zin.read(name) for name in zin.namelist()}
    if "mtTask.json" in members:
        task = json.loads(members["mtTask.json"].decode("utf-8"))
        if isinstance(task, list) and task:
            task[0]["name"] = target_name
            task[0]["frsGuid"] = mtt_frs_guid
            task[0]["mappingId"] = f"@{dtemplate_guid}"
            conn_fields = (
                "sourceConnectionId", "targetConnectionId",
                "lookupConnectionId", "connectionId",
            )
            for param in task[0].get("parameters") or []:
                for field in conn_fields:
                    value = param.get(field)
                    if not isinstance(value, str) or not value.startswith("@"):
                        continue
                    guid = value[1:]
                    mapped = replacements.get(guid) or replacements.get(value)
                    if mapped:
                        param[field] = mapped if mapped.startswith("@") else f"@{mapped}"
            members["mtTask.json"] = json.dumps(task, separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for member, payload in members.items():
            zout.writestr(member, payload)
    return buf.getvalue()


def _imf_bin_path(file_records: list[dict]) -> str:
    for record in file_records:
        if record.get("type") == "IMFOBJECT":
            return f"bin/{record['id']}.bin"
    return "bin/@2.bin"


def _graft_native_imf_into_reference_zip(
    reference_bytes: bytes,
    *,
    native_imf: bytes,
    replacements: dict[str, str],
    template_member: str,
    target_name: str,
    target_guid: str | None = None,
    mapplet_ref_guids: list[str] | None = None,
    set_asset_frs_guid: bool = False,
) -> bytes:
    """Keep reference preview/image shell; replace IMFOBJECT bin with native PC graph."""
    rewritten: dict[str, bytes] = {}
    reference_bins: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(reference_bytes)) as zin:
        for member in zin.namelist():
            data = zin.read(member)
            if member.startswith("bin/") and member.endswith(".bin"):
                reference_bins[member] = data
                continue
            if member.endswith((".json", ".meta")):
                text = data.decode("utf-8")
                for old, new in _ordered_replacement_items(replacements):
                    text = text.replace(old, new)
                data = text.encode("utf-8")
            rewritten[member] = data

    file_records = json.loads(rewritten["fileRecord.json"].decode("utf-8"))
    imf_path = _imf_bin_path(file_records)
    rewritten[imf_path] = native_imf
    for member, data in reference_bins.items():
        if member != imf_path:
            rewritten[member] = data

    rewritten = _sync_imf_file_records(rewritten)

    if template_member in rewritten:
        template = json.loads(rewritten[template_member].decode("utf-8"))
        if isinstance(template, list) and template:
            template[0]["name"] = target_name
            if set_asset_frs_guid and target_guid:
                template[0]["assetFrsGuid"] = target_guid
            else:
                template[0].pop("assetFrsGuid", None)
            if mapplet_ref_guids is not None:
                template[0]["references"] = [
                    {
                        "@type": "reference",
                        "refObjectId": f"@{guid}",
                        "refType": "mappletTemplate",
                        "refObjInSync": "false",
                    }
                    for guid in mapplet_ref_guids
                ]
            rewritten[template_member] = json.dumps(
                template, separators=(",", ":"),
            ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for member, data in rewritten.items():
            zout.writestr(member, data)
    return buf.getvalue()


def _sequence_guid_replacements(
    reference_shell: dict[str, Any] | None,
    shell_config: dict[str, Any] | None,
    seq_guids: dict[str, str],
) -> dict[str, str]:
    """Map reference SequenceGenerator guids to generated target guids."""
    if not reference_shell or not seq_guids:
        return {}
    seq_name_map = dict(shell_config.get("text_replacements") or []) if shell_config else {}
    replacements: dict[str, str] = {}
    for obj in reference_shell.get("exported_objects") or []:
        if obj.get("objectType") != "SequenceGenerator":
            continue
        ref_name = obj["objectName"]
        target_name = seq_name_map.get(ref_name, ref_name)
        new_guid = seq_guids.get(target_name)
        if not new_guid:
            continue
        old_guid = obj["objectGuid"]
        replacements[old_guid] = new_guid
        replacements[f"@{old_guid}"] = f"@{new_guid}"
    return replacements


def _reference_dmapplet_sequence_ref_guids(
    ref_dmapplet_bytes: bytes,
    replacements: dict[str, str],
) -> list[str]:
    """Resolve manifest objectRefs for a reference-shell mapplet sequenceGen deps."""
    with zipfile.ZipFile(io.BytesIO(ref_dmapplet_bytes)) as zin:
        template = json.loads(zin.read("mappletTemplate.json"))
    refs = template[0].get("references") if isinstance(template, list) and template else []
    guids: list[str] = []
    for ref in refs or []:
        if ref.get("refType") != "sequenceGen":
            continue
        old_id = str(ref.get("refObjectId") or "").lstrip("@")
        new_id = replacements.get(old_id, old_id)
        if new_id and new_id not in guids:
            guids.append(new_id)
    return guids


def _rewrite_reference_dmapplet_zip(
    source_bytes: bytes,
    *,
    replacements: dict[str, str],
    target_name: str,
    target_guid: str | None = None,
) -> bytes:
    """Rewrite a client gold DMAPPLET shell (preview image + IMF bins) for JobDimension names."""
    rewritten: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as zin:
        for member in zin.namelist():
            data = zin.read(member)
            if member.endswith((".json", ".meta")):
                text = data.decode("utf-8")
                for old, new in _ordered_replacement_items(replacements):
                    text = text.replace(old, new)
                data = text.encode("utf-8")
            elif member.startswith("bin/") and member.endswith(".bin"):
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    rewritten[member] = data
                    continue
                for old, new in _ordered_replacement_items(replacements):
                    text = text.replace(old, new)
                data = text.encode("utf-8")
            rewritten[member] = data

    rewritten = _sync_dmapplet_file_records(rewritten)
    if "mappletTemplate.json" in rewritten:
        template = json.loads(rewritten["mappletTemplate.json"].decode("utf-8"))
        if isinstance(template, list) and template:
            template[0]["name"] = target_name
            if target_guid:
                template[0]["assetFrsGuid"] = target_guid
            else:
                template[0].pop("assetFrsGuid", None)
            rewritten["mappletTemplate.json"] = json.dumps(
                template, separators=(",", ":"),
            ).encode("utf-8")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for member, data in rewritten.items():
            zout.writestr(member, data)
    return buf.getvalue()


def _invert_name_map(name_map: dict[str, str]) -> dict[str, str]:
    return {target: source for source, target in name_map.items()}


def _load_reference_shell(reference_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(reference_path) as zf:
        manifest = json.loads(zf.read("exportMetadata.v2.json"))
        sys_entries = {
            name: zf.read(name)
            for name in zf.namelist()
            if name.startswith("SYS/")
        }
        dmapplet_entries = {
            Path(name).name[: -len(".DMAPPLET.zip")]: zf.read(name)
            for name in zf.namelist()
            if name.endswith(".DMAPPLET.zip")
        }
        dtemplate_entry: bytes | None = None
        mtt_entry: bytes | None = None
        taskflow_entry: bytes | None = None
        reference_mapping_name: str | None = None
        for name in zf.namelist():
            base = Path(name).name
            if base.endswith(".DTEMPLATE.zip"):
                dtemplate_entry = zf.read(name)
                reference_mapping_name = base[: -len(".DTEMPLATE.zip")]
            elif reference_mapping_name and base == f"{reference_mapping_name}.MTT.zip":
                mtt_entry = zf.read(name)
            elif reference_mapping_name and base == f"{reference_mapping_name}.TASKFLOW.xml":
                taskflow_entry = zf.read(name)
    exported = manifest.get("exportedObjects") or []
    by_name = {obj["objectName"]: obj for obj in exported}
    return {
        "reference_path": str(reference_path),
        "exported_objects": exported,
        "sys_entries": sys_entries,
        "dmapplet_entries": dmapplet_entries,
        "dtemplate_entry": dtemplate_entry,
        "mtt_entry": mtt_entry,
        "taskflow_entry": taskflow_entry,
        "reference_mapping_name": reference_mapping_name,
        "primary_conn_guid": by_name["Orcl_BI_Jacobs_HR_PC2CDI"]["objectGuid"],
        "agent_group_guid": by_name["PC Secure Agent Group"]["objectGuid"],
    }


def _merge_manifest_from_reference(
    ref_objects: list[dict],
    *,
    mapping_name: str,
    folder_path: str,
    pc_folder: str,
    project_obj: dict,
    folder_obj: dict,
    dtemplate_obj: dict,
    mtt_obj: dict,
    taskflow_objects: list[dict],
    dmapplet_objects: list[dict],
    sequence_objects: list[dict],
    skip_dmapplets: set[str],
    dmapplet_name_map: dict[str, str],
) -> list[dict]:
    """Preserve client reference manifest order; swap in JobDimension assets + target paths."""
    gen_dmapplets = {o["objectName"]: o for o in dmapplet_objects}
    taskflow = taskflow_objects[0] if taskflow_objects else None
    sequence = sequence_objects[0] if sequence_objects else None

    merged: list[dict] = []
    used: set[str] = set()

    def _append(obj: dict) -> None:
        guid = obj.get("objectGuid") or ""
        if guid and guid in used:
            return
        merged.append(obj)
        if guid:
            used.add(guid)

    for ref in ref_objects:
        otype = ref.get("objectType") or ""
        oname = ref.get("objectName") or ""

        if otype in {"Connection", "AgentGroup"}:
            _append(ref)
            continue
        if otype == "Project":
            _append({**project_obj, "path": "/Explore"})
            continue
        if otype == "Folder":
            _append({**folder_obj, "path": f"/Explore/{project_obj['objectName']}"})
            continue
        if otype == "DMAPPLET":
            if oname in skip_dmapplets:
                continue
            gen_name = dmapplet_name_map.get(oname, oname)
            gen = gen_dmapplets.get(gen_name)
            if gen:
                _append({**gen, "path": folder_path})
            continue
        if otype == "DTEMPLATE":
            _append({**dtemplate_obj, "path": folder_path})
            continue
        if otype == "MTT":
            _append({**mtt_obj, "path": folder_path})
            continue
        if otype == "TASKFLOW" and taskflow:
            _append({**taskflow, "path": folder_path})
            continue
        if otype == "SequenceGenerator" and sequence:
            _append({**sequence, "path": folder_path})
            continue

    return merged


# ── Main generator ────────────────────────────────────────────────────────────

def _count_folder_import_assets(
    exported_objects: list[dict],
    folder_path: str,
    pc_folder: str,
) -> int:
    """Count IICS Select Assets rows: folder + mapping/mtt/taskflow/mapplet content."""
    return len([
        obj for obj in exported_objects
        if obj.get("path") == folder_path
        or (obj.get("objectType") == "Folder" and obj.get("objectName") == pc_folder)
    ])


def _order_single_session_exported_objects(
    *,
    mapping_name: str,
    dtemplate_obj: dict,
    folder_obj: dict,
    project_obj: dict,
    conn_obj: dict,
    mtt_obj: dict,
    taskflow_objects: list[dict],
    dmapplet_objects: list[dict],
    sequence_objects: list[dict],
    agent_obj: dict,
) -> list[dict]:
    """Match gold single-session SDE/SIL manifest ordering."""
    code_lookup = [o for o in dmapplet_objects if "CodeLookup" in o["objectName"]]
    sa_mapplets = sorted(
        o for o in dmapplet_objects
        if o not in code_lookup and "mplt_SA" in o["objectName"]
    )
    bc_mapplets = sorted(
        o for o in dmapplet_objects
        if o not in code_lookup and "mplt_BC" in o["objectName"]
    )
    other_mapplets = [
        o for o in dmapplet_objects
        if o not in code_lookup and o not in sa_mapplets and o not in bc_mapplets
    ]

    if mapping_name.startswith("SDE_"):
        return (
            [dtemplate_obj, folder_obj]
            + other_mapplets
            + code_lookup
            + [project_obj, conn_obj, mtt_obj]
            + taskflow_objects
            + sa_mapplets
            + bc_mapplets
            + sequence_objects
            + [agent_obj]
        )

    return (
        [dtemplate_obj, folder_obj]
        + code_lookup
        + [project_obj, conn_obj, mtt_obj]
        + taskflow_objects
        + sa_mapplets
        + bc_mapplets
        + other_mapplets
        + sequence_objects
        + [agent_obj]
    )


class IICSPackageGenerator:
    """Generate a complete IICS import package from all parsed PC XML files."""

    PROJECT_NAME     = "RPA_PC_Modernization"
    FOLDER_NAME      = "Custom_SDE_SupplyChain"
    CONNECTION_NAME  = "DataWarehouse_PA"
    CONNECTION_PARAM = "DBConnection_OLAP"
    GOLD_CONNECTION_NAME = "Orcl_BI_Jacobs_HR_PC2CDI"
    GOLD_TARGET_CONN_PARAM = "Target"
    AGENT_GROUP_NAME = "PC Secure Agent Group"
    ORG_NAME         = "Jacobs"
    ORG_ID           = "gO4aVWAxgK0lY2UdXmECWZ"
    AGENT_ID         = "010CW70800000000000B"

    def __init__(
        self,
        parsed_json_dir: str | Path = "output/parsed_json",
        remediated_xml_dir: str | Path = "output/remediated_xml",
        output_dir: str | Path = "output/iics_generated",
        output_zip_name: str = "Custom_Project_Export.zip",
        project_root: str | Path | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.parsed_json_dir = Path(parsed_json_dir)
        self.remediated_xml_dir = Path(remediated_xml_dir)
        self.output_dir      = Path(output_dir)
        self.output_zip_name = output_zip_name
        self.project_root    = Path(project_root) if project_root else self._resolve_project_root()
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _resolve_project_root() -> Path:
        for start in (Path.cwd(),):
            candidate = start.resolve()
            for _ in range(8):
                if (candidate / "common/config/iics_success_criteria.json").exists():
                    return candidate
                if candidate.parent == candidate:
                    break
                candidate = candidate.parent
        return Path.cwd()

    def generate(self) -> dict[str, Any]:
        self.logger.info("IICS Package Generator starting. source=%s", self.parsed_json_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        json_files = sorted(
            f for f in self.parsed_json_dir.glob("*.json") if not f.name.startswith(".")
        )
        self.logger.info("Found %d parsed JSON files.", len(json_files))

        # Separate PC XML exports (SDE + SIL) → one gold single-session zip each.
        # Combining them produces 11+ import assets and breaks IICS import expectations.
        if len(json_files) > 1:
            return self._generate_per_mapping_packages(json_files)

        return self._generate_combined_package(json_files)

    def _generate_per_mapping_packages(self, json_files: list[Path]) -> dict[str, Any]:
        import shutil

        packages = self.generate_single_session_packages()
        named_zips: list[str] = []
        for pkg in packages:
            src = Path(pkg["output_zip"])
            dest = self.output_dir / f"{pkg['mapping_name']}.zip"
            shutil.copy2(src, dest)
            named_zips.append(str(dest))
            self.logger.info(
                "Single-session package: %s (%d import assets) -> %s",
                pkg["mapping_name"], pkg.get("folder_import_assets", pkg["total_assets"]), dest.name,
            )

        stale = self.output_dir / self.output_zip_name
        if stale.exists():
            stale.unlink()
            self.logger.info("Removed combined %s (use per-mapping zips instead).", stale.name)

        summary = {
            "mode": "single_session_per_mapping",
            "packages": packages,
            "output_zips": named_zips,
            "total_assets": sum(p["total_assets"] for p in packages),
            "iics_import_instructions": (
                "Import ONE zip per mapping (client reference-shell format). "
                "Path: RPA_PC_Modernization/Custom_SDE_SupplyChain. "
                "Example: SDE_ORA_JobDimension.zip, SIL_JobDimension.zip."
            ),
        }
        (self.output_dir / "generation_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8",
        )
        return summary

    def _generate_combined_package(self, json_files: list[Path]) -> dict[str, Any]:
        project_guid     = _new_guid()
        agent_group_guid = _new_guid()

        folder_guid      = _new_guid()
        conn_guid        = _new_guid()
        folder_path      = f"/Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}"

        connections: dict[str, str] = {
            self.CONNECTION_NAME: conn_guid,
            self.CONNECTION_PARAM: conn_guid,
        }
        mapping_objects: list[dict] = []
        zip_contents: dict[str, bytes] = {}
        mapping_name_counts: dict[str, int] = {}

        def _unique_mapping_name(base: str) -> str:
            mapping_name_counts[base] = mapping_name_counts.get(base, 0) + 1
            if mapping_name_counts[base] == 1:
                return base
            return f"{base}_{mapping_name_counts[base]}"

        project_obj = {
            "objectGuid": project_guid,
            "objectName": self.PROJECT_NAME,
            "objectType": "Project",
            "path": "/Explore",
            "providerName": None,
            "metadata": _meta_with_ctx(None, [], "Migrated project from PowerCenter", "Binary", "COMPLETE", []),
        }
        zip_contents[f"Explore/{self.PROJECT_NAME}.Project.json"] = \
            _build_project_json(self.PROJECT_NAME, project_guid).encode("utf-8")

        folder_obj = {
            "objectGuid": folder_guid,
            "objectName": self.FOLDER_NAME,
            "objectType": "Folder",
            "path": f"/Explore/{self.PROJECT_NAME}",
            "providerName": None,
            "metadata": _meta_with_ctx(None, [], None, "Binary", "COMPLETE", []),
        }
        zip_contents[f"Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}.Folder.json"] = \
            _build_folder_json(self.FOLDER_NAME, folder_guid, self.PROJECT_NAME, project_guid).encode("utf-8")

        ag_handle = _repo_handle()
        agent_obj = {
            "objectGuid": agent_group_guid,
            "objectName": self.AGENT_GROUP_NAME,
            "objectType": "AgentGroup",
            "path": "/SYS",
            "providerName": None,
            "metadata": _meta_with_ctx(ag_handle, [], None, "JSON", "VALID", _CONTEXT_ATTR),
        }
        zip_contents[f"SYS/{self.AGENT_GROUP_NAME}.AgentGroup.zip"] = \
            _build_agent_group_zip(self.AGENT_GROUP_NAME, agent_group_guid)

        conn_handle = _repo_handle()
        conn_obj = {
            "objectGuid": conn_guid,
            "objectName": self.CONNECTION_NAME,
            "objectType": "Connection",
            "path": "/SYS",
            "providerName": None,
            "metadata": _meta_with_ctx(
                conn_handle, [agent_group_guid],
                None, "JSON", "COMPLETE", _CONTEXT_ATTR,
            ),
        }
        zip_contents[f"SYS/{self.CONNECTION_NAME}.Connection.zip"] = \
            _build_connection_zip(
                self.CONNECTION_NAME, conn_guid,
                agent_group_guid, self.ORG_ID, self.AGENT_ID,
            )

        # ── Process each parsed XML ───────────────────────────────────────────
        mapplet_objects: list[dict] = []
        sequence_objects: list[dict] = []
        mapplet_guid_registry: dict[str, str] = {}  # mapplet_name -> guid (global unique)
        sequence_guid_registry: dict[str, str] = {}
        global_mtt_tasks: list[tuple[str, str]] = []
        global_mtt_seen: set[str] = set()

        for json_file in json_files:
            if json_file.name.startswith("."):
                continue
            self.logger.info("Processing %s ...", json_file.name)
            with open(json_file, encoding="utf-8") as fh:
                parsed = json.load(fh)

            for folder_data in parsed.get("folders", []):
                _ensure_reusable_transformations(
                    folder_data, json_file.name, self.remediated_xml_dir,
                )
                # Create DMAPPLETs for each unique mapplet used by mappings in this folder.
                used_mapplet_names: list[str] = []
                seen_mp: set[str] = set()
                for mapping in folder_data.get("mappings", []):
                    for mp_name in _collect_used_mapplet_names(mapping):
                        key = mp_name.casefold()
                        if key in seen_mp:
                            continue
                        seen_mp.add(key)
                        used_mapplet_names.append(mp_name)

                folder_mapplet_guids: dict[str, str] = {}
                for mp_name in used_mapplet_names:
                    mapplet_def = _lookup_mapplet(folder_data, mp_name)
                    if not mapplet_def:
                        self.logger.warning(
                            "Mapping references mapplet '%s' but folder has no MAPPLET definition",
                            mp_name,
                        )
                        continue
                    if mp_name in mapplet_guid_registry:
                        folder_mapplet_guids[mp_name] = mapplet_guid_registry[mp_name]
                        continue
                    dmapplet_guid = _new_guid()
                    mapplet_guid_registry[mp_name] = dmapplet_guid
                    folder_mapplet_guids[mp_name] = dmapplet_guid
                    dmapplet_zip = _build_dmapplet_zip(mapplet_def, folder_data, dmapplet_guid)
                    dmapplet_path = (
                        f"Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}/{mp_name}.DMAPPLET.zip"
                    )
                    zip_contents[dmapplet_path] = dmapplet_zip
                    mp_handle = _repo_handle()
                    mapplet_objects.append({
                        "objectGuid": dmapplet_guid,
                        "objectName": mp_name,
                        "objectType": "DMAPPLET",
                        "path": folder_path,
                        "providerName": None,
                        "metadata": _meta_with_ctx(
                            mp_handle, [], f"Mapplet pushed from PC to ICS : {mp_name}",
                            "JSON", "VALID", _CONTEXT_ATTR,
                        ),
                    })

                mtt_by_name: dict[str, str] = {}
                # ── Per mapping (all placed in Custom_SDE_SupplyChain) ─────────
                for mapping in folder_data.get("mappings", []):
                    m_name       = _unique_mapping_name(mapping["mapping_name"])
                    dtemplate_guid = _new_guid()
                    mtt_frs_guid   = _new_guid()
                    mtt_by_name[m_name] = mtt_frs_guid

                    sessions   = folder_data.get("sessions", [])
                    session    = next(
                        (s for s in sessions if s.get("session_name") == m_name
                         or s.get("mapping_name") == m_name
                         or s.get("mapping_name") == mapping["mapping_name"]),
                        next(
                            (s for s in sessions if s.get("mapping_name") == mapping["mapping_name"]),
                            sessions[0] if sessions else None,
                        ),
                    )
                    workflows  = folder_data.get("workflows", [])
                    workflow   = next(
                        (w for w in workflows if w.get("workflow_name") == m_name
                         or w.get("workflow_name") == mapping["mapping_name"]),
                        workflows[0] if workflows else None,
                    )

                    conn_guid = connections[self.CONNECTION_NAME]

                    seq_guids: dict[str, str] = {}
                    for seq_name, seq_tx in _collect_sequence_generators_for_session(
                        session, folder_data,
                    ):
                        if seq_name in sequence_guid_registry:
                            seq_guids[seq_name] = sequence_guid_registry[seq_name]
                            continue
                        seq_guid = _new_guid()
                        sequence_guid_registry[seq_name] = seq_guid
                        seq_guids[seq_name] = seq_guid
                        seq_zip = _build_sequence_generator_zip(seq_name, seq_guid, seq_tx)
                        seq_path = (
                            f"Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}/"
                            f"{seq_name}.SequenceGenerator.zip"
                        )
                        zip_contents[seq_path] = seq_zip
                        seq_handle = _repo_handle()
                        sequence_objects.append({
                            "objectGuid": seq_guid,
                            "objectName": seq_name,
                            "objectType": "SequenceGenerator",
                            "path": folder_path,
                            "providerName": None,
                            "metadata": _meta_with_ctx(
                                seq_handle, [],
                                "Re-usable Sequence Generator pushed from PC to ICS",
                                "JSON", "VALID", _CONTEXT_ATTR,
                            ),
                        })

                    # DTEMPLATE (native CDI mapping) with DMAPPLET references
                    dt_handle = _repo_handle()
                    dtemplate_zip = _build_dtemplate_zip(
                        mapping, folder_data, dtemplate_guid, mapplet_guids=folder_mapplet_guids,
                    )
                    dt_path = f"Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}/{m_name}.DTEMPLATE.zip"
                    zip_contents[dt_path] = dtemplate_zip
                    dtemplate_deps = [
                        folder_mapplet_guids[n]
                        for n in _collect_used_mapplet_names(mapping)
                        if n in folder_mapplet_guids
                    ]
                    dtemplate_obj = {
                        "objectGuid": dtemplate_guid,
                        "objectName": m_name,
                        "objectType": "DTEMPLATE",
                        "path": folder_path,
                        "providerName": None,
                        "metadata": _meta_with_ctx(
                            dt_handle, dtemplate_deps,
                            f"Mapping pushed from PC to ICS : {m_name}",
                            "JSON", "VALID", _CONTEXT_ATTR,
                        ),
                    }

                    mtt_handle = _repo_handle()
                    mtt_zip = _build_mtt_zip(
                        session, mtt_frs_guid, dtemplate_guid,
                        agent_group_guid, connections, folder_data, m_name,
                        mapping=mapping, seq_guids=seq_guids,
                    )
                    mtt_path = f"Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}/{m_name}.MTT.zip"
                    zip_contents[mtt_path] = mtt_zip
                    mtt_obj = {
                        "objectGuid": mtt_frs_guid,
                        "objectName": m_name,
                        "objectType": "MTT",
                        "path": folder_path,
                        "providerName": None,
                        "metadata": _meta_with_ctx(
                            mtt_handle,
                            [conn_guid, agent_group_guid, dtemplate_guid],
                            f"Session pushed from PC to ICS : {m_name}",
                            "JSON", "VALID", _CONTEXT_ATTR,
                        ),
                    }

                    mapping_objects.append(dtemplate_obj)
                    mapping_objects.append(mtt_obj)
                    if m_name not in global_mtt_seen:
                        global_mtt_seen.add(m_name)
                        global_mtt_tasks.append((m_name, mtt_frs_guid))

        taskflow_objects: list[dict] = []
        if global_mtt_tasks:
            wf_name = (
                _combined_workflow_name([name for name, _ in global_mtt_tasks])
                if len(global_mtt_tasks) > 1
                else global_mtt_tasks[0][0]
            )
            workflow = {"workflow_name": wf_name}
            tf_guid = _new_guid()
            from datetime import datetime
            now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.") + \
                f"{datetime.utcnow().microsecond // 1000:03d}Z"
            entry_id = f"{_h()}-gt-{abs(hash(wf_name)) % 99999999}-{now_str}::tf.xml"
            tf_xml = _build_workflow_taskflow_xml(workflow, global_mtt_tasks, tf_guid, entry_id)
            tf_path = f"Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}/{wf_name}.TASKFLOW.xml"
            zip_contents[tf_path] = tf_xml.encode("utf-8")
            taskflow_objects.append({
                "objectGuid": tf_guid,
                "objectName": wf_name,
                "objectType": "TASKFLOW",
                "path": folder_path,
                "providerName": None,
                "metadata": _meta_with_ctx(
                    entry_id,
                    [agent_group_guid, *[guid for _, guid in global_mtt_tasks]],
                    "These workflows are created from the Workflow Generation Wizard.",
                    "application/json; charset=utf-8",
                    "VALID",
                    None,
                    model_version={"major": 1, "minor": 0},
                ),
            })

        # Manifest order follows gold multi-session exports when multiple MTTs exist.
        mtt_objects = [obj for obj in mapping_objects if obj["objectType"] == "MTT"]
        dtemplate_objects = [obj for obj in mapping_objects if obj["objectType"] == "DTEMPLATE"]
        if len(mtt_objects) > 1:
            exported_objects = (
                taskflow_objects
                + [folder_obj, project_obj, conn_obj]
                + _interleave_dtemplate_mtt(dtemplate_objects, mtt_objects)
                + mapplet_objects
                + sequence_objects
                + [agent_obj]
            )
        else:
            exported_objects = (
                [project_obj, conn_obj, agent_obj]
                + mtt_objects
                + [folder_obj]
                + taskflow_objects
                + dtemplate_objects
                + mapplet_objects
                + sequence_objects
            )
        job_name = f"job-{int(time.time() * 1000)}"
        manifest = {
            "name": job_name,
            "sourceOrgId": self.ORG_ID,
            "sourceOrgName": self.ORG_NAME,
            "exportedObjects": exported_objects,
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")

        csv_buf = io.StringIO()
        writer  = csv.writer(csv_buf)
        writer.writerow(["objectPath", "objectName", "objectType", "id"])
        for obj in exported_objects:
            writer.writerow([obj["path"], obj["objectName"], obj["objectType"], obj["objectGuid"]])
        csv_filename = f"ContentsofExportPackage_{job_name}.csv"
        csv_bytes    = csv_buf.getvalue().encode("utf-8")

        checksums: dict[str, str] = {}
        output_zip_path = self.output_dir / self.output_zip_name

        with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            zout.writestr("exportMetadata.v2.json", manifest_bytes)
            checksums["exportMetadata.v2.json"] = _sha256_bytes(manifest_bytes)

            zout.writestr(csv_filename, csv_bytes)
            # ContentsofExportPackage CSV is NOT included in checksums (matches client format)

            for rel_path, content in sorted(zip_contents.items()):
                zout.writestr(rel_path, content)
                checksums[rel_path] = sha256_hex(content)

            zout.writestr("exportPackage.chksum", build_checksum_file(checksums))

        (self.output_dir / csv_filename).write_bytes(csv_bytes)
        (self.output_dir / "exportMetadata.v2.json").write_bytes(manifest_bytes)

        ok, chk_errors = validate_zip_checksums(output_zip_path)
        if not ok:
            self.logger.error("Checksum validation failed: %s", chk_errors[:10])
            raise RuntimeError(f"Generated package failed checksum validation: {chk_errors[0]}")

        benchmark_profile = "multi_session" if len(mtt_objects) > 1 else "single_session"
        benchmark = IICSSuccessBenchmark(project_root=self.project_root)
        benchmark_result = benchmark.validate_package(output_zip_path, profile=benchmark_profile)
        if not benchmark_result.passed:
            failed = [c for c in benchmark_result.checks if not c.passed]
            self.logger.error(
                "Gold-reference benchmark validation failed (%s): %s",
                benchmark_profile,
                failed,
            )
            raise RuntimeError(
                f"Package failed gold-reference validation ({benchmark_profile}): "
                f"{failed[0].name} expected {failed[0].expected}, got {failed[0].actual}",
            )

        summary = {
            "job_name": job_name,
            "total_assets": len(exported_objects),
            "asset_types": {
                t: sum(1 for o in exported_objects if o["objectType"] == t)
                for t in sorted({o["objectType"] for o in exported_objects})
            },
            "output_zip": str(output_zip_path),
            "output_zip_size_bytes": output_zip_path.stat().st_size,
            "checksum_validated": ok,
            "benchmark_profile": benchmark_profile,
            "benchmark_validated": benchmark_result.passed,
            "iics_import_instructions": "Admin → Import → Upload ZIP → Select objects → Import",
        }
        (self.output_dir / "generation_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        self.logger.info(
            "Generation complete. objects=%d zip=%d bytes path=%s",
            len(exported_objects), output_zip_path.stat().st_size, output_zip_path,
        )
        return summary

    def generate_single_session_packages(self) -> list[dict[str, Any]]:
        """
        Generate one IICS import zip per mapping, matching gold single-session exports.

        Each zip uses Explore path ``/Explore/RPA_PC_Modernization/Custom_SDE_SupplyChain``.
        """
        single_dir = self.output_dir / "single_session"
        single_dir.mkdir(parents=True, exist_ok=True)
        summaries: list[dict[str, Any]] = []

        for json_file in sorted(self.parsed_json_dir.glob("*.json")):
            if json_file.name.startswith("."):
                continue
            with open(json_file, encoding="utf-8") as fh:
                parsed = json.load(fh)
            for folder_data in parsed.get("folders", []):
                _ensure_reusable_transformations(
                    folder_data, json_file.name, self.remediated_xml_dir,
                )
                iics_folder = self.FOLDER_NAME
                for mapping in folder_data.get("mappings", []):
                    m_name = mapping["mapping_name"]
                    shell_cfg = SINGLE_SESSION_REFERENCE_SHELLS.get(m_name)
                    ref_path = (
                        _resolve_reference_shell_path(shell_cfg, self.project_root)
                        if shell_cfg else None
                    )
                    reference_shell = (
                        _slim_reference_shell(
                            _load_reference_shell(ref_path),
                            m_name,
                        )
                        if ref_path is not None else None
                    )
                    job_name = f"{m_name}-{int(time.time() * 1000)}"
                    summary = self._build_single_session_package(
                        folder_data=folder_data,
                        mapping=mapping,
                        pc_folder=iics_folder,
                        job_name=job_name,
                        output_zip_path=single_dir / f"{job_name}.zip",
                        reference_shell=reference_shell,
                        shell_config=shell_cfg,
                    )
                    summaries.append(summary)
                    time.sleep(0.002)

        summary_path = single_dir / "generation_summary.json"
        summary_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
        self.logger.info(
            "Single-session generation complete. packages=%d dir=%s",
            len(summaries), single_dir,
        )
        return summaries

    def _build_single_session_package(
        self,
        *,
        folder_data: dict,
        mapping: dict,
        pc_folder: str,
        job_name: str,
        output_zip_path: Path,
        reference_shell: dict[str, Any] | None = None,
        shell_config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        m_name = mapping["mapping_name"]
        folder_path = f"/Explore/{self.PROJECT_NAME}/{pc_folder}"

        project_guid = _new_guid()
        folder_guid = _new_guid()
        conn_guid = (
            reference_shell["primary_conn_guid"]
            if reference_shell else _new_guid()
        )
        agent_group_guid = (
            reference_shell["agent_group_guid"]
            if reference_shell else _new_guid()
        )
        flat_file_conn_guid: str | None = None
        if reference_shell and m_name.startswith("SDE_"):
            for obj in reference_shell.get("exported_objects") or []:
                if (
                    obj.get("objectType") == "Connection"
                    and obj.get("objectName") == SDE_FLAT_FILE_CONNECTION
                ):
                    flat_file_conn_guid = obj.get("objectGuid")
                    break
        dtemplate_guid = _new_guid()
        mtt_frs_guid = _new_guid()

        zip_contents: dict[str, bytes] = {}
        zip_contents[f"Explore/{self.PROJECT_NAME}.Project.json"] = \
            _build_project_json(self.PROJECT_NAME, project_guid).encode("utf-8")
        zip_contents[f"Explore/{self.PROJECT_NAME}/{pc_folder}.Folder.json"] = \
            _build_folder_json(pc_folder, folder_guid, self.PROJECT_NAME, project_guid).encode("utf-8")
        if reference_shell:
            zip_contents.update(reference_shell["sys_entries"])
        else:
            zip_contents[f"SYS/{self.AGENT_GROUP_NAME}.AgentGroup.zip"] = \
                _build_agent_group_zip(self.AGENT_GROUP_NAME, agent_group_guid)
            gold_conn = self.GOLD_CONNECTION_NAME
            zip_contents[f"SYS/{gold_conn}.Connection.zip"] = \
                _build_connection_zip(
                    gold_conn, conn_guid,
                    agent_group_guid, self.ORG_ID, self.AGENT_ID,
                )

        used_mapplets = _collect_used_mapplet_names(mapping)
        dmapplet_name_map = dict(shell_config.get("dmapplet_name_map") or {}) if shell_config else {}
        effective_skip_dmapplets = set(shell_config.get("skip_dmapplets") or []) if shell_config else set()
        all_mapplet_names = sorted(set(used_mapplets))

        sessions = folder_data.get("sessions", [])
        session = next(
            (s for s in sessions if s.get("mapping_name") == m_name or s.get("session_name") == m_name),
            sessions[0] if sessions else None,
        )
        workflows = folder_data.get("workflows", [])
        workflow = next(
            (w for w in workflows if w.get("workflow_name") == m_name),
            workflows[0] if workflows else None,
        )

        sequence_objects: list[dict] = []
        seq_guids: dict[str, str] = {}
        for seq_name, seq_tx in _collect_sequence_generators_for_session(session, folder_data):
            seq_guid = _new_guid()
            seq_guids[seq_name] = seq_guid
            seq_path = f"Explore/{self.PROJECT_NAME}/{pc_folder}/{seq_name}.SequenceGenerator.zip"
            zip_contents[seq_path] = _build_sequence_generator_zip(seq_name, seq_guid, seq_tx)
            sequence_objects.append({
                "objectGuid": seq_guid,
                "objectName": seq_name,
                "objectType": "SequenceGenerator",
                "path": folder_path,
                "providerName": None,
                "metadata": _meta_with_ctx(
                    _repo_handle(), [],
                    "Re-usable Sequence Generator pushed from PC to ICS",
                    "JSON", "VALID", _CONTEXT_ATTR,
                ),
            })

        seq_guid_replacements = _sequence_guid_replacements(
            reference_shell, shell_config, seq_guids,
        )

        mapplet_guids: dict[str, str] = {}
        dmapplet_objects: list[dict] = []
        ref_dmapplet_by_target = (
            _invert_name_map(dict(shell_config.get("dmapplet_name_map") or {}))
            if shell_config else {}
        )
        ref_dmapplet_entries = (
            reference_shell.get("dmapplet_entries") or {}
            if reference_shell else {}
        )
        for mp_name in all_mapplet_names:
            if mp_name in effective_skip_dmapplets:
                continue
            mapplet_def = _lookup_mapplet(folder_data, mp_name)
            mp_guid = _new_guid()
            mapplet_guids[mp_name] = mp_guid
            mp_path = f"Explore/{self.PROJECT_NAME}/{pc_folder}/{mp_name}.DMAPPLET.zip"
            ref_name = ref_dmapplet_by_target.get(mp_name) or mp_name
            ref_bytes = ref_dmapplet_entries.get(ref_name or "")
            dmapplet_replacements = {
                ref_name: mp_name,
                f"{ref_name}_preview.jpg": f"{mp_name}_preview.jpg",
                **_shell_text_replacement_dict(shell_config),
                **seq_guid_replacements,
            }
            if ref_bytes and mapplet_def and shell_config.get("native_graph_mapplets", True):
                preview_replacements = {
                    ref_name: mp_name,
                    f"{ref_name}_preview.jpg": f"{mp_name}_preview.jpg",
                }
                zip_contents[mp_path] = _graft_native_imf_into_reference_zip(
                    ref_bytes,
                    native_imf=_build_dmapplet_bin(mapplet_def, folder_data),
                    replacements=preview_replacements,
                    template_member="mappletTemplate.json",
                    target_name=mp_name,
                )
            elif ref_bytes:
                zip_contents[mp_path] = _rewrite_reference_dmapplet_zip(
                    ref_bytes,
                    replacements=dmapplet_replacements,
                    target_name=mp_name,
                    target_guid=None,
                )
            elif mapplet_def:
                zip_contents[mp_path] = _build_dmapplet_zip(mapplet_def, folder_data, mp_guid)
            else:
                continue
            mp_refs: list[str] = []
            doc_state = "VALID"
            if mp_name.startswith("mplt_BC_") or "mplt_BC" in mp_name:
                mp_refs = [conn_guid]
                doc_state = "INVALID"
            elif mp_name == "MPLT_EMPLOYEE_INS_REJ":
                mp_refs = [conn_guid]
            elif ref_bytes and seq_guid_replacements:
                mp_refs = _reference_dmapplet_sequence_ref_guids(ref_bytes, dmapplet_replacements)
            dmapplet_objects.append({
                "objectGuid": mp_guid,
                "objectName": mp_name,
                "objectType": "DMAPPLET",
                "path": folder_path,
                "providerName": None,
                "metadata": _meta_with_ctx(
                    _repo_handle(), mp_refs, f"Mapplet pushed from PC to ICS : {mp_name}",
                    "JSON", doc_state, _CONTEXT_ATTR,
                ),
            })

        dt_path = f"Explore/{self.PROJECT_NAME}/{pc_folder}/{m_name}.DTEMPLATE.zip"
        shell_replacements: dict[str, str] = {}
        dtemplate_deps = [mapplet_guids[n] for n in used_mapplets if n in mapplet_guids]
        if reference_shell and reference_shell.get("dtemplate_entry") and shell_config and shell_config.get("native_graph_dtemplate", True):
            shell_replacements = _build_reference_text_replacements(
                reference_shell,
                shell_config,
                target_mapping_name=m_name,
                project_name=self.PROJECT_NAME,
                folder_name=pc_folder,
                dtemplate_guid=dtemplate_guid,
                mtt_frs_guid=mtt_frs_guid,
                mapplet_guids=mapplet_guids,
                taskflow_guid=None,
                seq_guids=seq_guids,
            )
            zip_contents[dt_path] = _graft_native_imf_into_reference_zip(
                reference_shell["dtemplate_entry"],
                native_imf=_build_bin(mapping, folder_data, mapplet_guids=mapplet_guids),
                replacements=shell_replacements,
                template_member="mappingTemplate.json",
                target_name=m_name,
                target_guid=dtemplate_guid,
                mapplet_ref_guids=dtemplate_deps,
                set_asset_frs_guid=True,
            )
        else:
            zip_contents[dt_path] = _build_dtemplate_zip(
                mapping, folder_data, dtemplate_guid, mapplet_guids=mapplet_guids,
            )
        dtemplate_obj = {
            "objectGuid": dtemplate_guid,
            "objectName": m_name,
            "objectType": "DTEMPLATE",
            "path": folder_path,
            "providerName": None,
            "metadata": _meta_with_ctx(
                _repo_handle(), dtemplate_deps,
                f"Mapping pushed from PC to ICS : {m_name}",
                "JSON", "VALID", _CONTEXT_ATTR,
            ),
        }

        connections = {
            self.GOLD_CONNECTION_NAME: conn_guid,
            self.CONNECTION_PARAM: conn_guid,
        }
        if m_name.startswith("SDE_"):
            connections[self.GOLD_TARGET_CONN_PARAM] = conn_guid
            if flat_file_conn_guid:
                connections[SDE_FLAT_FILE_CONNECTION] = flat_file_conn_guid
        mtt_path = f"Explore/{self.PROJECT_NAME}/{pc_folder}/{m_name}.MTT.zip"
        if reference_shell and reference_shell.get("mtt_entry") and shell_config:
            if not shell_replacements:
                shell_replacements = _build_reference_text_replacements(
                    reference_shell,
                    shell_config,
                    target_mapping_name=m_name,
                    project_name=self.PROJECT_NAME,
                    folder_name=pc_folder,
                    dtemplate_guid=dtemplate_guid,
                    mtt_frs_guid=mtt_frs_guid,
                    mapplet_guids=mapplet_guids,
                    taskflow_guid=None,
                    seq_guids=seq_guids,
                )
            zip_contents[mtt_path] = _rewrite_reference_mtt_zip(
                reference_shell["mtt_entry"],
                replacements=shell_replacements,
                target_name=m_name,
                mtt_frs_guid=mtt_frs_guid,
                dtemplate_guid=dtemplate_guid,
            )
        else:
            zip_contents[mtt_path] = _build_mtt_zip(
                session, mtt_frs_guid, dtemplate_guid,
                agent_group_guid, connections, folder_data, m_name,
                mapping=mapping, seq_guids=seq_guids,
            )
        mtt_refs = [dtemplate_guid, conn_guid, agent_group_guid]
        if flat_file_conn_guid:
            mtt_refs = [dtemplate_guid, conn_guid, flat_file_conn_guid, agent_group_guid]
        mtt_refs.extend(seq_guids.values())
        mtt_obj = {
            "objectGuid": mtt_frs_guid,
            "objectName": m_name,
            "objectType": "MTT",
            "path": folder_path,
            "providerName": None,
            "metadata": _meta_with_ctx(
                _repo_handle(),
                mtt_refs,
                f"Session pushed from PC to ICS : {m_name}",
                "JSON", "VALID", _CONTEXT_ATTR,
            ),
        }

        taskflow_objects: list[dict] = []
        if workflow:
            from datetime import datetime
            tf_name = m_name
            tf_guid = _new_guid()
            now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.") + \
                f"{datetime.utcnow().microsecond // 1000:03d}Z"
            entry_id = f"{_h()}-gt-{abs(hash(tf_name)) % 99999999}-{now_str}::tf.xml"
            tf_path = f"Explore/{self.PROJECT_NAME}/{pc_folder}/{tf_name}.TASKFLOW.xml"
            if reference_shell and reference_shell.get("taskflow_entry") and shell_config:
                tf_replacements = _build_reference_text_replacements(
                    reference_shell,
                    shell_config,
                    target_mapping_name=m_name,
                    project_name=self.PROJECT_NAME,
                    folder_name=pc_folder,
                    dtemplate_guid=dtemplate_guid,
                    mtt_frs_guid=mtt_frs_guid,
                    mapplet_guids=mapplet_guids,
                    taskflow_guid=tf_guid,
                    seq_guids=seq_guids,
                )
                tf_text = reference_shell["taskflow_entry"].decode("utf-8")
                for old, new in _ordered_replacement_items(tf_replacements):
                    tf_text = tf_text.replace(old, new)
                zip_contents[tf_path] = tf_text.encode("utf-8")
            else:
                zip_contents[tf_path] = _build_workflow_taskflow_xml(
                    workflow, [(m_name, mtt_frs_guid)], tf_guid, entry_id,
                ).encode("utf-8")
            taskflow_objects.append({
                "objectGuid": tf_guid,
                "objectName": tf_name,
                "objectType": "TASKFLOW",
                "path": folder_path,
                "providerName": None,
                "metadata": _meta_with_ctx(
                    entry_id, [mtt_frs_guid],
                    "These workflows are created from the Workflow Generation Wizard.",
                    "application/json; charset=utf-8", "VALID", None,
                    model_version={"major": 1, "minor": 0},
                ),
            })

        project_obj = {
            "objectGuid": project_guid,
            "objectName": self.PROJECT_NAME,
            "objectType": "Project",
            "path": "/Explore",
            "providerName": None,
            "metadata": _meta_with_ctx(None, [], "Migrated project from PowerCenter", "Binary", "COMPLETE", []),
        }
        folder_obj = {
            "objectGuid": folder_guid,
            "objectName": pc_folder,
            "objectType": "Folder",
            "path": f"/Explore/{self.PROJECT_NAME}",
            "providerName": None,
            "metadata": _meta_with_ctx(None, [], None, "Binary", "COMPLETE", []),
        }
        conn_obj = {
            "objectGuid": conn_guid,
            "objectName": self.GOLD_CONNECTION_NAME,
            "objectType": "Connection",
            "path": "/SYS",
            "providerName": None,
            "metadata": _meta_with_ctx(
                _repo_handle(), [agent_group_guid], None, "JSON", "COMPLETE", _CONTEXT_ATTR,
            ),
        }
        agent_obj = {
            "objectGuid": agent_group_guid,
            "objectName": self.AGENT_GROUP_NAME,
            "objectType": "AgentGroup",
            "path": "/SYS",
            "providerName": None,
            "metadata": _meta_with_ctx(_repo_handle(), [], None, "JSON", "VALID", _CONTEXT_ATTR),
        }

        if reference_shell and shell_config:
            exported_objects = _merge_manifest_from_reference(
                reference_shell["exported_objects"],
                mapping_name=m_name,
                folder_path=folder_path,
                pc_folder=pc_folder,
                project_obj=project_obj,
                folder_obj=folder_obj,
                dtemplate_obj=dtemplate_obj,
                mtt_obj=mtt_obj,
                taskflow_objects=taskflow_objects,
                dmapplet_objects=dmapplet_objects,
                sequence_objects=sequence_objects,
                skip_dmapplets=effective_skip_dmapplets,
                dmapplet_name_map=dict(shell_config.get("dmapplet_name_map") or {}),
            )
        else:
            exported_objects = _order_single_session_exported_objects(
                mapping_name=m_name,
                dtemplate_obj=dtemplate_obj,
                folder_obj=folder_obj,
                project_obj=project_obj,
                conn_obj=conn_obj,
                mtt_obj=mtt_obj,
                taskflow_objects=taskflow_objects,
                dmapplet_objects=dmapplet_objects,
                sequence_objects=sequence_objects,
                agent_obj=agent_obj,
            )
        folder_import_assets = _count_folder_import_assets(
            exported_objects, folder_path, pc_folder,
        )

        manifest = {
            "name": job_name,
            "sourceOrgId": self.ORG_ID,
            "sourceOrgName": self.ORG_NAME,
            "exportedObjects": exported_objects,
        }
        manifest_bytes = json.dumps(manifest, indent=2).encode("utf-8")
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["objectPath", "objectName", "objectType", "id"])
        for obj in exported_objects:
            writer.writerow([obj["path"], obj["objectName"], obj["objectType"], obj["objectGuid"]])
        csv_filename = f"ContentsofExportPackage_{job_name}.csv"
        csv_bytes = csv_buf.getvalue().encode("utf-8")

        checksums: dict[str, str] = {}
        with zipfile.ZipFile(output_zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            zout.writestr("exportMetadata.v2.json", manifest_bytes)
            checksums["exportMetadata.v2.json"] = _sha256_bytes(manifest_bytes)
            zout.writestr(csv_filename, csv_bytes)
            for rel_path, content in sorted(zip_contents.items()):
                zout.writestr(rel_path, content)
                checksums[rel_path] = sha256_hex(content)
            zout.writestr("exportPackage.chksum", build_checksum_file(checksums))

        ok, chk_errors = validate_zip_checksums(output_zip_path)
        if not ok:
            raise RuntimeError(
                f"Single-session package failed checksum validation: {chk_errors[0]}",
            )

        return {
            "job_name": job_name,
            "mapping_name": m_name,
            "folder_name": pc_folder,
            "folder_import_assets": folder_import_assets,
            "total_assets": len(exported_objects),
            "reference_shell": reference_shell["reference_path"] if reference_shell else None,
            "output_zip": str(output_zip_path),
            "output_zip_size_bytes": output_zip_path.stat().st_size,
            "checksum_validated": ok,
        }
