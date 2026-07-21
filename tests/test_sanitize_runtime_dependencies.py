"""Tests for client-safe Connection / Runtime Environment sanitization."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from business.export.sanitize_runtime_dependencies import (
    DEFAULT_AGENT_GROUP_NAME,
    DEFAULT_CONNECTION_NAME,
    assert_no_foreign_runtime_names,
    sanitize_export_runtime_dependencies,
)


def _connection_zip(name: str, guid: str, agent_guid: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "connection.json",
            json.dumps(
                [
                    {
                        "@type": "connection",
                        "name": name,
                        "federatedId": guid,
                        "runtimeEnvironmentId": f"@{agent_guid}",
                        "host": "uslas0-scan11",
                        "username": "appsbi",
                    }
                ]
            ),
        )
        zf.writestr("metadata.meta", json.dumps([{"@type": "objectRef", "id": "@1", "type": "connection"}]))
    return buf.getvalue()


def _agent_zip(name: str, guid: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "runtimeEnvironment.json",
            json.dumps([{"@type": "runtimeEnvironment", "name": name, "federatedId": guid}]),
        )
        zf.writestr(
            "metadata.meta",
            json.dumps([{"@type": "objectRef", "id": "@1", "type": "runtimeEnvironment"}]),
        )
    return buf.getvalue()


def _mtt_zip(connection_guid: str, connection_name: str, agent_guid: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "mtTask.json",
            json.dumps(
                [
                    {
                        "@type": "mtTask",
                        "name": "SDE_ORA_JobDimension",
                        "runtimeEnvironmentId": f"@{agent_guid}",
                        "parameters": [
                            {
                                "sourceConnectionId": f"@{connection_guid}",
                                "uiProperties": {
                                    "logcnx": connection_name,
                                    "paramName": connection_name,
                                },
                            }
                        ],
                    }
                ]
            ),
        )
    return buf.getvalue()


class SanitizeRuntimeDependenciesTests(unittest.TestCase):
    def test_sanitize_collapses_foreign_connections_and_agents(self) -> None:
        package = io.BytesIO()
        with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "exportMetadata.v2.json",
                json.dumps(
                    {
                        "name": "job-1",
                        "exportedObjects": [
                            {
                                "objectGuid": "mtt1",
                                "objectName": "SDE_ORA_JobDimension",
                                "objectType": "MTT",
                                "path": "/Explore/P/F",
                            },
                            {
                                "objectGuid": "connJacobs",
                                "objectName": "Orcl_BI_Jacobs_HR2",
                                "objectType": "Connection",
                                "path": "/SYS",
                            },
                            {
                                "objectGuid": "agentLinux",
                                "objectName": "Linux_SecureAgentGroup",
                                "objectType": "AgentGroup",
                                "path": "/SYS",
                            },
                        ],
                    }
                ),
            )
            zf.writestr(
                "ContentsofExportPackage_job-1.csv",
                "objectPath,objectName,objectType,id\n"
                "/Explore/P/F,SDE_ORA_JobDimension,MTT,mtt1\n"
                "/SYS,Orcl_BI_Jacobs_HR2,Connection,connJacobs\n"
                "/SYS,Linux_SecureAgentGroup,AgentGroup,agentLinux\n",
            )
            zf.writestr(
                "Explore/P/F/SDE_ORA_JobDimension.MTT.zip",
                _mtt_zip("connJacobs", "Orcl_BI_Jacobs_HR2", "agentLinux"),
            )
            zf.writestr(
                "SYS/Orcl_BI_Jacobs_HR2.Connection.zip",
                _connection_zip("Orcl_BI_Jacobs_HR2", "connJacobs", "agentLinux"),
            )
            zf.writestr(
                "SYS/Linux_SecureAgentGroup.AgentGroup.zip",
                _agent_zip("Linux_SecureAgentGroup", "agentLinux"),
            )
            zf.writestr("exportPackage.chksum", "#\n")

        with tempfile.TemporaryDirectory() as tmp:
            input_zip = Path(tmp) / "in.zip"
            output_zip = Path(tmp) / "out.zip"
            input_zip.write_bytes(package.getvalue())
            sanitize_export_runtime_dependencies(input_zip, output_zip)
            assert_no_foreign_runtime_names(output_zip)

            with zipfile.ZipFile(output_zip) as zf:
                meta = json.loads(zf.read("exportMetadata.v2.json"))
                conn_names = [
                    o["objectName"] for o in meta["exportedObjects"] if o["objectType"] == "Connection"
                ]
                agent_names = [
                    o["objectName"] for o in meta["exportedObjects"] if o["objectType"] == "AgentGroup"
                ]
                self.assertEqual(conn_names, [DEFAULT_CONNECTION_NAME])
                self.assertEqual(agent_names, [DEFAULT_AGENT_GROUP_NAME])
                self.assertNotIn(
                    b"Orcl_BI_Jacobs_HR2",
                    zf.read("Explore/P/F/SDE_ORA_JobDimension.MTT.zip"),
                )


if __name__ == "__main__":
    unittest.main()
