from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from business.validation.datatype_harmonization import DatatypeHarmonizationEngine
from common.config.config import AppConfig


@dataclass(frozen=True)
class ValidationIssue:
    rule_id: str
    issue: str
    severity: str
    asset: str
    recommendation: str
    category: str = ""
    source_file: str = ""


class ValidationEngine:
    """Rule-driven migration validation engine backed by validation_rules.json."""

    REPORT_COLUMNS = [
        "Issue",
        "Severity",
        "Recommendation",
        "Auto Fixed",
        "Fix Applied",
        "Before Value",
        "After Value",
        "Status",
        "Rule ID",
        "Asset",
        "Source File",
    ]

    def __init__(
        self,
        config: AppConfig | None = None,
        logger=None,
        output_folder: str | Path | None = None,
        rules_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        configured_output = output_folder or (config.paths.output_folder if config else "output")
        self.output_folder = self._resolve_path(configured_output)
        self.metadata_folder = self.output_folder / "metadata_tables"
        self.report_path = self.output_folder / "validation_report.csv"
        self.rules_path = self._resolve_path(rules_path or Path("common/config/validation_rules.json"))
        self.rules = self._load_rules()
        self.tables: dict[str, list[dict[str, str]]] = {}
        self.datatype_findings: list[dict[str, str]] = []

    def validate(self) -> list[ValidationIssue]:
        self.tables = self._load_metadata_tables()
        self.datatype_findings = self._load_or_build_datatype_findings()

        issues: list[ValidationIssue] = []
        for rule in self.rules:
            issues.extend(self._evaluate_rule(rule))

        deduped = self._deduplicate(issues)
        self.write_report(deduped)
        if self.logger:
            self.logger.info("Validation report written to %s. rows=%s", self.report_path, len(deduped))
        return deduped

    def write_report(self, issues: list[ValidationIssue], report_path: str | Path | None = None) -> None:
        path = self._resolve_path(report_path or self.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.REPORT_COLUMNS)
            writer.writeheader()
            for issue in issues:
                writer.writerow(
                    {
                        "Issue": issue.issue,
                        "Severity": issue.severity,
                        "Recommendation": issue.recommendation,
                        "Auto Fixed": "False",
                        "Fix Applied": "",
                        "Before Value": issue.asset,
                        "After Value": issue.asset,
                        "Status": "Open",
                        "Rule ID": issue.rule_id,
                        "Asset": issue.asset,
                        "Source File": issue.source_file,
                    }
                )

    def _evaluate_rule(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        logic = rule.get("detection_logic", {})
        detection_type = logic.get("type", "")
        handlers = {
            "session_sql_override_precedence": self._session_sql_override_precedence,
            "mapping_sql_override_precedence": self._mapping_sql_override_precedence,
            "sql_pattern": self._pattern_rule,
            "metadata_pattern": self._pattern_rule,
            "varchar_precision_doubling": self._varchar_precision_doubling,
            "missing_physical_connection": self._missing_physical_connection,
            "datatype_issue": self._datatype_issue,
            "source_query_column_count_mismatch": self._source_query_column_count_mismatch,
            "source_query_column_order_mismatch": self._source_query_column_order_mismatch,
            "duplicate_column_names": self._duplicate_column_names,
            "missing_schedules": self._missing_schedules,
            "missing_target_table_binding": self._missing_target_table_binding,
            "name_length": self._name_length,
            "missing_alias_in_concat": self._missing_alias_in_concat,
            "schema_prefix_in_lookup": self._schema_prefix_in_lookup,
            "transformation_type": self._transformation_type,
            "shared_folder_dependency": self._shared_folder_dependency,
            "snowflake_keyword_conflicts": self._snowflake_keyword_conflicts,
            "field_unavailable": self._field_unavailable,
        }
        handler = handlers.get(detection_type)
        if handler is None:
            return []
        return handler(rule)

    def _session_sql_override_precedence(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        sql_rows = self.tables.get("sql_overrides", [])
        grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
        for row in sql_rows:
            grouped[(row.get("file_name", ""), row.get("mapping_name", ""))].add(row.get("context_type", ""))
            if row.get("session_name"):
                grouped[(row.get("file_name", ""), row.get("mapping_name", ""))].add("SESSION")
        return [
            self._issue(rule, f"Session and mapping SQL override precedence requires review for {mapping}.", mapping, file_name)
            for (file_name, mapping), contexts in grouped.items()
            if "SESSION" in contexts and len(contexts - {""}) > 1
        ]

    def _mapping_sql_override_precedence(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        counter: Counter[tuple[str, str]] = Counter(
            (row.get("file_name", ""), row.get("mapping_name", ""))
            for row in self.tables.get("sql_overrides", [])
            if row.get("mapping_name")
        )
        return [
            self._issue(rule, f"Multiple SQL override contexts found for mapping {mapping}.", mapping, file_name)
            for (file_name, mapping), count in counter.items()
            if count > 1
        ]

    def _pattern_rule(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        logic = rule["detection_logic"]
        flags = re.IGNORECASE if logic.get("case_insensitive", True) else 0
        patterns = [re.compile(pattern, flags) for pattern in logic.get("patterns", [])]
        issues: list[ValidationIssue] = []
        for table_name in logic.get("tables", []):
            for row in self.tables.get(table_name, []):
                for field in logic.get("fields", []):
                    value = row.get(field, "")
                    if value and any(pattern.search(value) for pattern in patterns):
                        asset = self._asset_name(row)
                        issues.append(self._issue(rule, f"{rule['rule_name']} detected in {table_name}.{field}.", asset, row.get("file_name", "")))
                        break
        return issues

    def _varchar_precision_doubling(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for finding in self.datatype_findings:
            if finding.get("issue_type") in {"unicode_mismatch", "varchar_vs_nvarchar"}:
                issues.append(
                    self._issue(
                        rule,
                        f"Potential VARCHAR precision change for {finding.get('column', '')}: {finding.get('source', '')} to {finding.get('target', '')}.",
                        finding.get("column", ""),
                        finding.get("source_file", ""),
                    )
                )
        return issues

    def _missing_physical_connection(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for row in [*self.tables.get("sources", []), *self.tables.get("targets", [])]:
            database_type = row.get("database_type", "")
            if database_type and not row.get("connection_name"):
                issues.append(self._issue(rule, f"Physical connection metadata is missing for {self._asset_name(row)}.", self._asset_name(row), row.get("file_name", "")))
        return issues

    def _datatype_issue(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        issue_types = set(rule["detection_logic"].get("issue_types", []))
        return [
            self._issue(
                rule,
                f"{rule['rule_name']} detected for {finding.get('column', '')}: {finding.get('source', '')} to {finding.get('target', '')}.",
                finding.get("mapping_name") or finding.get("transformation") or finding.get("column", ""),
                finding.get("source_file", ""),
            )
            for finding in self.datatype_findings
            if finding.get("issue_type") in issue_types
        ]

    def _source_query_column_count_mismatch(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        ports = self._ports_by_transformation()
        issues: list[ValidationIssue] = []
        for row in self.tables.get("sql_overrides", []):
            selected = self._select_columns(row.get("sql_query", ""))
            if not selected:
                continue
            key = self._transformation_key(row)
            port_count = len(ports.get(key, []))
            if port_count and len(selected) != port_count:
                asset = row.get("context_name") or row.get("mapping_name", "")
                issues.append(self._issue(rule, f"Source query selected {len(selected)} columns but transformation has {port_count} ports.", asset, row.get("file_name", "")))
        return issues

    def _source_query_column_order_mismatch(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        ports = self._ports_by_transformation()
        issues: list[ValidationIssue] = []
        for row in self.tables.get("sql_overrides", []):
            selected = [self._normalize_name(column) for column in self._select_columns(row.get("sql_query", ""))]
            if not selected:
                continue
            key = self._transformation_key(row)
            port_names = [self._normalize_name(port.get("port_name", "")) for port in ports.get(key, [])]
            comparable_count = min(len(selected), len(port_names))
            if comparable_count and selected[:comparable_count] != port_names[:comparable_count]:
                asset = row.get("context_name") or row.get("mapping_name", "")
                issues.append(self._issue(rule, "Source query select-list order differs from transformation port order.", asset, row.get("file_name", "")))
        return issues

    def _duplicate_column_names(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for table_name, asset_key in [("source_columns", "source_name"), ("target_columns", "target_name")]:
            grouped: dict[tuple[str, str, str], list[str]] = defaultdict(list)
            for row in self.tables.get(table_name, []):
                key = (row.get("file_name", ""), row.get(asset_key, ""), self._normalize_name(row.get("column_name", "")))
                grouped[key].append(row.get("column_name", ""))
            for (file_name, asset, column), names in grouped.items():
                if column and len(names) > 1:
                    issues.append(self._issue(rule, f"Duplicate column name {names[0]} found in {asset}.", asset, file_name))
        return issues

    def _missing_schedules(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        return [
            self._issue(rule, f"Workflow schedule metadata is not available for {row.get('workflow_name', '')}.", row.get("workflow_name", ""), row.get("file_name", ""))
            for row in self.tables.get("workflows", [])
            if "schedule" not in {key.lower() for key in row}
        ]

    def _missing_target_table_binding(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        target_names = {(row.get("file_name", ""), row.get("target_name", "")) for row in self.tables.get("targets", [])}
        issues: list[ValidationIssue] = []
        for row in self.tables.get("instances", []):
            if row.get("instance_type", "").upper() == "TARGET" and (row.get("file_name", ""), row.get("instance_name", "")) not in target_names:
                issues.append(self._issue(rule, f"Target instance {row.get('instance_name', '')} is not bound to a target definition.", row.get("instance_name", ""), row.get("file_name", "")))
        return issues

    def _name_length(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        max_length = int(rule["detection_logic"].get("max_length", 65))
        name_fields = ["folder_name", "mapping_name", "session_name", "workflow_name", "source_name", "target_name", "transformation_name", "instance_name", "column_name", "port_name"]
        issues: list[ValidationIssue] = []
        for table_name, rows in self.tables.items():
            for row in rows:
                for field in name_fields:
                    value = row.get(field, "")
                    if len(value) > max_length:
                        issues.append(self._issue(rule, f"{field} exceeds {max_length} characters in {table_name}.", value, row.get("file_name", "")))
        return issues

    def _missing_alias_in_concat(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        for row in [*self.tables.get("sql_overrides", []), *self.tables.get("ports", [])]:
            text = row.get("sql_query") or row.get("expression", "")
            if re.search(r"\bCONCAT\s*\(", text, re.IGNORECASE) and not re.search(r"\bAS\s+[A-Za-z_][A-Za-z0-9_]*", text, re.IGNORECASE):
                issues.append(self._issue(rule, "CONCAT expression appears without an explicit alias.", self._asset_name(row), row.get("file_name", "")))
        return issues

    def _schema_prefix_in_lookup(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        lookup_names = {
            (row.get("file_name", ""), row.get("mapping_name", ""), row.get("transformation_name", ""))
            for row in self.tables.get("transformations", [])
            if "LOOKUP" in row.get("transformation_type", "").upper()
        }
        issues: list[ValidationIssue] = []
        for row in self.tables.get("sql_overrides", []):
            key = (row.get("file_name", ""), row.get("mapping_name", ""), row.get("context_name", ""))
            if key in lookup_names and re.search(r"\b[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\b", row.get("sql_query", "")):
                issues.append(self._issue(rule, "Lookup SQL contains a hard-coded schema prefix.", row.get("context_name", ""), row.get("file_name", "")))
        return issues

    def _transformation_type(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        patterns = [re.compile(pattern, re.IGNORECASE) for pattern in rule["detection_logic"].get("patterns", [])]
        return [
            self._issue(rule, f"{rule['rule_name']} found: {row.get('transformation_name', '')}.", row.get("transformation_name", ""), row.get("file_name", ""))
            for row in self.tables.get("transformations", [])
            if any(pattern.search(row.get("transformation_type", "")) for pattern in patterns)
        ]

    def _shared_folder_dependency(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        return [
            self._issue(rule, f"Reusable asset dependency detected for {row.get('transformation_name', '')}.", row.get("transformation_name", ""), row.get("file_name", ""))
            for row in self.tables.get("transformations", [])
            if row.get("reusable_flag", "").upper() == "YES"
        ]

    def _snowflake_keyword_conflicts(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        keywords = {"ACCOUNT", "CURRENT_DATE", "CURRENT_TIMESTAMP", "DATABASE", "GROUP", "ILIKE", "QUALIFY", "SAMPLE", "SCHEMA", "TABLE"}
        rows = [*self.tables.get("source_columns", []), *self.tables.get("target_columns", []), *self.tables.get("ports", [])]
        issues: list[ValidationIssue] = []
        for row in rows:
            name = row.get("column_name") or row.get("port_name", "")
            if name.upper() in keywords:
                issues.append(self._issue(rule, f"Column or port name {name} conflicts with a Snowflake keyword.", name, row.get("file_name", "")))
        return issues

    def _field_unavailable(self, rule: dict[str, Any]) -> list[ValidationIssue]:
        required = set(rule["detection_logic"].get("required_fields", []))
        available = {field for rows in self.tables.values() for row in rows[:1] for field in row}
        missing = sorted(required - available)
        if not missing:
            return []
        return [
            self._issue(
                rule,
                f"Required metadata fields are unavailable for automated detection: {', '.join(missing)}.",
                "Metadata Repository",
                "",
            )
        ]

    def _load_or_build_datatype_findings(self) -> list[dict[str, str]]:
        report = self.output_folder / "datatype_mismatch_report.csv"
        if not report.exists():
            DatatypeHarmonizationEngine(config=self.config, logger=self.logger, output_folder=self.output_folder).harmonize()
        return self._read_csv(report) if report.exists() else []

    def _load_metadata_tables(self) -> dict[str, list[dict[str, str]]]:
        tables: dict[str, list[dict[str, str]]] = {}
        if not self.metadata_folder.exists():
            return tables
        for path in self.metadata_folder.glob("*.csv"):
            tables[path.stem] = self._read_csv(path)
        return tables

    def _load_rules(self) -> list[dict[str, Any]]:
        with self.rules_path.open("r", encoding="utf-8") as rules_file:
            payload = json.load(rules_file)
        return list(payload.get("rules", []))

    def _ports_by_transformation(self) -> dict[tuple[str, str, str, str, str], list[dict[str, str]]]:
        grouped: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
        for row in self.tables.get("ports", []):
            grouped[self._transformation_key(row)].append(row)
        return grouped

    @staticmethod
    def _select_columns(sql: str) -> list[str]:
        match = re.search(r"\bSELECT\b(.*?)\bFROM\b", sql or "", re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        select_list = match.group(1)
        columns: list[str] = []
        current: list[str] = []
        depth = 0
        for char in select_list:
            if char == "(":
                depth += 1
            elif char == ")" and depth:
                depth -= 1
            if char == "," and depth == 0:
                columns.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            columns.append("".join(current).strip())
        return [column for column in columns if column]

    @staticmethod
    def _transformation_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
        return (
            row.get("file_name", ""),
            row.get("repository_name", ""),
            row.get("folder_name", ""),
            row.get("mapping_name", ""),
            row.get("context_name") or row.get("transformation_name", ""),
        )

    @staticmethod
    def _asset_name(row: dict[str, str]) -> str:
        for field in ["mapping_name", "session_name", "workflow_name", "context_name", "transformation_name", "instance_name", "source_name", "target_name", "column_name", "port_name"]:
            if row.get(field):
                return row[field]
        return row.get("file_name", "Unknown Asset")

    @staticmethod
    def _normalize_name(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    def _issue(self, rule: dict[str, Any], issue: str, asset: str, source_file: str) -> ValidationIssue:
        return ValidationIssue(
            rule_id=rule["rule_id"],
            issue=issue,
            severity=rule["severity"],
            asset=asset or "Unknown Asset",
            recommendation=rule["recommendation"],
            category=rule.get("category", ""),
            source_file=source_file,
        )

    @staticmethod
    def _deduplicate(issues: Iterable[ValidationIssue]) -> list[ValidationIssue]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[ValidationIssue] = []
        for issue in issues:
            key = (issue.rule_id, issue.issue, issue.asset)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(issue)
        return deduped

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def build_validation_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    rules_path: str | Path | None = None,
) -> list[ValidationIssue]:
    return ValidationEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        rules_path=rules_path,
    ).validate()
