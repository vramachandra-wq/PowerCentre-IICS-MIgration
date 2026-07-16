"""
Repair IDMC export DTEMPLATE/MTT artifacts that would fail IICS IMF import.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path


def repair_dtemplate_zip(source_bytes: bytes, mapping_name: str | None = None) -> bytes:
    """Sync fileRecord size/name with embedded bin/*.bin payloads."""

    with zipfile.ZipFile(io.BytesIO(source_bytes)) as source_zip:
        members = {name: source_zip.read(name) for name in source_zip.namelist()}

    if "fileRecord.json" not in members:
        return source_bytes

    if mapping_name is None and "mappingTemplate.json" in members:
        template = json.loads(members["mappingTemplate.json"].decode("utf-8"))
        if template:
            mapping_name = template[0].get("name")

    payload = json.loads(members["fileRecord.json"].decode("utf-8"))
    if not isinstance(payload, list):
        raise ValueError("fileRecord.json must be a JSON list")

    bin_members = {
        name: content
        for name, content in members.items()
        if name.startswith("bin/") and name.endswith(".bin")
    }
    for record in payload:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("id", "")).lstrip("@")
        bin_member = next(
            (name for name in bin_members if name.endswith(f"/@{record_id}.bin")),
            None,
        )
        if not bin_member:
            continue
        bin_content = bin_members[bin_member]
        if mapping_name and record.get("type") == "IMFOBJECT":
            record["name"] = mapping_name
        record["size"] = len(bin_content)

        if record.get("type") == "IMFOBJECT" and mapping_name:
            try:
                bin_payload = json.loads(bin_content.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                bin_payload = None
            if isinstance(bin_payload, dict) and isinstance(bin_payload.get("content"), dict):
                bin_payload["content"]["name"] = mapping_name
                members[bin_member] = json.dumps(
                    bin_payload, separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
                record["size"] = len(members[bin_member])

    members["fileRecord.json"] = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as repaired_zip:
        for name, content in members.items():
            repaired_zip.writestr(name, content)
    return output.getvalue()


def repair_mtt_zip(source_bytes: bytes, mapping_name: str) -> bytes:
    """Normalize MTT metadata for a renamed mapping."""

    with zipfile.ZipFile(io.BytesIO(source_bytes)) as source_zip:
        members = {name: source_zip.read(name) for name in source_zip.namelist()}

    if "mtTask.json" not in members:
        return source_bytes

    payload = json.loads(members["mtTask.json"].decode("utf-8"))
    if payload:
        payload[0]["name"] = mapping_name
        payload[0]["description"] = (
            f"Sample-backed mapping task wrapper for remediated XML : {mapping_name}"
        )
        payload[0]["shortDescription"] = f"Session pushed from PC to ICS : {mapping_name}"[:60]
    members["mtTask.json"] = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as repaired_zip:
        for name, content in members.items():
            repaired_zip.writestr(name, content)
    return output.getvalue()


def repair_export_package(input_zip: str | Path, output_zip: str | Path) -> Path:
    """Repair all DTEMPLATE/MTT members inside an IDMC export package."""

    input_path = Path(input_zip)
    output_path = Path(output_zip)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(input_path) as source_zip:
        with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as target_zip:
            for member in source_zip.namelist():
                content = source_zip.read(member)
                if member.endswith(".DTEMPLATE.zip"):
                    mapping_name = Path(member).name.removesuffix(".DTEMPLATE.zip")
                    content = repair_dtemplate_zip(content, mapping_name)
                elif member.endswith(".MTT.zip"):
                    mapping_name = Path(member).name.removesuffix(".MTT.zip")
                    content = repair_mtt_zip(content, mapping_name)
                target_zip.writestr(member, content)

    from business.iics.checksum_utils import rewrite_zip_checksums

    rewrite_zip_checksums(output_path, output_path)
    return output_path
