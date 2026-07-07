"""
Module: business/validation/xml_remediation_engine.py

Purpose:
    This module supports migration validation and readiness logic for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the migration validation and readiness logic area and evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from lxml import etree
except ModuleNotFoundError:  # pragma: no cover - stdlib fallback for lean environments.
    etree = None


@dataclass(frozen=True)
class XmlChange:
    """
    Represents the XmlChange component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    xml_file: str
    object_type: str
    object_name: str
    attribute: str
    before_value: str
    after_value: str
    rule_applied: str
    status: str
    timestamp: str


class XmlRemediationEngine:
    """Applies approved metadata-level remediation to every PowerCenter XML file."""

    AUTO_FIX_ISSUES = {
        "precision_mismatch",
        "scale_mismatch",
        "length_mismatch",
        "truncation_risk",
        "varchar_precision_doubling",
        "unicode_mismatch",
        "varchar_vs_nvarchar",
        "native_precision_mismatch",
        "lookup_datatype_mismatch",
    }

    AI_ASSISTANCE_PATTERNS = [
        "STORED PROCEDURE",
        "JAVA",
        "DLL",
        "CDC",
        "PUSHDOWN",
        "SAP",
        "MAINFRAME",
        "COBOL",
        "MQ",
        "COMMAND",
        "EVENT WAIT",
        "EMAIL",
        "WORKLET",
    ]

    def __init__(
        self,
        input_folder: str | Path = "input_xml",
        output_folder: str | Path = "output",
        datatype_report: str | Path | None = None,
    ) -> None:
        """
        Executes the __init__ workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                input_folder (object): Value supplied by the caller and used by the workflow.
                output_folder (object): Value supplied by the caller and used by the workflow.
                datatype_report (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.project_root = Path.cwd()
        self.input_folder = self._resolve_path(input_folder)
        self.output_folder = self._resolve_path(output_folder)
        self.remediated_folder = self.output_folder / "remediated_xml"
        self.datatype_report = self._resolve_path(datatype_report or self.output_folder / "datatype_mismatch_report.csv")

    def remediate_all(self) -> list[XmlChange]:
        """
        Executes the remediate_all workflow for migration validation and readiness logic.
        
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
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.remediated_folder.mkdir(parents=True, exist_ok=True)
        target_updates, transform_updates = self._build_updates(self._read_csv(self.datatype_report))
        changes: list[XmlChange] = []

        for xml_path in self._xml_files():
            changes.extend(self.remediate_file(xml_path, target_updates, transform_updates))
        return changes

    def remediate_file(
        self,
        xml_path: Path,
        target_updates: dict[tuple[str, str], dict[str, object]],
        transform_updates: dict[tuple[str, str, str], dict[str, object]],
    ) -> list[XmlChange]:
        """
        Executes the remediate_file workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                xml_path (object): Value supplied by the caller and used by the workflow.
                target_updates (object): Value supplied by the caller and used by the workflow.
                transform_updates (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        output_path = self.remediated_folder / f"{xml_path.stem}_remediated{xml_path.suffix.lower()}"
        tree = self._parse_xml(xml_path)
        root = tree.getroot()
        changes: list[XmlChange] = []

        if self._ai_assistance_only(root):
            self._write_xml(tree, output_path)
            return [
                self._change(xml_path.name, "XML", xml_path.stem, "AI_ASSISTANCE_REQUIRED", "", "true", "ai_assistance_exclusion", "AI_ASSISTANCE_REQUIRED")
            ]

        for elem in root.iter("TARGETFIELD"):
            update = target_updates.get((xml_path.name, self._normalize(elem.get("NAME", ""))))
            if update:
                changes.extend(self._apply_update(xml_path.name, elem, update))

        for transformation in root.iter("TRANSFORMATION"):
            transformation_name = transformation.get("NAME", "")
            transformation_key = self._normalize(transformation_name)
            if self._ai_assistance_transformation(transformation):
                changes.append(
                    self._change(
                        xml_path.name,
                        "TRANSFORMATION",
                        transformation_name,
                        "AI_ASSISTANCE_REQUIRED",
                        "",
                        "true",
                        "ai_assistance_exclusion",
                        "AI_ASSISTANCE_REQUIRED",
                    )
                )
                continue
            for field in transformation.iter("TRANSFORMFIELD"):
                update = transform_updates.get((xml_path.name, transformation_key, self._normalize(field.get("NAME", ""))))
                if update:
                    changes.extend(self._apply_update(xml_path.name, field, update))

        self._write_xml(tree, output_path)
        return changes

    def _apply_update(self, xml_file: str, elem, update: dict[str, object]) -> list[XmlChange]:
        """
        Executes the _apply_update workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                xml_file (object): Value supplied by the caller and used by the workflow.
                elem (object): Value supplied by the caller and used by the workflow.
                update (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        changes: list[XmlChange] = []
        issues = set(update.get("issues", set()))
        object_name = elem.get("NAME", "")
        object_type = str(elem.tag)

        if issues & {"precision_mismatch", "native_precision_mismatch", "lookup_datatype_mismatch"}:
            changes.extend(self._set_attr(xml_file, elem, object_type, object_name, "PRECISION", update.get("precision"), "precision_mismatch"))
        if issues & {"scale_mismatch", "native_precision_mismatch", "lookup_datatype_mismatch"}:
            changes.extend(self._set_attr(xml_file, elem, object_type, object_name, "SCALE", update.get("scale"), "scale_mismatch"))
        if issues & {"length_mismatch", "truncation_risk", "varchar_precision_doubling"}:
            length = update.get("length")
            if self._string_datatype(elem):
                for attr in ("LENGTH", "PHYSICALLENGTH", "PRECISION"):
                    if elem.get(attr) is not None:
                        changes.extend(self._set_attr(xml_file, elem, object_type, object_name, attr, length, "length_mismatch"))
        if update.get("unicode"):
            datatype = elem.get("DATATYPE", "").lower()
            if datatype in {"varchar", "varchar2", "char"}:
                after = "nvarchar2" if datatype in {"varchar", "varchar2"} else "nchar"
                changes.extend(self._set_attr(xml_file, elem, object_type, object_name, "DATATYPE", after, "unicode_mismatch"))
        return changes

    def _set_attr(
        self,
        xml_file: str,
        elem,
        object_type: str,
        object_name: str,
        attribute: str,
        after: object,
        rule: str,
    ) -> list[XmlChange]:
        """
        Executes the _set_attr workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                xml_file (object): Value supplied by the caller and used by the workflow.
                elem (object): Value supplied by the caller and used by the workflow.
                object_type (object): Value supplied by the caller and used by the workflow.
                object_name (object): Value supplied by the caller and used by the workflow.
                attribute (object): Value supplied by the caller and used by the workflow.
                after (object): Value supplied by the caller and used by the workflow.
                rule (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if after is None:
            return []
        before = elem.get(attribute, "")
        after_text = str(after)
        if before == after_text:
            return []
        elem.set(attribute, after_text)
        return [self._change(xml_file, object_type, object_name, attribute, before, after_text, rule, "AUTO_FIXED")]

    def _build_updates(
        self,
        rows: Iterable[dict[str, str]],
    ) -> tuple[dict[tuple[str, str], dict[str, object]], dict[tuple[str, str, str], dict[str, object]]]:
        """
        Executes the _build_updates workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                rows (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        target_updates: dict[tuple[str, str], dict[str, object]] = {}
        transform_updates: dict[tuple[str, str, str], dict[str, object]] = {}
        for row in rows:
            issue = row.get("issue_type", "").strip()
            if issue not in self.AUTO_FIX_ISSUES:
                continue
            xml_file = Path(row.get("source_file", "")).name
            column_key = self._normalize(row.get("column", ""))
            if not xml_file or not column_key:
                continue

            transformation = row.get("transformation", "").strip()
            if transformation:
                entry = transform_updates.setdefault((xml_file, self._normalize(transformation), column_key), {"issues": set()})
            else:
                entry = target_updates.setdefault((xml_file, column_key), {"issues": set()})
            self._merge_update(entry, row)
        return target_updates, transform_updates

    def _merge_update(self, entry: dict[str, object], row: dict[str, str]) -> None:
        """
        Executes the _merge_update workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                entry (object): Value supplied by the caller and used by the workflow.
                row (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        issue = row.get("issue_type", "").strip()
        source_base, source_precision, source_scale = self._parse_type(row.get("source", ""))
        target_base, _, _ = self._parse_type(row.get("target", ""))
        entry.setdefault("issues", set()).add(issue)
        if issue in {"precision_mismatch", "native_precision_mismatch", "lookup_datatype_mismatch"} and source_precision is not None:
            entry["precision"] = source_precision
        if issue in {"scale_mismatch", "native_precision_mismatch", "lookup_datatype_mismatch"} and source_scale is not None:
            entry["scale"] = source_scale
        if issue in {"length_mismatch", "truncation_risk", "varchar_precision_doubling"} and source_precision is not None:
            entry["length"] = source_precision
        if issue in {"unicode_mismatch", "varchar_vs_nvarchar"} and (
            source_base in {"NSTRING", "NVARCHAR2", "NCHAR"} or target_base in {"NSTRING", "NVARCHAR2", "NCHAR"}
        ):
            entry["unicode"] = True

    def _parse_xml(self, path: Path):
        """
        Executes the _parse_xml workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if etree is None:
            import xml.etree.ElementTree as std_etree

            return std_etree.parse(path)
        parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False, load_dtd=False)
        return etree.parse(str(path), parser)

    def _write_xml(self, tree, path: Path) -> None:
        """
        Executes the _write_xml workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                tree (object): Value supplied by the caller and used by the workflow.
                path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if etree is None:
            body = self._stdlib_tostring(tree)
            text = '<?xml version="1.0" encoding="UTF-8"?>\n<!-- Informatica proprietary -->\n<!DOCTYPE POWERMART SYSTEM "powrmart.dtd">\n' + body + "\n"
            path.write_text(text, encoding="utf-8")
            return
        tree.write(
            str(path),
            encoding="UTF-8",
            xml_declaration=True,
            doctype='<!DOCTYPE POWERMART SYSTEM "powrmart.dtd">',
            pretty_print=False,
        )

    @staticmethod
    def _stdlib_tostring(tree) -> str:
        """
        Executes the _stdlib_tostring workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                tree (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        import xml.etree.ElementTree as std_etree

        return std_etree.tostring(tree.getroot(), encoding="unicode")

    def _ai_assistance_only(self, root) -> bool:
        """
        Executes the _ai_assistance_only workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                root (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        text = " ".join(str(value).upper() for elem in root.iter() for value in [elem.tag, *elem.attrib.values()])
        return any(pattern in text for pattern in ["SAP CONNECTOR", "MAINFRAME", "COBOL SOURCE", "MQ SOURCE"])

    def _ai_assistance_transformation(self, elem) -> bool:
        """
        Executes the _ai_assistance_transformation workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                elem (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        text = " ".join(str(value).upper() for value in [elem.get("NAME", ""), elem.get("TYPE", ""), *elem.attrib.values()])
        return any(pattern in text for pattern in self.AI_ASSISTANCE_PATTERNS)

    @staticmethod
    def _string_datatype(elem) -> bool:
        """
        Executes the _string_datatype workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                elem (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return elem.get("DATATYPE", "").lower() in {"varchar", "varchar2", "nvarchar2", "char", "nchar", "string"}

    @staticmethod
    def _parse_type(value: str) -> tuple[str, int | None, int | None]:
        """
        Executes the _parse_type workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        match = re.match(r"^([A-Z0-9_]+)\s*(?:\((\d+)(?:,(\d+))?\))?$", str(value or "").strip().upper())
        if not match:
            return str(value or "").strip().upper(), None, None
        return (
            match.group(1),
            int(match.group(2)) if match.group(2) else None,
            int(match.group(3)) if match.group(3) else None,
        )

    @staticmethod
    def _normalize(value: str) -> str:
        """
        Executes the _normalize workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        """
        Executes the _read_csv workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    def _xml_files(self) -> list[Path]:
        """
        Executes the _xml_files workflow for migration validation and readiness logic.
        
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
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return sorted({path.resolve() for path in [*self.input_folder.glob("*.XML"), *self.input_folder.glob("*.xml")]})

    @staticmethod
    def _change(
        xml_file: str,
        object_type: str,
        object_name: str,
        attribute: str,
        before: str,
        after: str,
        rule: str,
        status: str,
    ) -> XmlChange:
        """
        Executes the _change workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                xml_file (object): Value supplied by the caller and used by the workflow.
                object_type (object): Value supplied by the caller and used by the workflow.
                object_name (object): Value supplied by the caller and used by the workflow.
                attribute (object): Value supplied by the caller and used by the workflow.
                before (object): Value supplied by the caller and used by the workflow.
                after (object): Value supplied by the caller and used by the workflow.
                rule (object): Value supplied by the caller and used by the workflow.
                status (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        from datetime import datetime

        return XmlChange(
            xml_file=xml_file,
            object_type=object_type,
            object_name=object_name,
            attribute=attribute,
            before_value=before,
            after_value=after,
            rule_applied=rule,
            status=status,
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )

    def _resolve_path(self, path: str | Path) -> Path:
        """
        Executes the _resolve_path workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate
