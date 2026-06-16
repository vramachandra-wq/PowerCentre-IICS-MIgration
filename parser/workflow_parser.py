from __future__ import annotations

from xml.etree.ElementTree import Element

try:
    from parser.models import SessionMetadata, SqlOverrideMetadata, WorkflowMetadata
except ModuleNotFoundError:
    from models import SessionMetadata, SqlOverrideMetadata, WorkflowMetadata


class WorkflowParser:
    """Parses sessions, workflows, task instances, workflow links, and session SQL overrides."""

    SQL_OVERRIDE_NAMES = {"Sql Query", "SQL Query"}

    def parse_sessions(self, folder: Element) -> list[SessionMetadata]:
        return [self._parse_session(session) for session in folder.findall("SESSION")]

    def parse_workflows(self, folder: Element) -> list[WorkflowMetadata]:
        return [self._parse_workflow(workflow) for workflow in folder.findall("WORKFLOW")]

    def _parse_session(self, session: Element) -> SessionMetadata:
        session_name = session.attrib.get("NAME", "")
        attributes = {
            item.attrib.get("NAME", ""): item.attrib.get("VALUE", "")
            for item in session.iter("ATTRIBUTE")
            if item.attrib.get("NAME")
        }
        sql_overrides = [
            SqlOverrideMetadata(
                context_type="SESSION",
                context_name=session_name,
                parent_name=session.attrib.get("MAPPINGNAME", ""),
                sql_query=item.attrib.get("VALUE", ""),
            )
            for item in session.iter("ATTRIBUTE")
            if item.attrib.get("NAME") in self.SQL_OVERRIDE_NAMES and item.attrib.get("VALUE", "")
        ]
        return SessionMetadata(
            session_name=session_name,
            mapping_name=session.attrib.get("MAPPINGNAME", ""),
            is_valid=session.attrib.get("ISVALID", ""),
            reusable_flag=session.attrib.get("REUSABLE", ""),
            attributes=attributes,
            sql_overrides=sql_overrides,
        )

    @staticmethod
    def _parse_workflow(workflow: Element) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_name=workflow.attrib.get("NAME", ""),
            is_valid=workflow.attrib.get("ISVALID", ""),
            is_enabled=workflow.attrib.get("ISENABLED", ""),
            server_name=workflow.attrib.get("SERVERNAME", ""),
            task_instances=[dict(item.attrib) for item in workflow.findall("TASKINSTANCE")],
            workflow_links=[dict(item.attrib) for item in workflow.findall("WORKFLOWLINK")],
        )
