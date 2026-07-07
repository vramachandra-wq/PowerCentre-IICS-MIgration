"""
Module: automation/ai/issue_definition_loader.py

Purpose:
    This module supports AI recommendation and evaluation support for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the AI recommendation and evaluation support area and connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from automation.evaluation_matrix import ReportRepository
from automation.ai.recommendation_models import FailureRecord


@dataclass(frozen=True)
class IssueDefinition:
    """One AI-only issue definition from the uploaded text file."""

    error_name: str
    priority: str
    why_it_occurs: str
    how_to_fix: str


class AIRecommendationIssueLoader:
    """Loads AI-only migration issue definitions and detects matching XML context."""

    FILE_NAMES = [
        "ai_recommendation_issues.txt",
        "pc to iics  errors 1.txt",
    ]
    PRIORITIES = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}

    def __init__(self, repository: ReportRepository, configured_path: str | Path = "") -> None:
        """
        Executes the __init__ workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                repository (object): Value supplied by the caller and used by the workflow.
                configured_path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.repository = repository
        self.configured_path = Path(configured_path) if configured_path else None

    def build_failures(self, migration_context: dict[str, object]) -> list[FailureRecord]:
        # These rows are recommendation-only; they are never written to remediation rules.
        """
        Executes the build_failures workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                migration_context (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        definitions = self.load()
        if not definitions:
            return []
        contexts = self._metadata_contexts()
        if not contexts:
            contexts = [self._placeholder_context(0)]

        failures: list[FailureRecord] = []
        for index, definition in enumerate(definitions):
            matches = self._matching_contexts(definition, contexts)
            if matches:
                # XML matches use real workflow/session/mapping/transformation metadata.
                for context in matches:
                    failures.append(self._failure(definition, context, migration_context, detected=True))
            else:
                # Non-matches still need a row, but only hierarchy/assets may be synthetic.
                failures.append(
                    self._failure(definition, self._placeholder_context(index), migration_context, detected=False)
                )
        return failures

    def load(self) -> list[IssueDefinition]:
        """
        Executes the load workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        path = self._definition_path()
        if not path:
            return []
        return self.parse(path.read_text(encoding="utf-8-sig"))

    @classmethod
    def parse(cls, content: str) -> list[IssueDefinition]:
        """Parses repeated Error Name/Priority/Why/How blocks from a plain text upload."""
        blocks = re.split(r"\n\s*\n+", content.strip())
        definitions: list[IssueDefinition] = []
        buffer = ""
        for block in blocks:
            if "Error Name" in block:
                if buffer:
                    parsed = cls._parse_block(buffer)
                    if parsed:
                        definitions.append(parsed)
                buffer = block
                continue
            buffer = f"{buffer}\n{block}" if buffer else block
        if buffer:
            parsed = cls._parse_block(buffer)
            if parsed:
                definitions.append(parsed)
        return definitions

    @classmethod
    def _parse_block(cls, block: str) -> IssueDefinition | None:
        """
        Executes the _parse_block workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                block (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        normalized = re.sub(r"^\s*\d+\.", "", block.strip())
        error_match = re.search(r"Error Name\s*=\s*(.+)", normalized, flags=re.IGNORECASE)
        why_match = re.search(r"Why it Occurs\s*=\s*(.+)", normalized, flags=re.IGNORECASE)
        fix_match = re.search(r"How to Fix\s*=\s*(.+)", normalized, flags=re.IGNORECASE)
        priority_match = re.search(r"\((Critical|High|Medium|Low)\)", normalized, flags=re.IGNORECASE)
        if not error_match or not why_match or not fix_match:
            return None
        priority = cls.PRIORITIES.get((priority_match.group(1) if priority_match else "Medium").lower(), "Medium")
        return IssueDefinition(
            error_name=error_match.group(1).strip(),
            priority=priority,
            why_it_occurs=why_match.group(1).strip(),
            how_to_fix=fix_match.group(1).strip(),
        )

    def _definition_path(self) -> Path | None:
        # Prefer project-local files; use Downloads only for the default app repository.
        """
        Executes the _definition_path workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        candidates: list[Path] = []
        if self.configured_path:
            candidates.append(self.configured_path)
        for name in self.FILE_NAMES:
            candidates.extend(
                [
                    self.repository.output_folder / name,
                    self.repository.reports_folder / name,
                    Path.cwd() / name,
                ]
            )
        if self._uses_default_repository():
            candidates.append(Path("D:/Download/pc to iics  errors 1.txt"))
        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def _uses_default_repository(self) -> bool:
        """
        Executes the _uses_default_repository workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        output = self.repository.output_folder
        return output == Path("output") or output.resolve() == (Path.cwd() / "output").resolve()

    def _metadata_contexts(self) -> list[dict[str, str]]:
        # Build the same hierarchy that is rendered in the recommendation table.
        """
        Executes the _metadata_contexts workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        workflows_by_file = {
            Path(row.get("file_name", "")).name: row.get("workflow_name", "")
            for row in self.repository.read_csv("metadata_tables/workflows.csv")
        }
        sessions_by_mapping = {
            row.get("mapping_name", ""): row.get("session_name", "")
            for row in self.repository.read_csv("metadata_tables/sessions.csv")
        }
        transformations_by_mapping: dict[str, list[dict[str, str]]] = {}
        for row in self.repository.read_csv("metadata_tables/transformations.csv"):
            transformations_by_mapping.setdefault(row.get("mapping_name", ""), []).append(row)

        contexts: list[dict[str, str]] = []
        for mapping in self.repository.read_csv("metadata_tables/mappings.csv"):
            mapping_name = mapping.get("mapping_name", "")
            file_name = Path(mapping.get("file_name", "")).name
            transformations = transformations_by_mapping.get(mapping_name) or [{}]
            for transformation in transformations:
                contexts.append(
                    {
                        "workflow": workflows_by_file.get(file_name, Path(file_name).stem),
                        "session": sessions_by_mapping.get(mapping_name, ""),
                        "mapping": mapping_name,
                        "transformation": transformation.get("transformation_name", ""),
                        "transformation_type": transformation.get("transformation_type", ""),
                        "source_file": file_name,
                    }
                )
        return contexts

    def _matching_contexts(
        self, definition: IssueDefinition, contexts: Iterable[dict[str, str]]
    ) -> list[dict[str, str]]:
        # Use broad issue tokens so uploaded business issue names can map to XML constructs.
        """
        Executes the _matching_contexts workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                definition (object): Value supplied by the caller and used by the workflow.
                contexts (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        issue_key = self._issue_key(definition.error_name)
        matches: list[dict[str, str]] = []
        for context in contexts:
            haystack = " ".join(
                [
                    context.get("transformation", ""),
                    context.get("transformation_type", ""),
                    context.get("mapping", ""),
                    self._xml_text(context.get("source_file", "")),
                ]
            ).lower()
            if self._is_match(issue_key, haystack):
                matches.append(context)
        return matches[:1]

    @staticmethod
    def _issue_key(error_name: str) -> str:
        """
        Executes the _issue_key workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                error_name (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        value = error_name.lower()
        if "sequence" in value:
            return "sequence"
        if "connection" in value:
            return "connection"
        if "incremental" in value or "cdc" in value:
            return "incremental"
        if "repository" in value and "metadata" in value:
            return "repository_metadata"
        return re.sub(r"[^a-z0-9]+", "_", value).strip("_")

    @staticmethod
    def _is_match(issue_key: str, haystack: str) -> bool:
        """
        Executes the _is_match workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                issue_key (object): Value supplied by the caller and used by the workflow.
                haystack (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if issue_key == "sequence":
            return "sequence" in haystack
        if issue_key == "connection":
            return any(token in haystack for token in ["connection", "connectstring", "cnxref"])
        if issue_key == "incremental":
            return any(token in haystack for token in ["incremental", "cdc", "change data", "update strategy"])
        return issue_key in haystack

    def _xml_text(self, file_name: str) -> str:
        """
        Executes the _xml_text workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                file_name (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not file_name:
            return ""
        for folder in [Path.cwd() / "input_xml", self.repository.output_folder / "input_xml"]:
            path = folder / file_name
            if path.exists():
                return path.read_text(encoding="utf-8", errors="ignore")
        return ""

    def _failure(
        self,
        definition: IssueDefinition,
        context: dict[str, str],
        migration_context: dict[str, object],
        detected: bool,
    ) -> FailureRecord:
        """
        Executes the _failure workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                definition (object): Value supplied by the caller and used by the workflow.
                context (object): Value supplied by the caller and used by the workflow.
                migration_context (object): Value supplied by the caller and used by the workflow.
                detected (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        asset = self._asset_name(definition, context)
        # Store the uploaded priority in context so fallback generation preserves it.
        extended_context = {
            **migration_context,
            "defined_priority": definition.priority,
            "issue_definition_source": "ai_recommendation_issue_file",
            "xml_detected": detected,
        }
        return FailureRecord(
            workflow=context.get("workflow", ""),
            session=context.get("session", ""),
            mapping=context.get("mapping", ""),
            transformation=context.get("transformation", ""),
            object_name=asset,
            failure_type=definition.error_name,
            validation_rule="AI-RECOMMENDATION-ONLY",
            validation_message=definition.why_it_occurs,
            auto_fix_status="AI Recommendation Only",
            severity=definition.priority.upper(),
            error_details=f"How to Fix: {definition.how_to_fix}",
            root_cause=definition.why_it_occurs,
            rule_based_recommendation=definition.how_to_fix,
            source_file=context.get("source_file", ""),
            migration_context=extended_context,
        )

    @staticmethod
    def _asset_name(definition: IssueDefinition, context: dict[str, str]) -> str:
        """
        Executes the _asset_name workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                definition (object): Value supplied by the caller and used by the workflow.
                context (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        transformation = context.get("transformation", "")
        mapping = context.get("mapping", "")
        if transformation:
            return transformation
        if mapping:
            return mapping
        token = re.sub(r"[^A-Za-z0-9]+", "_", definition.error_name).strip("_")
        return f"{token}_Asset"

    @staticmethod
    def _placeholder_context(index: int) -> dict[str, str]:
        """
        Executes the _placeholder_context workflow for AI recommendation and evaluation support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                index (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that connects validation findings, prompt/model execution, fallback recommendations, and report-ready AI outputs. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        suffix = index + 1
        return {
            "workflow": f"WF_Migration_Assessment_{suffix}",
            "session": f"S_Migration_Task_{suffix}",
            "mapping": f"M_Migration_Object_{suffix}",
            "transformation": f"EXP_Migration_Check_{suffix}",
            "transformation_type": "Expression",
            "source_file": "",
        }
