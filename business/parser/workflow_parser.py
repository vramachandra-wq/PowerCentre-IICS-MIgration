"""
Support workflow parser for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

try:
    from data.models.mapping_model import SessionMetadata, SqlOverrideMetadata, WorkflowMetadata
except ModuleNotFoundError:
    from models import SessionMetadata, SqlOverrideMetadata, WorkflowMetadata


class WorkflowParser:
    """Parses migration metadata into application structures."""

    SQL_OVERRIDE_NAMES = {"Sql Query", "SQL Query"}

    def parse_sessions(self, folder: Element) -> list[SessionMetadata]:
        """Parse sessions using the provided folder."""

        return [self._parse_session(session) for session in folder.findall("SESSION")]

    def parse_workflows(self, folder: Element) -> list[WorkflowMetadata]:
        """Parse workflows using the provided folder."""

        return [self._parse_workflow(workflow) for workflow in folder.findall("WORKFLOW")]

    def _parse_session(self, session: Element) -> SessionMetadata:
        """Parse session using the provided session."""

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
        transformation_instances: list[dict[str, str]] = []
        for inst in session.findall("SESSTRANSFORMATIONINST"):
            entry = dict(inst.attrib)
            for attr in inst.findall("ATTRIBUTE"):
                name = attr.attrib.get("NAME", "")
                if name:
                    entry[name] = attr.attrib.get("VALUE", "")
            transformation_instances.append(entry)
        return SessionMetadata(
            session_name=session_name,
            mapping_name=session.attrib.get("MAPPINGNAME", ""),
            is_valid=session.attrib.get("ISVALID", ""),
            reusable_flag=session.attrib.get("REUSABLE", ""),
            attributes=attributes,
            sql_overrides=sql_overrides,
            transformation_instances=transformation_instances,
        )

    @staticmethod
    def _parse_workflow(workflow: Element) -> WorkflowMetadata:
        """Parse workflow using the provided workflow."""

        schedule = workflow.find("./SCHEDULER/SCHEDULEINFO")
        schedule_attrib = schedule.attrib if schedule is not None else {}
        return WorkflowMetadata(
            workflow_name=workflow.attrib.get("NAME", ""),
            is_valid=workflow.attrib.get("ISVALID", ""),
            is_enabled=workflow.attrib.get("ISENABLED", ""),
            server_name=workflow.attrib.get("SERVERNAME", ""),
            schedule_type=schedule_attrib.get("SCHEDULETYPE", ""),
            schedule_interval=schedule_attrib.get("INTERVAL", "")
            or schedule_attrib.get("REPEAT", "")
            or schedule_attrib.get("REPEATCOUNT", ""),
            schedule_timezone=schedule_attrib.get("TIMEZONE", ""),
            schedule_start_time=schedule_attrib.get("STARTTIME", "")
            or schedule_attrib.get("STARTDATE", ""),
            schedule_recurrence=schedule_attrib.get("RECURRING", "")
            or schedule_attrib.get("RECURRINGTYPE", ""),
            task_instances=[dict(item.attrib) for item in workflow.findall("TASKINSTANCE")],
            workflow_links=[dict(item.attrib) for item in workflow.findall("WORKFLOWLINK")],
        )
