"""
Module: business/parser/workflow_parser.py

Purpose:
    This module supports PowerCenter XML metadata parsing for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the PowerCenter XML metadata parsing area and extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from xml.etree.ElementTree import Element

try:
    from data.models.mapping_model import SessionMetadata, SqlOverrideMetadata, WorkflowMetadata
except ModuleNotFoundError:
    from models import SessionMetadata, SqlOverrideMetadata, WorkflowMetadata


class WorkflowParser:
    """Parses sessions, workflows, task instances, workflow links, and session SQL overrides."""

    SQL_OVERRIDE_NAMES = {"Sql Query", "SQL Query"}

    def parse_sessions(self, folder: Element) -> list[SessionMetadata]:
        """
        Executes the parse_sessions workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                folder (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return [self._parse_session(session) for session in folder.findall("SESSION")]

    def parse_workflows(self, folder: Element) -> list[WorkflowMetadata]:
        """
        Executes the parse_workflows workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                folder (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return [self._parse_workflow(workflow) for workflow in folder.findall("WORKFLOW")]

    def _parse_session(self, session: Element) -> SessionMetadata:
        """
        Executes the _parse_session workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                session (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the _parse_workflow workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                workflow (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
