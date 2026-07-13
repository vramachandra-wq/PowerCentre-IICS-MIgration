"""Generate review-only IDMC taskflow XML from workflow/session metadata."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from export.package_builder import GeneratedAsset, ReviewWorkflow, safe_name


class TaskflowGenerator:
    """Build taskflow XML files that preserve workflow -> session -> mapping links."""

    def generate(self, workflow: ReviewWorkflow, output_dir: Path) -> GeneratedAsset:
        """Generate one taskflow XML for a workflow."""

        output_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{safe_name(workflow.workflow_name)}.TASKFLOW.xml"
        path = output_dir / file_name

        root = ET.Element(
            "Taskflow",
            {
                "name": workflow.workflow_name,
                "repository": workflow.repository_name,
                "folder": workflow.folder_name,
                "sourceFile": workflow.file_name,
                "reviewOnly": "true",
            },
        )
        if workflow.server_name:
            ET.SubElement(root, "RuntimeEnvironment").text = workflow.server_name

        sessions = ET.SubElement(root, "Sessions")
        for index, session in enumerate(workflow.sessions, start=1):
            session_node = ET.SubElement(
                sessions,
                "Session",
                {
                    "order": str(index),
                    "name": session.session_name,
                    "mapping": session.mapping_name,
                    "mappingPackage": (
                        f"Explore/MappingPackages/{safe_name(workflow.workflow_name, max_length=36)}/"
                        f"{safe_name(session.session_name, max_length=36)}/"
                        f"{safe_name(session.mapping_name, max_length=36)}.MTT.zip"
                    ),
                },
            )
            ET.SubElement(session_node, "SourcePowerCenterFile").text = session.file_name

        ET.indent(root, space="  ")
        ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
        return GeneratedAsset(workflow.workflow_name, "", "", "Workflow", f"Explore/Taskflows/{file_name}")
