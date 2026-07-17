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
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from copy import deepcopy
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any

from business.iics.checksum_utils import build_checksum_file, sha256_hex, validate_zip_checksums


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

def _build_bin(mapping: dict, folder_data: dict) -> bytes:
    """
    Build bin/@2.bin content matching the exact IICS DTEMPLATE format.

    ID scheme:
      $$ID  = definition (integer, sequential)
      ##ID  = back-reference to a previously defined $$ID
    """
    c = _IdCounter()
    name = mapping["mapping_name"]

    sources = folder_data.get("sources", [])
    targets = folder_data.get("targets", [])
    txs     = mapping.get("transformations", [])
    sess    = next(
        (s for s in folder_data.get("sessions", []) if s.get("mapping_name") == name),
        folder_data.get("sessions", [{}])[0] if folder_data.get("sessions") else {},
    )
    attrs   = sess.get("attributes", {}) if sess else {}

    # Fixed annotation IDs
    ann1_id = c.next()   # 1 - body annotation
    ann2_id = c.next()   # 2 - TEMPLATE_SETTINGS
    ann_kv_id = c.next() # 3

    # Assign IDs for every transformation/group upfront so links can ref them
    # Layout: target, [expressions], source_qualifier
    # We need to assign group IDs first

    # --- collect target definitions ---
    target_defs = []
    for tgt in targets:
        tgt_tx_id  = c.next()
        tgt_grp_id = c.next()
        tgt_da_id  = c.next()   # dataAdapter
        col_data   = []
        for col in tgt.get("columns", []):
            fld_id  = c.next()
            adapt_id = c.next()
            ann_id   = c.next()
            col_data.append({"fld_id": fld_id, "adapt_id": adapt_id, "ann_id": ann_id,
                             "col": col})
        target_defs.append({
            "name": tgt["target_name"], "tx_id": tgt_tx_id,
            "grp_id": tgt_grp_id, "da_id": tgt_da_id, "cols": col_data,
        })

    # --- expression/pass-through transformations ---
    expr_defs = []
    for tx in txs:
        tx_id  = c.next()
        grp_id = c.next()
        ann_id = c.next()
        port_data = []
        for p in tx.get("ports", []):
            p_id  = c.next()
            p_ann = c.next()
            port_data.append({"p_id": p_id, "p_ann": p_ann, "port": p})
        expr_defs.append({
            "name": tx["transformation_name"],
            "type": tx["transformation_type"],
            "tx_id": tx_id, "grp_id": grp_id, "ann_id": ann_id,
            "ports": port_data,
        })

    # --- source qualifier(s) ---
    src_defs = []
    for src in sources:
        sq_id  = c.next()
        grp_id = c.next()
        da_id  = c.next()
        ann_id = c.next()
        obj_id = c.next()
        col_data = []
        for col in src.get("columns", []):
            f_id   = c.next()
            fa_id  = c.next()
            f_ann  = c.next()
            col_data.append({"f_id": f_id, "fa_id": fa_id, "f_ann": f_ann, "col": col})
        src_defs.append({
            "name": f"SQ_{src['source_name']}",
            "raw_name": src["source_name"],
            "sq_id": sq_id, "grp_id": grp_id, "da_id": da_id,
            "ann_id": ann_id, "obj_id": obj_id, "cols": col_data,
        })

    # connection parameter
    conn_name = "DBConnection_OLAP"
    param_id   = c.next()
    anon_id    = c.next()

    # session-property IDs
    sp_ids = {
        "Reject file directory": c.next(),
        "Reject filename":       c.next(),
        "Target load type":      c.next(),
        "Commit Interval":       c.next(),
    }

    # ── build links ──────────────────────────────────────────────────────────
    links = []
    link_id_counter = _IdCounter(c.next())  # continue from current

    def _make_link(from_grp, from_tx, from_class, to_grp, to_tx, to_class) -> dict:
        lid = link_id_counter.next()
        return {
            "$$ID": lid, "$$class": 4,
            "name": f"link_{lid}",
            "fromGroup":        {"##ID": from_grp, "$$class": 5},
            "fromTransformation":{"##ID": from_tx,  "$$class": from_class},
            "toGroup":          {"##ID": to_grp,   "$$class": 5},
            "toTransformation": {"##ID": to_tx,    "$$class": to_class},
        }

    # SQ → expr[0] (if any)
    if src_defs:
        sq = src_defs[0]
        if expr_defs:
            ex = expr_defs[0]
            links.append(_make_link(sq["grp_id"], sq["sq_id"], 6,
                                    ex["grp_id"], ex["tx_id"], 7))
            # chain expressions
            for i in range(len(expr_defs) - 1):
                links.append(_make_link(
                    expr_defs[i]["grp_id"], expr_defs[i]["tx_id"], 7,
                    expr_defs[i+1]["grp_id"], expr_defs[i+1]["tx_id"], 7,
                ))
            # last expr → target
            if target_defs:
                links.append(_make_link(
                    expr_defs[-1]["grp_id"], expr_defs[-1]["tx_id"], 7,
                    target_defs[0]["grp_id"], target_defs[0]["tx_id"], 8,
                ))
        elif target_defs:
            links.append(_make_link(sq["grp_id"], sq["sq_id"], 6,
                                    target_defs[0]["grp_id"], target_defs[0]["tx_id"], 8))

    # ── build parameters ─────────────────────────────────────────────────────
    parameters = [{
        "$$ID": param_id, "$$class": 9,
        "input": "true", "output": "false",
        "precision": 0, "scale": 0,
        "allowRuntimeOverride": "true",
        "expressionVariable": "false",
        "label": "",
        "name": conn_name,
        "anonymousType": {
            "$$ID": anon_id, "$$class": 11,
            "name": "", "isVisible": "false",
            "subType": "", "typeSystem": "Oracle", "connectionType": "Oracle",
        },
    }]

    # ── build transformations list ───────────────────────────────────────────
    transformations = []

    # targets first (matching client layout)
    for tdef in target_defs:
        tgt_name = tdef["name"]
        rules = []
        rule1_id = c.next()
        rule2_id = c.next()
        rules.append({"$$ID": rule1_id, "$$class": 21, "bulkRename": "false", "include": "true"})
        names_list = []
        for cinfo in tdef["cols"]:
            nm_id = c.next()
            names_list.append({
                "$$ID": nm_id, "$$class": 28,
                "inputName": cinfo["col"]["column_name"],
                "outputName": cinfo["col"]["column_name"].upper(),
            })
        rules.append({
            "$$ID": rule2_id, "$$class": 22,
            "bulkRename": "false", "include": "true",
            "fieldNamesStr": "", "names": names_list,
        })

        tgt_ann_id = c.next()
        fields = []
        for cinfo in tdef["cols"]:
            col = cinfo["col"]
            fields.append({
                "$$ID": cinfo["fld_id"], "$$class": 14,
                "annotations": [{"$$ID": cinfo["ann_id"], "$$class": 2, "body": ""}],
                "adapterField": {"##ID": cinfo["adapt_id"], "$$class": 15},
                "defaultValue": "",
                "ignoreComparison": "false", "ignoreNullInputs": "false",
                "isDefaultValueUpdated": "false",
                "name": col["column_name"].upper(),
                "platformType": {
                    "##SID": "smd:com.informatica.metadata.seed.platform.Platform.typesystem/string",
                    "$$class": 16,
                },
                "precision": int(col.get("precision") or 60),
                "scale": int(col.get("scale") or 0),
            })

        obj_id = c.next()
        obj_fields = []
        for cinfo in tdef["cols"]:
            col = cinfo["col"]
            prop1_id = c.next()
            prop2_id = c.next()
            obj_fields.append({
                "$$ID": cinfo["adapt_id"], "$$class": 15,
                "name": col["column_name"].upper(),
                "createable": "false", "externalId": "false",
                "fieldStatus": "UNDEFINED", "fieldType": "UNDEFINED",
                "filterable": "true", "foreignKey": "false", "generated": "false",
                "javaType": "", "key": "false", "label": "", "nativeName": "",
                "nativeType": _native(col.get("datatype", "varchar2")),
                "newField": "false", "nullable": "true", "original": "false",
                "passthroughPort": "false",
                "precision": int(col.get("precision") or 60),
                "scale": int(col.get("scale") or 0),
                "sfIdLookup": "false", "unique": "false", "updateable": "false",
                "properties": [
                    {"$$ID": prop1_id, "$$class": 30, "name": "parentObjectLabel", "value": tgt_name},
                    {"$$ID": prop2_id, "$$class": 30, "name": "parentLabel",       "value": tgt_name},
                ],
            })

        session_props = [
            {"$$ID": sp_ids["Reject file directory"], "$$class": 12,
             "name": "Reject file directory", "value": "$PMBadFileDir\\"},
            {"$$ID": sp_ids["Reject filename"], "$$class": 12,
             "name": "Reject filename", "value": f"{tgt_name.lower()}.bad"},
        ]

        transformations.append({
            "$$ID": tdef["tx_id"], "$$class": 8,
            "annotations": [{"$$ID": tgt_ann_id, "$$class": 2, "body": ""}],
            "augmented": "false", "createTime": "",
            "name": tgt_name,
            "groups": [{
                "$$ID": tdef["grp_id"], "$$class": 5,
                "input": "true", "name": "DefaultGroup", "output": "false",
                "rules": rules,
            }],
            "sessionProperties": session_props,
            "createTarget": "false", "fieldMappingMode": "MANUAL",
            "inputSorted": "false", "schemaProviderType": "SELECTED_OBJECT",
            "targetFieldsOrdered": "false",
            "updateColumns": [], "useLabels": "false", "useSequenceFields": "false",
            "fields": fields,
            "dataAdapter": {
                "$$ID": tdef["da_id"], "$$class": 13,
                "name": "", "codePage": "", "compatibleEngine": "",
                "connectionId": "",
                "connectionId$": {"##ID": param_id, "$$class": 9},
                "connectionSelectionType": "",
                "excludeDynamicFileNameField": "false",
                "fwConfigId": "", "multipleObject": "false",
                "objectType": "SINGLE", "typeSystem": "Oracle",
                "useDynamicFileName": "false",
                "object": {
                    "$$ID": obj_id, "$$class": 23,
                    "name": tgt_name, "customQuery": "",
                    "dbSchema": "", "label": tgt_name,
                    "objectName": "", "objectType": "", "parentPath": "",
                    "path": tgt_name, "retainMetadata": "false",
                    "fields": obj_fields,
                },
            },
        })

    # expression transformations
    for edef in expr_defs:
        ep_ann = c.next()
        ports_out = []
        for pinfo in edef["ports"]:
            p = pinfo["port"]
            ports_out.append({
                "$$ID": pinfo["p_id"], "$$class": 17,
                "annotations": [{"$$ID": pinfo["p_ann"], "$$class": 2, "body": ""}],
                "businessLabel": "", "datatype": "string",
                "description": "", "expression": p.get("expression", p["port_name"]),
                "expressionType": "EXPRESSION_RETURN",
                "label": p["port_name"],
                "name": p["port_name"],
                "nullable": "true",
                "portType": "INPUT_OUTPUT",
                "precision": int(p.get("precision") or 50),
                "scale": int(p.get("scale") or 0),
            })
        transformations.append({
            "$$ID": edef["tx_id"], "$$class": 7,
            "annotations": [{"$$ID": ep_ann, "$$class": 2, "body": ""}],
            "augmented": "false", "createTime": "",
            "name": edef["name"],
            "groups": [{
                "$$ID": edef["grp_id"], "$$class": 5,
                "input": "true", "name": "DefaultGroup", "output": "true",
                "rules": [{"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"}],
                "fields": ports_out,
            }],
        })

    # source qualifier(s)
    for sdef in src_defs:
        sq_ann = c.next()
        sq_fields = []
        for cinfo in sdef["cols"]:
            col = cinfo["col"]
            sq_fields.append({
                "$$ID": cinfo["f_id"], "$$class": 18,
                "annotations": [{"$$ID": cinfo["f_ann"], "$$class": 2, "body": ""}],
                "businessLabel": "", "datatype": "string",
                "description": "", "label": col["column_name"],
                "name": col["column_name"],
                "nullable": "true", "portType": "OUTPUT",
                "precision": int(col.get("precision") or 50),
                "scale": int(col.get("scale") or 0),
            })

        obj_fields_sq = []
        for cinfo in sdef["cols"]:
            col = cinfo["col"]
            pr1 = c.next(); pr2 = c.next()
            obj_fields_sq.append({
                "$$ID": cinfo["fa_id"], "$$class": 15,
                "name": col["column_name"],
                "createable": "false", "externalId": "false",
                "fieldStatus": "UNDEFINED", "fieldType": "UNDEFINED",
                "filterable": "true", "foreignKey": "false", "generated": "false",
                "javaType": "", "key": "false", "label": "", "nativeName": "",
                "nativeType": _native(col.get("datatype", "varchar2")),
                "newField": "false", "nullable": "true", "original": "false",
                "passthroughPort": "false",
                "precision": int(col.get("precision") or 50),
                "scale": int(col.get("scale") or 0),
                "sfIdLookup": "false", "unique": "false", "updateable": "false",
                "properties": [
                    {"$$ID": pr1, "$$class": 30, "name": "parentObjectLabel", "value": sdef["raw_name"]},
                    {"$$ID": pr2, "$$class": 30, "name": "parentLabel",       "value": sdef["raw_name"]},
                ],
            })

        custom_query = attrs.get("Sql Query", "")
        transformations.append({
            "$$ID": sdef["sq_id"], "$$class": 6,
            "annotations": [{"$$ID": sq_ann, "$$class": 2, "body": ""}],
            "augmented": "false", "createTime": "",
            "name": sdef["name"],
            "groups": [{
                "$$ID": sdef["grp_id"], "$$class": 5,
                "input": "false", "name": "DefaultGroup", "output": "true",
                "rules": [{"$$ID": c.next(), "$$class": 21, "bulkRename": "false", "include": "true"}],
                "fields": sq_fields,
            }],
            "dataAdapter": {
                "$$ID": sdef["da_id"], "$$class": 13,
                "name": "", "codePage": "", "compatibleEngine": "",
                "connectionId": "",
                "connectionId$": {"##ID": param_id, "$$class": 9},
                "connectionSelectionType": "",
                "excludeDynamicFileNameField": "false",
                "fwConfigId": "", "multipleObject": "false",
                "objectType": "SINGLE", "typeSystem": "Oracle",
                "useDynamicFileName": "false",
                "customQuery": custom_query,
                "object": {
                    "$$ID": sdef["obj_id"], "$$class": 23,
                    "name": sdef["raw_name"], "customQuery": custom_query,
                    "dbSchema": "", "label": sdef["raw_name"],
                    "objectName": "", "objectType": "", "parentPath": "",
                    "path": sdef["raw_name"], "retainMetadata": "false",
                    "fields": obj_fields_sq,
                },
            },
        })

    # ── assemble final content ────────────────────────────────────────────────
    content = {
        "$$IID": "stringIdentity:@2",
        "$$class": 1,
        "annotations": [
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
        ],
        "allowMaxFieldLength": "false",
        "bigIntConvertType": "",
        "documentType": "",
        "ecoSystem": "",
        "name": name,
        "specialCharacterSupport": "true",
        "templateOrigin": "",
        "links": links,
        "parameters": parameters,
        "transformations": transformations,
    }
    return json.dumps(
        {
            "content": content,
            "metadata": {
                "$$classInfo": {
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
                }
            },
        },
        separators=(",", ":"),
    ).encode("utf-8")


