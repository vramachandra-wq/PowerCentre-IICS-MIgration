import json
import unittest
import zipfile
import uuid
from pathlib import Path
from xml.etree import ElementTree as ET

from business.iics.iics_package_generator import IICSPackageGenerator


class IICSPackageGeneratorMultisessionTests(unittest.TestCase):
    def test_single_session_keeps_single_taskflow_shape(self) -> None:
        root = self._workspace_temp()
        parsed = root / "parsed"
        out = root / "out"
        parsed.mkdir(parents=True)
        self._write_parsed_json(parsed, ["s_LoadA"])

        summary = IICSPackageGenerator(parsed_json_dir=parsed, output_dir=out).generate()
        taskflows = self._taskflow_shapes(Path(summary["output_zip"]))

        self.assertEqual("Custom_Project_Export.zip", Path(summary["output_zip"]).name)
        self.assertEqual(1, len(taskflows))
        self.assertEqual(["s_LoadA"], taskflows[0]["services"])
        self.assertEqual([], taskflows[0]["containers"])

    def test_two_sessions_generate_one_parallel_workflow_taskflow(self) -> None:
        root = self._workspace_temp()
        parsed = root / "parsed"
        out = root / "out"
        parsed.mkdir(parents=True)
        self._write_parsed_json(parsed, ["s_LoadA", "s_LoadB"])

        summary = IICSPackageGenerator(parsed_json_dir=parsed, output_dir=out).generate()
        taskflows = self._taskflow_shapes(Path(summary["output_zip"]))

        self.assertEqual(1, len(taskflows))
        self.assertEqual(["s_LoadA", "s_LoadB"], taskflows[0]["services"])
        self.assertIn("parallel", taskflows[0]["containers"])
        self.assertEqual(2, taskflows[0]["containers"].count("exclusive"))
        self.assertEqual(0, taskflows[0]["duplicate_ids"])

    def test_three_sessions_generate_dynamic_parallel_branches(self) -> None:
        root = self._workspace_temp()
        parsed = root / "parsed"
        out = root / "out"
        parsed.mkdir(parents=True)
        self._write_parsed_json(parsed, ["s_LoadA", "s_LoadB", "s_LoadC"])

        summary = IICSPackageGenerator(parsed_json_dir=parsed, output_dir=out).generate()
        taskflows = self._taskflow_shapes(Path(summary["output_zip"]))

        self.assertEqual(1, len(taskflows))
        self.assertEqual(["s_LoadA", "s_LoadB", "s_LoadC"], taskflows[0]["services"])
        self.assertIn("parallel", taskflows[0]["containers"])
        self.assertEqual(3, taskflows[0]["containers"].count("exclusive"))
        self.assertEqual(0, taskflows[0]["duplicate_ids"])

    def test_invalid_duplicate_session_is_not_counted_as_multisession(self) -> None:
        root = self._workspace_temp()
        parsed = root / "parsed"
        out = root / "out"
        parsed.mkdir(parents=True)
        self._write_parsed_json(
            parsed,
            ["s_LoadA", "s_LoadA_Invalid"],
            invalid_sessions={"s_LoadA_Invalid"},
            workflow_links=[
                {"FROMTASK": "Start", "TOTASK": "s_LoadA", "CONDITION": ""},
                {"FROMTASK": "Start", "TOTASK": "s_LoadA_Invalid", "CONDITION": ""},
            ],
        )

        summary = IICSPackageGenerator(parsed_json_dir=parsed, output_dir=out).generate()
        taskflows = self._taskflow_shapes(Path(summary["output_zip"]))

        self.assertEqual(1, len(taskflows))
        self.assertEqual(["s_LoadA"], taskflows[0]["services"])
        self.assertEqual([], taskflows[0]["containers"])

    @staticmethod
    def _workspace_temp() -> Path:
        root = Path(".test_tmp") / f"iics_multisession_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=False)
        return root

    @staticmethod
    def _write_parsed_json(
        parsed_dir: Path,
        session_names: list[str],
        invalid_sessions: set[str] | None = None,
        workflow_links: list[dict[str, str]] | None = None,
    ) -> None:
        invalid_sessions = invalid_sessions or set()
        mappings = [IICSPackageGeneratorMultisessionTests._mapping(name) for name in session_names]
        sessions = [
            {
                "session_name": name,
                "mapping_name": name.replace("_Invalid", ""),
                "is_valid": "NO" if name in invalid_sessions else "YES",
                "reusable_flag": "YES",
                "attributes": {},
            }
            for name in session_names
        ]
        links = workflow_links or [{"FROMTASK": "Start", "TOTASK": name, "CONDITION": ""} for name in session_names]
        valid_mapping_names = []
        for session in sessions:
            mapping_name = session["mapping_name"]
            if mapping_name not in valid_mapping_names:
                valid_mapping_names.append(mapping_name)
        mappings = [IICSPackageGeneratorMultisessionTests._mapping(name) for name in valid_mapping_names]
        payload = {
            "file_name": "sample.XML",
            "repository": {"name": "REP"},
            "folders": [{
                "folder_name": "FOLDER",
                "repository_name": "REP",
                "sources": [IICSPackageGeneratorMultisessionTests._source()],
                "targets": [IICSPackageGeneratorMultisessionTests._target()],
                "mappings": mappings,
                "sessions": sessions,
                "workflows": [{
                    "workflow_name": "wf_Load",
                    "task_instances": (
                        [{"NAME": "Start", "TASKNAME": "Start", "TASKTYPE": "Start"}]
                        + [{"NAME": name, "TASKNAME": name, "TASKTYPE": "Session"} for name in session_names]
                    ),
                    "workflow_links": links,
                }],
            }],
        }
        (parsed_dir / "sample.json").write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def _mapping(name: str) -> dict:
        return {
            "mapping_name": name,
            "is_valid": "YES",
            "transformation_count": 0,
            "source_count": 1,
            "target_count": 1,
            "transformations": [],
        }

    @staticmethod
    def _source() -> dict:
        return {
            "source_name": "SRC_TABLE",
            "database_type": "Oracle",
            "owner_name": "OWNER",
            "columns": [{"column_name": "ID", "datatype": "number", "precision": "10", "scale": "0"}],
        }

    @staticmethod
    def _target() -> dict:
        return {
            "target_name": "TGT_TABLE",
            "database_type": "Oracle",
            "columns": [{"column_name": "ID", "datatype": "number", "precision": "10", "scale": "0"}],
        }

    @staticmethod
    def _taskflow_shapes(zip_path: Path) -> list[dict]:
        ns = {"tf": "http://schemas.active-endpoints.com/appmodules/screenflow/2010/10/avosScreenflow.xsd"}
        shapes = []
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if not name.endswith(".TASKFLOW.xml"):
                    continue
                root = ET.fromstring(zf.read(name))
                ids = [elem.attrib["id"] for elem in root.findall(".//*[@id]")]
                services = [
                    title.text
                    for service in root.findall(".//tf:service", ns)
                    for title in [service.find("tf:title", ns)]
                    if title is not None
                ]
                containers = [
                    container.attrib.get("type", "")
                    for container in root.findall(".//tf:container", ns)
                ]
                shapes.append({
                    "name": name,
                    "services": services,
                    "containers": containers,
                    "duplicate_ids": len(ids) - len(set(ids)),
                })
        return shapes


if __name__ == "__main__":
    unittest.main()
