"""
Module: business/parser/xml_explorer.py

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

import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable
from xml.etree.ElementTree import Element

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[1]))

try:
    import pandas as pd
except ModuleNotFoundError:  # pragma: no cover - local bootstrap fallback.
    pd = None

try:
    from common.utils.xml_utils import XmlLoader
except ModuleNotFoundError:
    from xml_loader import XmlLoader

from common.config.config import AppConfig


INFORMATICA_COMPONENT_TAGS = {
    "POWERMART",
    "REPOSITORY",
    "FOLDER",
    "SOURCE",
    "SOURCEFIELD",
    "TARGET",
    "TARGETFIELD",
    "MAPPING",
    "TRANSFORMATION",
    "TRANSFORMFIELD",
    "INSTANCE",
    "CONNECTOR",
    "SESSION",
    "WORKFLOW",
    "WORKLET",
    "TASK",
    "TASKINSTANCE",
    "CONFIG",
    "TABLEATTRIBUTE",
    "ATTRIBUTE",
    "MAPPLET",
}


@dataclass
class FolderSummary:
    """
    Represents the FolderSummary component in the PowerCenter XML metadata parsing area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    file_name: str
    repository_name: str
    folder_name: str
    sources: int
    targets: int
    mappings: int
    mapplets: int
    sessions: int
    workflows: int
    transformations: int


@dataclass
class MappingSummary:
    """
    Represents the MappingSummary component in the PowerCenter XML metadata parsing area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    file_name: str
    folder_name: str
    mapping_name: str
    is_valid: str
    transformations: int
    transformation_types: str
    instances: int
    connectors: int
    sources: int
    targets: int


@dataclass
class ComponentSummary:
    """
    Represents the ComponentSummary component in the PowerCenter XML metadata parsing area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    component_tag: str
    count: int
    sample_names: str


