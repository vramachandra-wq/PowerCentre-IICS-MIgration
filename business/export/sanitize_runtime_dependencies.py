"""
Sanitize IDMC export packages for client delivery.

Keeps Explore assets intact and replaces source-org Connection / Runtime Environment
artifacts with neutral placeholders for IICS import mapping.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONNECTION_NAME = "Oracle_Connection"
DEFAULT_AGENT_GROUP_NAME = "Secure_Agent_Group"


def _stable_frs_guid(label: str) -> str:
    digest = hashlib.sha256(label.encode("utf-8")).digest()
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(alphabet[b % len(alphabet)] for b in digest[:22])


def _replace_text(value: str, replacements: dict[str, str]) -> str:
    updated = value
    for before, after in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if before:
            updated = updated.replace(before, after)
    return updated


def _replace_bytes(content: bytes, replacements: dict[str, str]) -> bytes:
    try:
        return _replace_text(content.decode("utf-8"), replacements).encode("utf-8")
    except UnicodeDecodeError:
        return content


def _rewrite_nested_zip(content: bytes, replacements: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source_zip:
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as target_zip:
            for member in source_zip.namelist():
                member_bytes = source_zip.read(member)
                if member.endswith((".bin", ".json", ".meta", ".xml")):
                    member_bytes = _replace_bytes(member_bytes, replacements)
                target_zip.writestr(member, member_bytes)
    return buffer.getvalue()


def _build_generic_connection_zip(
    connection_name: str,
    connection_guid: str,
    agent_guid: str,
) -> bytes:
    payload = [
        {
            "@type": "connection",
            "id": "@1",
            "name": connection_name,
            "description": (
                "Placeholder Oracle connection. Map to the client target connection during IICS import."
            ),
            "runtimeEnvironmentId": f"@{agent_guid}",
            "instanceDisplayName": "Oracle",
            "host": "placeholder-host",
            "database": "orcl",
            "codepage": "UTF-8",
            "adjustedJdbcHostName": "placeholder-host",
            "type": "Oracle",
            "baseType": "Oracle",
            "port": 1521,
            "password": "********",
            "username": "placeholder-user",
            "majorUpdateTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "timeout": 60,
            "connParams": {"oracleSubType": "oracleonpremise", "agentGroupId": agent_guid},
            "internal": False,
            "federatedId": connection_guid,
            "retryNetworkError": False,
            "metadataBrowsable": True,
            "connectorStatus": "ACTIVE",
        }
    ]
    meta = [{"@type": "objectRef", "id": "@1", "type": "connection"}]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("connection.json", json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
        zf.writestr("metadata.meta", json.dumps(meta, separators=(",", ":"), ensure_ascii=False))
    return buffer.getvalue()


def _build_generic_agent_group_zip(agent_group_name: str, agent_guid: str) -> bytes:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    payload = [
        {
            "@type": "runtimeEnvironment",
            "id": "@1",
            "name": agent_group_name,
            "isSystemAgentGroup": False,
            "isShared": False,
            "federatedId": agent_guid,
            "createTimeUTC": now,
            "updateTimeUTC": now,
        }
    ]
    meta = [{"@type": "objectRef", "id": "@1", "type": "runtimeEnvironment"}]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "runtimeEnvironment.json",
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False),
        )
        zf.writestr("metadata.meta", json.dumps(meta, separators=(",", ":"), ensure_ascii=False))
    return buffer.getvalue()


def _rewrite_export_metadata(
    metadata: dict[str, Any],
    *,
    connection_name: str,
    connection_guid: str,
    agent_group_name: str,
    agent_guid: str,
    replacements: dict[str, str],
) -> dict[str, Any]:
    kept: list[dict[str, Any]] = []
    for obj in metadata.get("exportedObjects", []):
        if obj.get("objectType") in {"Connection", "AgentGroup"}:
            continue
        kept.append(json.loads(_replace_text(json.dumps(obj), replacements)))

    kept.append(
        {
            "objectGuid": connection_guid,
            "objectName": connection_name,
            "objectType": "Connection",
            "path": "/SYS",
            "providerName": None,
            "metadata": {
                "repoInfo": {"repoHandle": connection_guid},
                "dependents": [agent_guid],
                "additionalInfo": {"contentType": "JSON", "documentState": "COMPLETE"},
            },
        }
    )
    kept.append(
        {
            "objectGuid": agent_guid,
            "objectName": agent_group_name,
            "objectType": "AgentGroup",
            "path": "/SYS",
            "providerName": None,
            "metadata": {
                "repoInfo": {"repoHandle": agent_guid},
                "additionalInfo": {"contentType": "JSON", "documentState": "VALID"},
            },
        }
    )
    metadata["exportedObjects"] = kept
    return metadata


def _rewrite_contents_csv(
    content: bytes,
    *,
    replacements: dict[str, str],
    connection_name: str,
    connection_guid: str,
    agent_group_name: str,
    agent_guid: str,
) -> bytes:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or ["objectPath", "objectName", "objectType", "id"]
    rows: list[dict[str, str]] = []
    for row in reader:
        if (row.get("objectType") or "").strip() in {"Connection", "AgentGroup"}:
            continue
        rows.append(
            {
                key: _replace_text((value or ""), replacements)
                for key, value in row.items()
            }
        )
    rows.append(
        {
            "objectPath": "/SYS",
            "objectName": connection_name,
            "objectType": "Connection",
            "id": connection_guid,
        }
    )
    rows.append(
        {
            "objectPath": "/SYS",
            "objectName": agent_group_name,
            "objectType": "AgentGroup",
            "id": agent_guid,
        }
    )
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def sanitize_export_runtime_dependencies(
    input_zip: str | Path,
    output_zip: str | Path,
    *,
    connection_name: str = DEFAULT_CONNECTION_NAME,
    agent_group_name: str = DEFAULT_AGENT_GROUP_NAME,
) -> Path:
    """Preserve Explore assets and collapse SYS runtime dependencies to placeholders."""

    input_path = Path(input_zip)
    output_path = Path(output_zip)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    connection_guid = _stable_frs_guid(f"connection:{connection_name}")
    agent_guid = _stable_frs_guid(f"agent:{agent_group_name}")

    with zipfile.ZipFile(input_path) as source_zip:
        metadata = json.loads(source_zip.read("exportMetadata.v2.json").decode("utf-8"))
        objects = metadata.get("exportedObjects", [])
        replacements: dict[str, str] = {}
        for obj in objects:
            if obj.get("objectType") == "Connection":
                guid = obj.get("objectGuid") or ""
                name = obj.get("objectName") or ""
                if guid:
                    replacements[guid] = connection_guid
                if name:
                    replacements[name] = connection_name
            if obj.get("objectType") == "AgentGroup":
                guid = obj.get("objectGuid") or ""
                name = obj.get("objectName") or ""
                if guid:
                    replacements[guid] = agent_guid
                if name:
                    replacements[name] = agent_group_name

        rewritten_members: dict[str, bytes] = {}
        for member in source_zip.namelist():
            if member.startswith("SYS/") and (
                member.endswith(".Connection.zip") or member.endswith(".AgentGroup.zip")
            ):
                continue
            content = source_zip.read(member)
            if member.endswith((".DTEMPLATE.zip", ".MTT.zip", ".DMAPPLET.zip")):
                content = _rewrite_nested_zip(content, replacements)
            elif member == "exportMetadata.v2.json" or member == "exportPackage.chksum":
                continue
            elif member.startswith("ContentsofExportPackage_") and member.endswith(".csv"):
                content = _rewrite_contents_csv(
                    content,
                    replacements=replacements,
                    connection_name=connection_name,
                    connection_guid=connection_guid,
                    agent_group_name=agent_group_name,
                    agent_guid=agent_guid,
                )
            elif member.endswith((".TASKFLOW.xml", ".json")):
                content = _replace_bytes(content, replacements)
            rewritten_members[member] = content

        metadata = _rewrite_export_metadata(
            metadata,
            connection_name=connection_name,
            connection_guid=connection_guid,
            agent_group_name=agent_group_name,
            agent_guid=agent_guid,
            replacements=replacements,
        )
        rewritten_members["exportMetadata.v2.json"] = json.dumps(
            metadata, indent=2, ensure_ascii=False
        ).encode("utf-8")
        rewritten_members[f"SYS/{connection_name}.Connection.zip"] = _build_generic_connection_zip(
            connection_name, connection_guid, agent_guid
        )
        rewritten_members[f"SYS/{agent_group_name}.AgentGroup.zip"] = _build_generic_agent_group_zip(
            agent_group_name, agent_guid
        )

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as target_zip:
        for member, content in sorted(rewritten_members.items()):
            target_zip.writestr(member, content)

    from business.iics.checksum_utils import rewrite_zip_checksums

    rewrite_zip_checksums(output_path, output_path)
    return output_path


def assert_no_foreign_runtime_names(
    package_zip: str | Path,
    *,
    allowed_connection_names: set[str] | None = None,
    allowed_agent_names: set[str] | None = None,
) -> None:
    allowed_connection_names = allowed_connection_names or {DEFAULT_CONNECTION_NAME}
    allowed_agent_names = allowed_agent_names or {DEFAULT_AGENT_GROUP_NAME}
    with zipfile.ZipFile(package_zip) as package:
        metadata = json.loads(package.read("exportMetadata.v2.json").decode("utf-8"))
        connections = {
            obj.get("objectName")
            for obj in metadata.get("exportedObjects", [])
            if obj.get("objectType") == "Connection"
        }
        agents = {
            obj.get("objectName")
            for obj in metadata.get("exportedObjects", [])
            if obj.get("objectType") == "AgentGroup"
        }
        sys_members = [name for name in package.namelist() if name.startswith("SYS/")]

    foreign_connections = connections - allowed_connection_names
    foreign_agents = agents - allowed_agent_names
    if foreign_connections or foreign_agents:
        raise ValueError(
            "Package still contains foreign runtime dependencies: "
            f"connections={sorted(c for c in foreign_connections if c)} "
            f"agents={sorted(a for a in foreign_agents if a)}"
        )
    unexpected_sys = [
        name
        for name in sys_members
        if not (
            any(name.endswith(f"{allowed}.Connection.zip") for allowed in allowed_connection_names)
            or any(name.endswith(f"{allowed}.AgentGroup.zip") for allowed in allowed_agent_names)
        )
    ]
    if unexpected_sys:
        raise ValueError(f"Unexpected SYS artifacts remain: {unexpected_sys}")