# ── PowerCenter XML Task builders (matches IICS import validation model) ────

def _resolve_remediated_xml(
    remediated_dir: Path,
    json_stem: str,
    mapping_name: str,
    fallback_xml_dir: Path | None = None,
) -> tuple[Path, str]:
    remediated_candidates = (f"{mapping_name}_remediated.xml", f"{json_stem}_remediated.xml")
    for candidate in remediated_candidates:
        path = remediated_dir / candidate
        if path.exists():
            return path, candidate

    if fallback_xml_dir is not None:
        source_candidates = (f"{mapping_name}.XML", f"{mapping_name}.xml", f"{json_stem}.XML", f"{json_stem}.xml")
        for candidate in source_candidates:
            path = fallback_xml_dir / candidate
            if path.exists():
                return path, candidate

    searched = [str(remediated_dir / candidate) for candidate in remediated_candidates]
    if fallback_xml_dir is not None:
        searched.extend(str(fallback_xml_dir / candidate) for candidate in source_candidates)
    raise FileNotFoundError(
        f"No remediated or source XML for mapping '{mapping_name}' (source={json_stem}). Searched: {searched}"
    )



def _xml_attrs(elem: ET.Element) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in elem.attrib.items()}


def _pc_port_from_field(field: ET.Element) -> dict[str, Any]:
    attrs = field.attrib
    port_name = attrs.get("NAME") or attrs.get("FIELDNAME") or ""
    return {
        "port_name": port_name,
        "port_type": attrs.get("PORTTYPE", ""),
        "datatype": attrs.get("DATATYPE", attrs.get("TYPE", "string")),
        "precision": attrs.get("PRECISION", "50"),
        "scale": attrs.get("SCALE", "0"),
        "expression": attrs.get("EXPRESSION") or attrs.get("DEFAULTVALUE") or port_name,
        "attributes": _xml_attrs(field),
    }


