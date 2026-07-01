from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from automation.metrics import MetricsCalculator
from business.validation.readiness_engine import Day3ReportLoader


@dataclass(frozen=True)
class CanonicalEvaluationObject:
    """Normalized mapping-level object consumed by Week-3 rule-based evaluation."""

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
    auto_fixable_issues: int
    auto_fixed: int
    remaining_unresolved: int
    manual_review: int
    manual_remediation: int
    readiness_before: int
    readiness_after: int
    readiness_improvement: float
    readiness_category: str
    risk_before: int
    risk_after: int
    risk_reduction: int
    risk_category: str
    top_risk_factor: str
    auto_fix_success_rate: float
    blocking_issues: int
    migration_status: str
    overall_health_score: float

    @property
    def remaining_issues(self) -> int:
        return self.remaining_unresolved

    @property
    def risk_score(self) -> int:
        return self.risk_after


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
        with self._open_writable(path, newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            return Path(csv_file.name)

    def write_json(self, file_name: str, payload: Any) -> Path:
        self.reports_folder.mkdir(parents=True, exist_ok=True)
        path = self.reports_folder / file_name
        with self._open_writable(path) as json_file:
            json.dump(payload, json_file, indent=2, sort_keys=True)
            return Path(json_file.name)

    @staticmethod
    def _preferred_existing_path(path: Path) -> Path:
        if path.name == "remediation_report.csv":
            latest = path.with_name("remediation_report_latest.csv")
            if latest.exists() and (not path.exists() or latest.stat().st_mtime >= path.stat().st_mtime):
                return latest
        return path

    @staticmethod
    def _open_writable(path: Path, newline: str | None = None):
        candidates = [
            path,
            path.with_name(f"{path.stem}_latest{path.suffix}"),
            path.with_name(f"{path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}"),
        ]
        last_error: PermissionError | None = None
        for candidate in candidates:
            try:
                if newline is None:
                    return candidate.open("w", encoding="utf-8")
                return candidate.open("w", newline=newline, encoding="utf-8")
            except PermissionError as exc:
                last_error = exc
        raise last_error or PermissionError(f"Unable to write report: {path}")


class EvaluationMatrixBuilder:
    """Builds the validation matrix by consuming existing report artifacts."""

    MANUAL_UNRESOLVED_ISSUES = {"mapplet_nesting"}

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
        "auto_fixable_issues",
        "auto_fixed",
        "remaining_unresolved",
        "manual_review",
        "manual_remediation",
        "readiness_before",
        "readiness_after",
        "readiness_improvement",
        "readiness_category",
        "risk_before",
        "risk_after",
        "risk_reduction",
        "risk_category",
        "top_risk_factor",
        "auto_fix_success_rate",
        "blocking_issues",
        "migration_status",
        "overall_health_score",
    ]

    def __init__(self, repository: ReportRepository | None = None, validation_rules_path: str | Path | None = None) -> None:
        self.repository = repository or ReportRepository()
        self.validation_rules_path = Path(validation_rules_path or "common/config/validation_rules.json")
        self.metrics = MetricsCalculator()
        self.day3_loader = Day3ReportLoader(self.repository.output_folder)
        self.risk_rules = self.day3_loader.rules

    def build(self) -> list[EvaluationMatrixRecord]:
        mappings = self.repository.read_csv("metadata_tables/mappings.csv")
        complexity = self._index(self.repository.read_csv("complexity_classification_report.csv"), "Mapping")
        readiness = self._index(self.repository.read_csv("migration_readiness_report.csv"), "mapping_name")
        effectiveness = self._index(self.repository.read_csv("remediation_effectiveness_report.csv"), "mapping_name")
        validation = self._group_by_mapping(self.repository.read_csv("validation_report.csv"), "Asset", "Source File")
        datatype = self._group_by_mapping(self.repository.read_csv("datatype_mismatch_report.csv"), "mapping_name", "source_file")
        remediation = self._group_remediation_by_mapping(self.repository.read_csv("remediation_report.csv"))
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
            effectiveness_row = effectiveness.get(mapping, {})
            validation_rows = validation.get(mapping, [])
            datatype_rows = datatype.get(mapping, [])
            remediation_rows = remediation.get(mapping, [])
            transformation_rows = transformations.get(mapping, [])

            before_issues = self._issue_records(mapping, validation_rows, datatype_rows)
            unique_before_issues = self._deduplicate_issues(before_issues)
            unresolved_issues = self._unresolved_issues(unique_before_issues, remediation_rows)
            validation_failed = len(unresolved_issues)
            validation_issues = len(unique_before_issues)
            validation_passed = max(validation_issues - validation_failed, 0)
            auto_fixed = self._auto_fixed(remediation_rows) or self._first_int(effectiveness_row, "auto_fixed")
            remaining_unresolved = len(unresolved_issues)
            manual_review = self._manual_count(
                remediation_rows, "Approval Required"
            ) or self._first_int(effectiveness_row, "manual_review")
            manual_remediation = self._manual_count(
                remediation_rows, "Manual Remediation Required"
            ) or self._first_int(effectiveness_row, "manual_remediation")
            auto_fixable_issues = self._auto_fixable_count(remediation_rows)
            if not auto_fixable_issues:
                auto_fixable_issues = max(
                    self._first_int(effectiveness_row, "issues_found") - manual_review - manual_remediation,
                    auto_fixed,
                    0,
                )
            auto_fix_success_rate = self.metrics.percentage(auto_fixed, auto_fixable_issues)
            risk_before, _ = self._risk_summary(unique_before_issues)
            risk_after, top_risk_factor = self._risk_summary(unresolved_issues)
            risk_category = self._risk_category(risk_after)
            readiness_after = self._first_int(readiness_row, "readiness_after")
            readiness_before = self._first_int(readiness_row, "readiness_before")
            readiness_improvement = self.metrics.readiness_improvement(readiness_before, readiness_after)
            risk_reduction = max(risk_before - risk_after, 0)
            blocking_issues = self._blocking_issues(remaining_unresolved, risk_category, readiness_after)
            overall_health_score = self._overall_health_score(readiness_after, risk_after, validation_failed, auto_fix_success_rate)

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
                    validation_issues=validation_issues,
                    validation_passed=validation_passed,
                    validation_failed=validation_failed,
                    auto_fixable_issues=auto_fixable_issues,
                    auto_fixed=auto_fixed,
                    remaining_unresolved=remaining_unresolved,
                    manual_review=manual_review,
                    manual_remediation=manual_remediation,
                    readiness_before=readiness_before,
                    readiness_after=readiness_after,
                    readiness_improvement=readiness_improvement,
                    readiness_category=readiness_row.get("readiness_category", "UNKNOWN") or "UNKNOWN",
                    risk_before=risk_before,
                    risk_after=risk_after,
                    risk_reduction=risk_reduction,
                    risk_category=risk_category,
                    top_risk_factor=top_risk_factor,
                    auto_fix_success_rate=auto_fix_success_rate,
                    blocking_issues=blocking_issues,
                    migration_status=self._migration_status(
                        readiness_after, risk_category, remaining_unresolved, manual_remediation
                    ),
                    overall_health_score=overall_health_score,
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
                        "auto_fixable_issues": record.auto_fixable_issues,
                        "auto_fixed": record.auto_fixed,
                        "remaining": record.remaining_unresolved,
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
                        "before": record.risk_before,
                        "after": record.risk_after,
                        "reduction": record.risk_reduction,
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

    def _group_remediation_by_mapping(self, rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows:
            mapping = self.day3_loader._mapping_from_row(row)
            if mapping:
                grouped[mapping].append(row)
        return grouped

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
    def _auto_fixable_count(rows: Iterable[dict[str, str]]) -> int:
        count = 0
        for row in rows:
            manual_review = str(row.get("Approval Required", "")).strip().lower() == "true"
            manual_remediation = str(row.get("Manual Remediation Required", "")).strip().lower() == "true"
            if not manual_review and not manual_remediation:
                count += 1
        return count

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

    def _issue_records(
        self,
        mapping: str,
        validation_rows: Iterable[dict[str, str]],
        datatype_rows: Iterable[dict[str, str]],
    ) -> list[dict[str, str]]:
        records: list[dict[str, str]] = []
        for row in validation_rows:
            issue = self.day3_loader.canonical_issue(row.get("Issue", ""))
            records.append(
                {
                    "mapping": mapping,
                    "issue": issue,
                    "asset": row.get("Asset", ""),
                    "source_file": row.get("Source File", ""),
                    "severity": row.get("Severity", "MEDIUM").upper(),
                }
            )
        for row in datatype_rows:
            issue = self.day3_loader.canonical_issue(row.get("issue_type", "datatype_mismatch"))
            records.append(
                {
                    "mapping": mapping,
                    "issue": issue,
                    "asset": row.get("column", "") or row.get("transformation", ""),
                    "source_file": row.get("source_file", ""),
                    "severity": row.get("severity", "MEDIUM").upper(),
                }
            )
        return records

    def _deduplicate_issues(self, issues: Iterable[dict[str, str]]) -> list[dict[str, str]]:
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str, str, str]] = set()
        for issue in issues:
            key = self._issue_key(issue)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(issue)
        return deduped

    def _unresolved_issues(
        self,
        before_issues: list[dict[str, str]],
        remediation_rows: Iterable[dict[str, str]],
    ) -> list[dict[str, str]]:
        resolved_counts: dict[tuple[str, str, str, str], int] = {}
        resolved_issue_counts: dict[tuple[str, str], int] = {}
        for row in remediation_rows:
            status = row.get("Status", "").strip().lower()
            if row.get("Auto Fixed", "").strip().lower() == "true" or status in {"resolved", "suppressed"}:
                issue = {
                    "mapping": self.day3_loader._mapping_from_row(row),
                    "issue": self.day3_loader.canonical_issue(row.get("Issue", "")),
                    "asset": row.get("Asset", ""),
                    "source_file": "",
                    "severity": row.get("Severity", "MEDIUM").upper(),
                }
                key = self._issue_key(issue)
                resolved_counts[key] = resolved_counts.get(key, 0) + 1
                issue_key = (issue["mapping"], issue["issue"])
                resolved_issue_counts[issue_key] = resolved_issue_counts.get(issue_key, 0) + 1

        remaining: list[dict[str, str]] = []
        for issue in before_issues:
            if issue["issue"] not in self.MANUAL_UNRESOLVED_ISSUES:
                continue
            key = self._issue_key(issue)
            if resolved_counts.get(key, 0) > 0:
                resolved_counts[key] -= 1
                continue
            issue_key = (issue["mapping"], issue["issue"])
            if resolved_issue_counts.get(issue_key, 0) > 0:
                resolved_issue_counts[issue_key] -= 1
                continue
            remaining.append(issue)
        return remaining

    @staticmethod
    def _issue_key(issue: dict[str, str]) -> tuple[str, str, str, str]:
        return (
            issue.get("mapping", ""),
            issue.get("issue", ""),
            MetricsCalculator.normalize_text(issue.get("asset", "")),
            Path(issue.get("source_file", "")).name,
        )

    def _risk_summary(self, issues: Iterable[dict[str, str]]) -> tuple[int, str]:
        scored = [(issue["issue"], self._risk_score(issue)) for issue in issues]
        if not scored:
            return 0, "none"
        return sum(score for _, score in scored), max(scored, key=lambda item: item[1])[0]

    def _risk_score(self, issue: dict[str, str]) -> int:
        factors = self.risk_rules.get("risk_factors", {})
        issue_name = issue["issue"]
        if issue_name in factors:
            return int(factors[issue_name]["score"])
        defaults = self.risk_rules.get("default_risk_score", {})
        return int(defaults.get(issue.get("severity", "MEDIUM").upper(), 8))

    def _risk_category(self, score: int) -> str:
        for band in self.risk_rules.get("risk_levels", []):
            if int(band["min"]) <= score <= int(band["max"]):
                return str(band["level"])
        return "CRITICAL"

    @staticmethod
    def _overall_health_score(
        readiness_after: int,
        risk_after: int,
        validation_failed: int,
        auto_fix_success_rate: float,
    ) -> float:
        risk_component = max(0.0, 100.0 - min(float(risk_after), 100.0))
        validation_component = max(0.0, 100.0 - min(float(validation_failed), 100.0))
        return round(
            (float(readiness_after) * 0.4)
            + (risk_component * 0.25)
            + (float(auto_fix_success_rate) * 0.25)
            + (validation_component * 0.1),
            2,
        )

    @staticmethod
    def issue_distribution(rows: Iterable[dict[str, str]], field: str) -> Counter[str]:
        return Counter(row.get(field, "") for row in rows if row.get(field))
