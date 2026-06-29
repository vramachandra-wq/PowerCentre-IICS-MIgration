from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

from automation.metrics import MetricsCalculator


@dataclass(frozen=True)
class CanonicalEvaluationObject:
    """Normalized mapping-level object consumed by Week-3 AI evaluation."""

    xml_name: str
    workflow: str
    session: str
    mapping: str
    complexity: dict[str, Any] = field(default_factory=dict)
    inventory: dict[str, Any] = field(default_factory=dict)
    datatype: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    remediation: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    risk: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationMatrixRecord:
    """Flat validation matrix row. One record represents one mapping."""

    xml_name: str
    workflow: str
    session: str
    mapping: str
    source_count: int
    target_count: int
    transformation_count: int
    lookup_count: int
    joiner_count: int
    aggregator_count: int
    router_count: int
    sql_override_count: int
    complexity_score: int
    complexity_category: str
    validation_issues: int
    validation_passed: int
    validation_failed: int
    auto_fixed: int
    remaining_issues: int
    manual_review: int
    manual_remediation: int
    readiness_before: int
    readiness_after: int
    readiness_category: str
    risk_score: int
    risk_category: str
    top_risk_factor: str
    auto_fix_success_rate: float
    blocking_issues: int
    migration_status: str


class ReportRepository:
    """File repository for existing Week-1/Week-2 artifacts and Week-3 outputs."""

    def __init__(self, output_folder: str | Path = "output", reports_folder: str | Path = "output/automation") -> None:
        self.output_folder = Path(output_folder)
        self.reports_folder = Path(reports_folder)

    def read_csv(self, relative_path: str | Path) -> list[dict[str, str]]:
        path = self.output_folder / relative_path
        path = self._preferred_existing_path(path)
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    def read_json(self, relative_path: str | Path) -> Any:
        path = self.output_folder / relative_path
        if not path.exists():
            return {}
        with path.open("r", encoding="utf-8") as json_file:
            return json.load(json_file)

    def write_csv(self, file_name: str, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> Path:
        self.reports_folder.mkdir(parents=True, exist_ok=True)
        path = self.reports_folder / file_name
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def write_json(self, file_name: str, payload: Any) -> Path:
        self.reports_folder.mkdir(parents=True, exist_ok=True)
        path = self.reports_folder / file_name
        with path.open("w", encoding="utf-8") as json_file:
            json.dump(payload, json_file, indent=2, sort_keys=True)
        return path

    @staticmethod
    def _preferred_existing_path(path: Path) -> Path:
        if path.name == "remediation_report.csv":
            latest = path.with_name("remediation_report_latest.csv")
            if latest.exists() and (not path.exists() or latest.stat().st_mtime >= path.stat().st_mtime):
                return latest
        return path


class EvaluationMatrixBuilder:
    """Builds the AI-ready validation matrix by consuming existing report artifacts."""

    FIELDNAMES = [
        "xml_name",
        "workflow",
        "session",
        "mapping",
        "source_count",
        "target_count",
        "transformation_count",
        "lookup_count",
        "joiner_count",
        "aggregator_count",
        "router_count",
        "sql_override_count",
        "complexity_score",
        "complexity_category",
        "validation_issues",
        "validation_passed",
        "validation_failed",
        "auto_fixed",
        "remaining_issues",
        "manual_review",
        "manual_remediation",
        "readiness_before",
        "readiness_after",
        "readiness_category",
        "risk_score",
        "risk_category",
        "top_risk_factor",
        "auto_fix_success_rate",
        "blocking_issues",
        "migration_status",
    ]

    def __init__(self, repository: ReportRepository | None = None, validation_rules_path: str | Path | None = None) -> None:
        self.repository = repository or ReportRepository()
        self.validation_rules_path = Path(validation_rules_path or "common/config/validation_rules.json")
        self.metrics = MetricsCalculator()

    def build(self) -> list[EvaluationMatrixRecord]:
        mappings = self.repository.read_csv("metadata_tables/mappings.csv")
        complexity = self._index(self.repository.read_csv("complexity_classification_report.csv"), "Mapping")
        readiness = self._index(self.repository.read_csv("migration_readiness_report.csv"), "mapping_name")
        risk = self._index(self.repository.read_csv("risk_assessment_report.csv"), "mapping_name")
        effectiveness = self._index(self.repository.read_csv("remediation_effectiveness_report.csv"), "mapping_name")
        validation = self._group_by_mapping(self.repository.read_csv("validation_report.csv"), "Asset", "Source File")
        datatype = self._group_by_mapping(self.repository.read_csv("datatype_mismatch_report.csv"), "mapping_name", "source_file")
        remediation = self._group_by_mapping(self.repository.read_csv("remediation_report.csv"), "Asset", "")
        sessions = self._group_by_mapping(self.repository.read_csv("metadata_tables/sessions.csv"), "mapping_name", "file_name")
        workflows = self._group_by_xml(self.repository.read_csv("metadata_tables/workflows.csv"))
        transformations = self._group_by_mapping(
            self.repository.read_csv("metadata_tables/transformations.csv"), "mapping_name", "file_name"
        )
        rule_count = self._validation_rule_count()

        records: list[EvaluationMatrixRecord] = []
        for mapping_row in mappings:
            mapping = mapping_row.get("mapping_name", "")
            xml_name = mapping_row.get("file_name", "")
            complexity_row = complexity.get(mapping, {})
            readiness_row = readiness.get(mapping, {})
            risk_row = risk.get(mapping, {})
            effectiveness_row = effectiveness.get(mapping, {})
            validation_rows = validation.get(mapping, [])
            datatype_rows = datatype.get(mapping, [])
            remediation_rows = remediation.get(mapping, [])
            transformation_rows = transformations.get(mapping, [])

            validation_failed = len(validation_rows) + len(datatype_rows)
            validation_passed = max(rule_count - validation_failed, 0)
            auto_fixed = self._first_int(effectiveness_row, "auto_fixed") or self._auto_fixed(remediation_rows)
            remediation_total = len(remediation_rows)
            effectiveness_percentage = MetricsCalculator.to_float(effectiveness_row.get("auto_fix_percentage", 0))
            auto_fix_success_rate = (
                effectiveness_percentage
                if effectiveness_percentage
                else self.metrics.percentage(auto_fixed, remediation_total)
            )
            remaining = self._first_int(readiness_row, "issues_remaining")
            manual_review = self._first_int(effectiveness_row, "manual_review") or self._manual_count(
                remediation_rows, "Approval Required"
            )
            manual_remediation = self._first_int(effectiveness_row, "manual_remediation") or self._manual_count(
                remediation_rows, "Manual Remediation Required"
            )
            risk_score = self._first_int(risk_row, "risk_score")
            risk_category = risk_row.get("risk_level", "LOW") or "LOW"
            readiness_after = self._first_int(readiness_row, "readiness_after")
            readiness_before = self._first_int(readiness_row, "readiness_before")
            blocking_issues = self._blocking_issues(remaining, risk_category, readiness_after)

            records.append(
                EvaluationMatrixRecord(
                    xml_name=xml_name,
                    workflow=self._workflow_name(workflows.get(Path(xml_name).name, []), xml_name),
                    session=self._session_name(sessions.get(mapping, [])),
                    mapping=mapping,
                    source_count=self._first_int(mapping_row, "source_count"),
                    target_count=self._first_int(mapping_row, "target_count"),
                    transformation_count=self._first_int(mapping_row, "transformation_count"),
                    lookup_count=self._type_count(transformation_rows, "lookup"),
                    joiner_count=self._type_count(transformation_rows, "joiner"),
                    aggregator_count=self._type_count(transformation_rows, "aggregator"),
                    router_count=self._type_count(transformation_rows, "router"),
                    sql_override_count=self._first_int(mapping_row, "sql_override_count"),
                    complexity_score=self._first_int(complexity_row, "Score"),
                    complexity_category=complexity_row.get("Complexity", "UNKNOWN") or "UNKNOWN",
                    validation_issues=validation_failed,
                    validation_passed=validation_passed,
                    validation_failed=validation_failed,
                    auto_fixed=auto_fixed,
                    remaining_issues=remaining,
                    manual_review=manual_review,
                    manual_remediation=manual_remediation,
                    readiness_before=readiness_before,
                    readiness_after=readiness_after,
                    readiness_category=readiness_row.get("readiness_category", "UNKNOWN") or "UNKNOWN",
                    risk_score=risk_score,
                    risk_category=risk_category,
                    top_risk_factor=risk_row.get("top_risk_factor", "none") or "none",
                    auto_fix_success_rate=auto_fix_success_rate,
                    blocking_issues=blocking_issues,
                    migration_status=self._migration_status(readiness_after, risk_category, remaining, manual_remediation),
                )
            )
        return sorted(records, key=lambda item: (item.xml_name, item.mapping))

    def build_canonical_objects(self, records: Iterable[EvaluationMatrixRecord]) -> list[CanonicalEvaluationObject]:
        objects: list[CanonicalEvaluationObject] = []
        for record in records:
            objects.append(
                CanonicalEvaluationObject(
                    xml_name=record.xml_name,
                    workflow=record.workflow,
                    session=record.session,
                    mapping=record.mapping,
                    complexity={
                        "score": record.complexity_score,
                        "category": record.complexity_category,
                    },
                    inventory={
                        "sources": record.source_count,
                        "targets": record.target_count,
                        "transformations": record.transformation_count,
                        "lookups": record.lookup_count,
                        "joiners": record.joiner_count,
                        "aggregators": record.aggregator_count,
                        "routers": record.router_count,
                        "sql_overrides": record.sql_override_count,
                    },
                    validation={
                        "issues": record.validation_issues,
                        "passed": record.validation_passed,
                        "failed": record.validation_failed,
                    },
                    remediation={
                        "auto_fixed": record.auto_fixed,
                        "remaining": record.remaining_issues,
                        "manual_review": record.manual_review,
                        "manual_remediation": record.manual_remediation,
                        "auto_fix_success_rate": record.auto_fix_success_rate,
                    },
                    readiness={
                        "before": record.readiness_before,
                        "after": record.readiness_after,
                        "category": record.readiness_category,
                    },
                    risk={
                        "score": record.risk_score,
                        "category": record.risk_category,
                        "top_factor": record.top_risk_factor,
                    },
                )
            )
        return objects

    def write(self, records: Iterable[EvaluationMatrixRecord]) -> Path:
        rows = [asdict(record) for record in records]
        return self.repository.write_csv("evaluation_matrix.csv", rows, self.FIELDNAMES)

    def _validation_rule_count(self) -> int:
        if not self.validation_rules_path.exists():
            return 0
        with self.validation_rules_path.open("r", encoding="utf-8") as rules_file:
            payload = json.load(rules_file)
        if isinstance(payload, dict):
            rules = payload.get("rules", payload.get("validation_rules", []))
            return len(rules) if isinstance(rules, list) else 0
        return len(payload) if isinstance(payload, list) else 0

    def _group_by_mapping(
        self, rows: list[dict[str, str]], mapping_field: str, source_file_field: str
    ) -> dict[str, list[dict[str, str]]]:
        mapping_by_xml = self._mapping_by_xml()
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            mapping = row.get(mapping_field, "")
            if mapping and mapping.lower().endswith(".xml"):
                mapping = mapping_by_xml.get(Path(mapping).name, Path(mapping).stem)
            if not mapping and source_file_field:
                source_file = row.get(source_file_field, "")
                mapping = mapping_by_xml.get(Path(source_file).name, mapping_by_xml.get(Path(source_file).stem, ""))
            if mapping:
                grouped[mapping].append(row)
        return grouped

    def _mapping_by_xml(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for row in self.repository.read_csv("metadata_tables/mappings.csv"):
            mapping = row.get("mapping_name", "")
            xml_name = row.get("file_name", "")
            if mapping and xml_name:
                index[Path(xml_name).name] = mapping
                index[Path(xml_name).stem] = mapping
        return index

    @staticmethod
    def _group_by_xml(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            xml_name = row.get("file_name", "")
            if xml_name:
                grouped[Path(xml_name).name].append(row)
        return grouped

    @staticmethod
    def _index(rows: list[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
        return {row.get(key, ""): row for row in rows if row.get(key)}

    @staticmethod
    def _first_int(row: dict[str, str], field: str) -> int:
        return MetricsCalculator.to_int(row.get(field, 0))

    @staticmethod
    def _type_count(rows: Iterable[dict[str, str]], token: str) -> int:
        return sum(1 for row in rows if token in row.get("transformation_type", "").lower())

    @staticmethod
    def _auto_fixed(rows: Iterable[dict[str, str]]) -> int:
        return sum(1 for row in rows if str(row.get("Auto Fixed", "")).lower() == "true")

    @staticmethod
    def _manual_count(rows: Iterable[dict[str, str]], field: str) -> int:
        return sum(1 for row in rows if str(row.get(field, "")).lower() == "true")

    @staticmethod
    def _session_name(rows: list[dict[str, str]]) -> str:
        return rows[0].get("session_name", "") if rows else ""

    @staticmethod
    def _workflow_name(rows: list[dict[str, str]], xml_name: str) -> str:
        if rows:
            return rows[0].get("workflow_name", "")
        return Path(xml_name).stem

    @staticmethod
    def _blocking_issues(remaining: int, risk_category: str, readiness_after: int) -> int:
        if remaining <= 0:
            return 0
        if risk_category.upper() in {"HIGH", "CRITICAL"} or readiness_after < 50:
            return remaining
        return 0

    @staticmethod
    def _migration_status(readiness_after: int, risk_category: str, remaining: int, manual_remediation: int) -> str:
        if readiness_after >= 80 and risk_category.upper() == "LOW" and remaining == 0:
            return "READY"
        if risk_category.upper() in {"HIGH", "CRITICAL"} or readiness_after < 50:
            return "HIGH_RISK"
        if manual_remediation or remaining:
            return "NEEDS_REVIEW"
        return "READY_WITH_MONITORING"

    @staticmethod
    def issue_distribution(rows: Iterable[dict[str, str]], field: str) -> Counter[str]:
        return Counter(row.get(field, "") for row in rows if row.get(field))