def _pc_transformation_from_xml(
    elem: ET.Element,
    *,
    name_prefix: str = "",
    origin: str,
) -> dict[str, Any]:
    raw_name = elem.attrib.get("NAME", "")
    tx_name = f"{name_prefix}__{raw_name}" if name_prefix else raw_name
    return {
        "transformation_name": tx_name,
        "original_transformation_name": raw_name,
        "transformation_type": elem.attrib.get("TYPE", "Expression"),
        "reusable_flag": elem.attrib.get("REUSABLE", ""),
        "conversion_origin": origin,
        "attributes": _xml_attrs(elem),
        "ports": [_pc_port_from_field(port) for port in elem.findall("TRANSFORMFIELD")],
    }


def _find_folder_for_mapping(root: ET.Element, mapping_name: str) -> ET.Element | None:
    for folder in root.iter("FOLDER"):
        for mapping in folder.findall("MAPPING"):
            if mapping.attrib.get("NAME") == mapping_name:
                return folder
    return None


def _enrich_mapping_from_remediated_xml(
    mapping: dict,
    folder_data: dict,
    remediated_path: Path,
) -> tuple[dict, dict[str, Any]]:
    """Flatten remediated XML mapplet/reusable logic into the generated IICS template."""

    mapping_name = mapping["mapping_name"]
    enriched = deepcopy(mapping)
    root = ET.parse(remediated_path).getroot()
    folder = _find_folder_for_mapping(root, mapping_name)
    if folder is None:
        raise ValueError(f"Mapping {mapping_name!r} not found in remediated XML {remediated_path}")

    mapplet_defs = {m.attrib.get("NAME", ""): m for m in folder.findall("MAPPLET")}
    folder_reusable = {
        tx.attrib.get("NAME", ""): tx
        for tx in folder.findall("TRANSFORMATION")
        if tx.attrib.get("NAME")
    }
    mapping_elem = next(
        m for m in folder.findall("MAPPING")
        if m.attrib.get("NAME") == mapping_name
    )

    existing_names = {
        tx.get("transformation_name", "")
        for tx in enriched.get("transformations", [])
    }
    generated_names = set(existing_names)
    flattened: list[dict[str, Any]] = []
    documented_equivalents: list[dict[str, str]] = []
    unsupported_or_review: list[dict[str, str]] = []

    def append_if_new(tx: dict[str, Any]) -> None:
        name = tx.get("transformation_name", "")
        if name and name not in generated_names:
            flattened.append(tx)
            generated_names.add(name)

    mapplet_instances = [
        inst for inst in mapping_elem.findall("INSTANCE")
        if inst.attrib.get("TYPE", "").upper() == "MAPPLET"
    ]
    for inst in mapplet_instances:
        mapplet_name = inst.attrib.get("TRANSFORMATION_NAME") or inst.attrib.get("NAME", "")
        mapplet = mapplet_defs.get(mapplet_name)
        if mapplet is None:
            unsupported_or_review.append({
                "object": mapplet_name,
                "type": "Mapplet",
                "reason": "Mapplet instance has no matching remediated XML definition.",
            })
            continue

        documented_equivalents.append({
            "object": mapplet_name,
            "type": "Mapplet",
            "equivalent": "Flattened into parent mapping template as explicit transformation components.",
        })
        prefix = f"MPLT_{mapplet_name}"
        for tx in mapplet.findall("TRANSFORMATION"):
            append_if_new(_pc_transformation_from_xml(tx, name_prefix=prefix, origin=f"mapplet:{mapplet_name}"))

        for nested_inst in mapplet.findall("INSTANCE"):
            reusable_name = nested_inst.attrib.get("TRANSFORMATION_NAME", "")
            reusable = folder_reusable.get(reusable_name)
            if reusable is not None:
                append_if_new(_pc_transformation_from_xml(
                    reusable,
                    name_prefix=f"REUSABLE_{mapplet_name}",
                    origin=f"reusable:{reusable_name}",
                ))

    for inst in mapping_elem.findall("INSTANCE"):
        reusable_name = inst.attrib.get("TRANSFORMATION_NAME", "")
        if inst.attrib.get("REUSABLE", "").upper() == "YES" and reusable_name in folder_reusable:
            append_if_new(_pc_transformation_from_xml(
                folder_reusable[reusable_name],
                name_prefix="REUSABLE",
                origin=f"reusable:{reusable_name}",
            ))

    enriched.setdefault("transformations", [])
    enriched["transformations"].extend(flattened)
    enriched["transformation_count"] = len(enriched["transformations"])
    enriched["functional_enrichment"] = {
        "source": str(remediated_path),
        "flattened_component_count": len(flattened),
        "flattened_components": [
            {
                "name": tx.get("transformation_name", ""),
                "originalName": tx.get("original_transformation_name", ""),
                "type": tx.get("transformation_type", ""),
                "origin": tx.get("conversion_origin", ""),
                "portCount": len(tx.get("ports", [])),
            }
            for tx in flattened
        ],
    }

    coverage = {
        "mapping": mapping_name,
        "remediatedXml": remediated_path.name,
        "status": "FUNCTIONAL_COVERAGE_ENRICHED",
        "sourceCounts": {
            "mappings": len(folder.findall("MAPPING")),
            "mapplets": len(mapplet_defs),
            "folderReusableTransformations": len(folder_reusable),
            "mappingTransformations": len(mapping_elem.findall("TRANSFORMATION")),
            "mappingInstances": len(mapping_elem.findall("INSTANCE")),
            "mappingConnectors": len(mapping_elem.findall("CONNECTOR")),
        },
        "generatedCounts": {
            "templateTransformations": len(enriched.get("transformations", [])),
            "flattenedMappletOrReusableTransformations": len(flattened),
            "parsedConnectors": len(enriched.get("connectors", [])),
            "parsedInstances": len(enriched.get("instances", [])),
        },
        "documentedEquivalents": documented_equivalents,
        "unsupportedOrNeedsReview": unsupported_or_review,
        "notes": [
            "Mapplet and reusable transformation definitions are read from remediated XML during ZIP generation.",
            "Mapplet internals are flattened into the parent DTEMPLATE to avoid silently missing reusable PowerCenter logic.",
            "Original remediated XML is included in the ZIP as source-of-truth evidence for functional validation.",
        ],
    }
    return enriched, coverage

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