@dataclass
class ExplorationSummary:
    """
    Represents the ExplorationSummary component in the PowerCenter XML metadata parsing area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    file_count: int = 0
    tag_counts: Counter[str] = field(default_factory=Counter)
    component_counts: Counter[str] = field(default_factory=Counter)
    component_names: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    hierarchy_paths: Counter[str] = field(default_factory=Counter)
    folder_summary: list[FolderSummary] = field(default_factory=list)
    mapping_summary: list[MappingSummary] = field(default_factory=list)


class PowerCenterXmlExplorer:
    """Explores PowerCenter XML structure without extracting business metadata."""

    def __init__(self, config: AppConfig, logger) -> None:
        """
        Executes the __init__ workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                config (object): Value supplied by the caller and used by the workflow.
                logger (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.config = config
        self.logger = logger
        self.loader = XmlLoader()
        self.project_root = Path.cwd()
        self.xml_folder = self._resolve_path(config.paths.xml_folder)
        self.output_folder = self._resolve_path(config.paths.output_folder)
        self.output_folder.mkdir(parents=True, exist_ok=True)

    def explore_folder(self, print_hierarchy: bool = False) -> ExplorationSummary:
        """
        Executes the explore_folder workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                print_hierarchy (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        xml_files = sorted(self.xml_folder.glob("*.xml"))
        if not xml_files:
            self.logger.warning("No XML files found in %s", self.xml_folder)
            return ExplorationSummary()

        self.logger.info("Exploring %s PowerCenter XML file(s) from %s", len(xml_files), self.xml_folder)
        summary = ExplorationSummary()
        for xml_file in xml_files:
            file_summary = self._explore(xml_file)
            self._merge_summary(summary, file_summary)

        self._write_reports(summary)
        if print_hierarchy:
            self._print_hierarchy(summary)
        return summary

    def explore_file(self, xml_file: Path, print_hierarchy: bool = False) -> ExplorationSummary:
        """
        Executes the explore_file workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                xml_file (object): Value supplied by the caller and used by the workflow.
                print_hierarchy (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        xml_path = self._resolve_path(xml_file)
        summary = self._explore(xml_path)
        self._write_reports(summary)
        if print_hierarchy:
            self._print_hierarchy(summary)
        return summary

    def _explore(self, xml_path: Path) -> ExplorationSummary:
        """
        Executes the _explore workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                xml_path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.logger.info("Exploring XML file: %s", xml_path)
        try:
            tree = self.loader.parse(xml_path)
            root = tree.getroot()
        except Exception:
            self.logger.exception("Failed to parse XML file: %s", xml_path)
            raise

        summary = ExplorationSummary(file_count=1)
        self._traverse(root, [], summary)
        self._summarize_folders(root, xml_path.name, summary)
        return summary

    def _traverse(self, element: Element, parents: list[str], summary: ExplorationSummary) -> None:
        """
        Executes the _traverse workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                element (object): Value supplied by the caller and used by the workflow.
                parents (object): Value supplied by the caller and used by the workflow.
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        tag = self._clean_tag(element.tag)
        path = " / ".join([*parents, tag])

        summary.tag_counts[tag] += 1
        summary.hierarchy_paths[path] += 1

        if tag in INFORMATICA_COMPONENT_TAGS:
            summary.component_counts[tag] += 1
            name = element.attrib.get("NAME")
            if name:
                summary.component_names[tag].add(name)

        for child in list(element):
            self._traverse(child, [*parents, tag], summary)

    def _summarize_folders(self, root: Element, file_name: str, summary: ExplorationSummary) -> None:
        """
        Executes the _summarize_folders workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                root (object): Value supplied by the caller and used by the workflow.
                file_name (object): Value supplied by the caller and used by the workflow.
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        repository_name = self._first_attr(root, "REPOSITORY", "NAME")
        for folder in root.iter("FOLDER"):
            folder_name = folder.attrib.get("NAME", "")
            folder_summary = FolderSummary(
                file_name=file_name,
                repository_name=repository_name,
                folder_name=folder_name,
                sources=len(list(folder.findall("SOURCE"))),
                targets=len(list(folder.findall("TARGET"))),
                mappings=len(list(folder.findall("MAPPING"))),
                mapplets=len(list(folder.findall("MAPPLET"))),
                sessions=len(list(folder.findall("SESSION"))),
                workflows=len(list(folder.findall("WORKFLOW"))),
                transformations=len(list(folder.iter("TRANSFORMATION"))),
            )
            summary.folder_summary.append(folder_summary)

            for mapping in folder.findall("MAPPING"):
                transformations = list(mapping.findall("TRANSFORMATION"))
                transformation_types = sorted(
                    {item.attrib.get("TYPE", "UNKNOWN") for item in transformations}
                )
                instances = list(mapping.findall("INSTANCE"))
                summary.mapping_summary.append(
                    MappingSummary(
                        file_name=file_name,
                        folder_name=folder_name,
                        mapping_name=mapping.attrib.get("NAME", ""),
                        is_valid=mapping.attrib.get("ISVALID", ""),
                        transformations=len(transformations),
                        transformation_types=", ".join(transformation_types),
                        instances=len(instances),
                        connectors=len(list(mapping.findall("CONNECTOR"))),
                        sources=sum(1 for item in instances if item.attrib.get("TYPE") == "SOURCE"),
                        targets=sum(1 for item in instances if item.attrib.get("TYPE") == "TARGET"),
                    )
                )

    def _write_reports(self, summary: ExplorationSummary) -> None:
        """
        Executes the _write_reports workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.output_folder.mkdir(parents=True, exist_ok=True)

        self._write_csv(self.output_folder / "xml_tag_inventory.csv", self._counter_rows(summary.tag_counts, "tag", "count"))
        self._write_csv(self.output_folder / "informatica_component_inventory.csv", self._component_rows(summary))
        self._write_csv(self.output_folder / "folder_level_summary.csv", [asdict(item) for item in summary.folder_summary])
        self._write_csv(self.output_folder / "mapping_level_summary.csv", [asdict(item) for item in summary.mapping_summary])
        self._write_hierarchy(summary)
        self._write_metadata_json(summary)
        self.logger.info("Report files written to %s", self.output_folder)

    def _write_hierarchy(self, summary: ExplorationSummary) -> None:
        """
        Executes the _write_hierarchy workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        lines = [
            f"{path} ({count})"
            for path, count in sorted(summary.hierarchy_paths.items(), key=lambda item: item[0])
        ]
        (self.output_folder / "xml_tag_hierarchy.txt").write_text("\n".join(lines), encoding="utf-8")

    def _write_metadata_json(self, summary: ExplorationSummary) -> None:
        """
        Executes the _write_metadata_json workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        payload = {
            "file_count": summary.file_count,
            "unique_tag_count": len(summary.tag_counts),
            "tag_counts": dict(summary.tag_counts),
            "component_counts": dict(summary.component_counts),
            "folder_count": len(summary.folder_summary),
            "mapping_count": len(summary.mapping_summary),
            "folders": [asdict(item) for item in summary.folder_summary],
            "mappings": [asdict(item) for item in summary.mapping_summary],
        }
        (self.output_folder / "metadata_summary.json").write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    def _print_hierarchy(self, summary: ExplorationSummary) -> None:
        """
        Executes the _print_hierarchy workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        for path, count in sorted(summary.hierarchy_paths.items(), key=lambda item: item[0]):
            print(f"{path} ({count})")

    def _component_rows(self, summary: ExplorationSummary) -> list[dict[str, str | int]]:
        """
        Executes the _component_rows workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                summary (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        rows: list[ComponentSummary] = []
        for tag, count in sorted(summary.component_counts.items()):
            sample_names = ", ".join(sorted(summary.component_names.get(tag, set()))[:10])
            rows.append(ComponentSummary(component_tag=tag, count=count, sample_names=sample_names))
        return [asdict(item) for item in rows]

    @staticmethod
    def _counter_rows(counter: Counter[str], key_name: str, value_name: str) -> list[dict[str, str | int]]:
        """
        Executes the _counter_rows workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                counter (object): Value supplied by the caller and used by the workflow.
                key_name (object): Value supplied by the caller and used by the workflow.
                value_name (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return [{key_name: key, value_name: value} for key, value in counter.most_common()]

    @staticmethod
    def _write_csv(output_file: Path, rows: list[dict[str, object]]) -> None:
        """
        Executes the _write_csv workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                output_file (object): Value supplied by the caller and used by the workflow.
                rows (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        import csv

        fieldnames = sorted({key for row in rows for key in row.keys()})
        with output_file.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _merge_summary(target: ExplorationSummary, source: ExplorationSummary) -> None:
        """
        Executes the _merge_summary workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                target (object): Value supplied by the caller and used by the workflow.
                source (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        target.file_count += source.file_count
        target.tag_counts.update(source.tag_counts)
        target.component_counts.update(source.component_counts)
        target.hierarchy_paths.update(source.hierarchy_paths)
        target.folder_summary.extend(source.folder_summary)
        target.mapping_summary.extend(source.mapping_summary)
        for tag, names in source.component_names.items():
            target.component_names[tag].update(names)

    def _resolve_path(self, path_value: str | Path) -> Path:
        """
        Executes the _resolve_path workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path_value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        path = Path(path_value)
        return path if path.is_absolute() else self.project_root / path

    @staticmethod
    def _clean_tag(tag: str) -> str:
        """
        Executes the _clean_tag workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                tag (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return tag.split("}", 1)[-1] if "}" in tag else tag

    @staticmethod
    def _first_attr(root: Element, tag: str, attribute: str) -> str:
        """
        Executes the _first_attr workflow for PowerCenter XML metadata parsing.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                root (object): Value supplied by the caller and used by the workflow.
                tag (object): Value supplied by the caller and used by the workflow.
                attribute (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that extracts mappings, transformations, sessions, workflows, sources, and targets from Informatica XML exports. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        element = next(root.iter(tag), None)
        return element.attrib.get(attribute, "") if element is not None else ""