def _build_dtemplate_zip(mapping: dict, folder_data: dict, guid: str) -> bytes:
    name = mapping["mapping_name"]
    bin_bytes = _build_bin(mapping, folder_data)

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
        "references": [],
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


# ── MTT builder ──────────────────────────────────────────────────────────────

def _build_mtt_zip(
    session: dict | None,
    mtt_frs_guid: str,
    dtemplate_guid: str,
    agent_group_guid: str,
    conn_guids: dict[str, str],
    folder_data: dict,
    mapping_name: str,
) -> bytes:
    if session is None:
        session = {"session_name": mapping_name, "mapping_name": mapping_name, "attributes": {}}
    name   = session.get("session_name", mapping_name)
    attrs  = session.get("attributes", {})
    sources = folder_data.get("sources", [])
    targets = folder_data.get("targets", [])

    conn_name = "DBConnection_OLAP"
    conn_guid = conn_guids.get(conn_name) or conn_guids.get("DBConnection_OLAP_Oracle", "")

    # Build parameters array (one per source qualifier)
    parameters = []
    for src in sources:
        sq_name = f"SQ_{src['source_name']}"
        po_name = sq_name.replace("_", "-")
        param_id = abs(hash(f"{name}_{sq_name}")) % (2 ** 31)
        src_obj_name = f"DUMMY_{sq_name}"
        src_obj_label = src["source_name"]

        src_field_list = []
        for col in src.get("columns", []):
            src_field_list.append({
                "name":      col["column_name"],
                "nativeType": _native(col.get("datatype", "varchar2")),
                "precision": int(col.get("precision") or 50),
                "scale":     int(col.get("scale") or 0),
                "nullable":  True,
            })

        parameters.append({
            "@type": "mtTaskParameter",
            "id": param_id,
            "name": f"${sq_name}$",
            "type": "SOURCE",
            "label": sq_name,
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
                "isCustomQueryRetainMetaData": "true",
                "flags": "SUPPORTS_MULTI_SCHEMA",
                "originalPath": sq_name,
            },
            "sourceConnectionId": f"@{conn_guid}",
            "sourceObject": src_obj_name,
            "newFlatFile": False,
            "newObject": False,
            "showBusinessNames": True,
            "naturalOrder": True,
            "truncateTarget": False,
            "bulkApiDBTarget": False,
            "srcFFAttrs": {
                "@type": "flatFileAttrs", "id": param_id + 1,
                "delimiter": "|", "textQualifier": "NONE",
                "escapeChar": "", "headerLineNo": 1, "firstDataRow": 2,
                "rowDelimiter": 0, "consecutiveDelimiter": False,
                "multiDelimitersAsAnd": False, "firstDataRowAsHeader": False,
                "codePage": "", "customRowDelimiter": "",
                "headerAndDataDelimiter": 0,
            },
            "customFuncCfg": {
                "@type": "customFuncConfig", "id": -1,
                "connections": [], "inputMap": [], "outputFields": [],
            },
            "targetRefsV2": {},
        })

    for tgt in targets:
        tgt_name = tgt.get("target_name") or tgt.get("name", "")
        if not tgt_name:
            continue
        param_id = abs(hash(f"{name}_TGT_{tgt_name}")) % (2 ** 31)
        parameters.append({
            "@type": "mtTaskParameter",
            "id": param_id,
            "name": f"${tgt_name}$",
            "type": "TARGET",
            "label": tgt_name,
            "objectName": tgt_name,
            "objectLabel": tgt_name,
            "operationType": "Insert",
            "truncateTarget": False,
            "bulkApiDBTarget": True,
            "newFlatFile": False,
            "newObject": False,
            "naturalOrder": True,
            "showBusinessNames": True,
            "targetConnectionId": f"@{conn_guid}",
            "targetObject": tgt_name,
            "targetObjectLabel": tgt_name,
            "runtimeParameterData": {
                "@type": "mtTaskRuntimeParameterData",
                "isConnectionRuntimeParameter": True,
                "isObjectRuntimeParameter": False,
                "connectionParameterName": conn_name,
            },
            "targetRefsV2": {},
        })

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
        {"@type": "taskProperty", "name": "parameterFileDir",  "currentValue": "",
         "type": "STRING", "label": "label.parameterFileDir",  "required": False},
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
        "parameters": parameters,
    }]

    metadata_meta = [{"@type": "objectRef", "id": "@1", "type": "mtTask"}]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mtTask.json",   json.dumps(mt_task, separators=(",", ":")))
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
    dependencies = ""
    branch_xml = ""
    for mtt_name, mtt_frs_guid in tasks:
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
                              </serviceInput>
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
                  <link id="{start_link}" targetId="{parallel_id}"/>
               </start>
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


def _valid_workflow_tasks(folder_data: dict, workflow: dict, mtt_by_name: dict[str, str]) -> list[tuple[str, str]]:
    sessions = folder_data.get("sessions", [])
    valid_sessions = {
        session.get("session_name"): session
        for session in sessions
        if session.get("session_name") and str(session.get("is_valid", "YES")).upper() != "NO"
    }
    task_names = [
        task.get("TASKNAME") or task.get("NAME")
        for task in workflow.get("task_instances", [])
        if str(task.get("TASKTYPE", "")).lower() == "session"
    ]
    if not task_names:
        task_names = [session.get("session_name") for session in sessions]

    tasks: list[tuple[str, str]] = []
    seen: set[str] = set()
    for task_name in task_names:
        session = valid_sessions.get(task_name)
        if not session:
            continue
        mtt_name = session.get("mapping_name") or task_name
        mtt_guid = mtt_by_name.get(mtt_name)
        if not mtt_guid or mtt_name in seen:
            continue
        seen.add(mtt_name)
        tasks.append((mtt_name, mtt_guid))
    return tasks


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


# ── Main generator ────────────────────────────────────────────────────────────

class IICSPackageGenerator:
    """Generate a complete IICS import package from all parsed PC XML files."""

    PROJECT_NAME     = "BIAINFADEV2_FLEX"
    FOLDER_NAME      = "Custom_Project"
    CONNECTION_NAME  = "DataWarehouse_PA"
    CONNECTION_PARAM = "DBConnection_OLAP"
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
        logger: logging.Logger | None = None,
    ) -> None:
        self.parsed_json_dir = Path(parsed_json_dir)
        self.remediated_xml_dir = Path(remediated_xml_dir)
        self.output_dir      = Path(output_dir)
        self.output_zip_name = output_zip_name
        self.logger = logger or logging.getLogger(__name__)

    def generate(self) -> dict[str, Any]:
        self.logger.info("IICS Package Generator starting. source=%s", self.parsed_json_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        json_files = sorted(self.parsed_json_dir.glob("*.json"))
        self.logger.info("Found %d parsed JSON files.", len(json_files))

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
        coverage_manifests: list[dict[str, Any]] = []
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
        for json_file in json_files:
            if json_file.name.startswith("."):
                continue
            self.logger.info("Processing %s ...", json_file.name)
            with open(json_file, encoding="utf-8") as fh:
                parsed = json.load(fh)

            for folder_data in parsed.get("folders", []):
                mtt_by_name: dict[str, str] = {}
                # ── Per mapping (all placed in Custom_Project) ────────────────
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
                    remediated_path, remediated_name = _resolve_remediated_xml(
                        self.remediated_xml_dir,
                        json_file.stem,
                        mapping["mapping_name"],
                        Path("input_xml"),
                    )
                    enriched_mapping, coverage = _enrich_mapping_from_remediated_xml(
                        mapping,
                        folder_data,
                        remediated_path,
                    )
                    enriched_mapping["mapping_name"] = m_name
                    coverage["generatedMappingName"] = m_name
                    coverage_manifests.append(coverage)
                    evidence_prefix = f"PCXML/{self.FOLDER_NAME}"
                    zip_contents[f"{evidence_prefix}/{remediated_name}"] = remediated_path.read_bytes()
                    zip_contents[
                        f"{evidence_prefix}/{m_name}_functional_coverage.json"
                    ] = json.dumps(coverage, indent=2).encode("utf-8")

                    # DTEMPLATE (native CDI mapping enriched from remediated XML)
                    dt_handle = _repo_handle()
                    dtemplate_zip = _build_dtemplate_zip(enriched_mapping, folder_data, dtemplate_guid)
                    dt_path = f"Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}/{m_name}.DTEMPLATE.zip"
                    zip_contents[dt_path] = dtemplate_zip
                    dtemplate_obj = {
                        "objectGuid": dtemplate_guid,
                        "objectName": m_name,
                        "objectType": "DTEMPLATE",
                        "path": folder_path,
                        "providerName": None,
                        "metadata": _meta_with_ctx(
                            dt_handle, [], f"Mapping pushed from PC to ICS : {m_name}",
                            "JSON", "VALID", _CONTEXT_ATTR,
                        ),
                    }

                    mtt_handle = _repo_handle()
                    mtt_zip = _build_mtt_zip(
                        session, mtt_frs_guid, dtemplate_guid,
                        agent_group_guid, connections, folder_data, m_name,
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

                    # Teammate export order: DTEMPLATE -> MTT -> TASKFLOW
                    mapping_objects.append(dtemplate_obj)
                    mapping_objects.append(mtt_obj)

                for workflow in folder_data.get("workflows", []):
                    tasks = _valid_workflow_tasks(folder_data, workflow, mtt_by_name)
                    if not tasks:
                        continue
                    tf_name = tasks[0][0] if len(tasks) == 1 else workflow.get("workflow_name", tasks[0][0])
                    tf_guid = _new_guid()
                    from datetime import datetime
                    now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.") + \
                        f"{datetime.utcnow().microsecond // 1000:03d}Z"
                    entry_id = f"{_h()}-gt-{abs(hash(tf_name)) % 99999999}-{now_str}::tf.xml"
                    tf_xml = _build_workflow_taskflow_xml(workflow, tasks, tf_guid, entry_id)
                    tf_path = f"Explore/{self.PROJECT_NAME}/{self.FOLDER_NAME}/{tf_name}.TASKFLOW.xml"
                    zip_contents[tf_path] = tf_xml.encode("utf-8")
                    mapping_objects.append({
                        "objectGuid": tf_guid,
                        "objectName": tf_name,
                        "objectType": "TASKFLOW",
                        "path": folder_path,
                        "providerName": None,
                        "metadata": _meta_with_ctx(
                            entry_id,
                            [agent_group_guid, *[mtt_guid for _, mtt_guid in tasks]],
                            "These workflows are created from the Workflow Generation Wizard.",
                            "application/json; charset=utf-8",
                            "VALID",
                            None,
                            model_version={"major": 1, "minor": 0},
                        ),
                    })

        package_coverage = {
            "status": "FUNCTIONAL_COVERAGE_ENRICHED",
            "coverageManifests": coverage_manifests,
            "totalMappings": len(coverage_manifests),
            "totalFlattenedComponents": sum(
                item.get("generatedCounts", {}).get("flattenedMappletOrReusableTransformations", 0)
                for item in coverage_manifests
            ),
        }
        zip_contents[f"PCXML/{self.FOLDER_NAME}/functional_coverage_manifest.json"] = json.dumps(
            package_coverage, indent=2
        ).encode("utf-8")

        # Manifest order follows the single-taskflow client export shape.
        mtt_objects = [obj for obj in mapping_objects if obj["objectType"] == "MTT"]
        taskflow_objects = [obj for obj in mapping_objects if obj["objectType"] == "TASKFLOW"]
        dtemplate_objects = [obj for obj in mapping_objects if obj["objectType"] == "DTEMPLATE"]
        exported_objects = [project_obj, conn_obj, agent_obj] + mtt_objects + [folder_obj] + taskflow_objects + dtemplate_objects
        job_name = f"job-{int(time.time() * 1000)}"
        manifest = {
            "name": job_name,
            "sourceOrgId": self.ORG_ID,
            "sourceOrgName": self.ORG_NAME,
            "exportedObjects": exported_objects,
        }
        manifest_bytes = json.dumps(manifest, indent=2).replace("\n", "\r\n").encode("utf-8")

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
            "functional_coverage": package_coverage,
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
