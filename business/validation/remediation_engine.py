from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from business.validation.datatype_harmonization import DatatypeHarmonizationEngine, MetadataColumn
from business.validation.validation_engine import ValidationEngine, ValidationIssue
from common.config.config import AppConfig


@dataclass(frozen=True)
class RemediationResult:
    issue: str
    severity: str
    recommendation: str
    auto_fixed: bool
    fix_applied: str
    before_value: str
    after_value: str
    status: str
    asset: str = ""
    manual_remediation_required: bool = False
    approval_required: bool = False
    original_sql: str = ""
    proposed_sql: str = ""


@dataclass(frozen=True)
class RevalidationSummary:
    before_fix_issues: int
    after_fix_issues: int
    resolved_issues: int


class RemediationEngine:
    """Applies deterministic Day-2 remediation rules and revalidates remediated metadata."""

    REPORT_COLUMNS = [
        "Issue",
        "Severity",
        "Recommendation",
        "Auto Fixed",
        "Fix Applied",
        "Before Value",
        "After Value",
        "Status",
        "Asset",
        "Manual Remediation Required",
        "Approval Required",
        "Original SQL",
        "Proposed SQL",
    ]
    REVALIDATION_COLUMNS = ["Before Fix Issues", "After Fix Issues", "Resolved Issues"]

    def __init__(
        self,
        config: AppConfig | None = None,
        logger=None,
        output_folder: str | Path | None = None,
        validation_rules_path: str | Path | None = None,
        remediation_rules_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        configured_output = output_folder or (config.paths.output_folder if config else "output")
        self.output_folder = self._resolve_path(configured_output)
        self.metadata_folder = self.output_folder / "metadata_tables"
        self.validation_rules_path = validation_rules_path
        self.rules_path = self._resolve_path(remediation_rules_path or Path("common/config/remediation_rules.json"))
        self.validation_report_path = self.output_folder / "validation_report.csv"
        self.remediation_report_path = self.output_folder / "remediation_report.csv"
        self.revalidation_report_path = self.output_folder / "revalidation_report.csv"
        self.remediated_metadata_path = self.output_folder / "remediated_metadata.json"
        self.rules = self._load_rules()
        self.tables: dict[str, list[dict[str, str]]] = {}
        self.results: list[RemediationResult] = []

    def remediate(self) -> tuple[list[RemediationResult], RevalidationSummary]:
        validator = ValidationEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
            rules_path=self.validation_rules_path,
        )
        before_issues = self._validate_without_writing(validator)
        self.tables = deepcopy(validator.tables)
        datatype_findings = validator.datatype_findings

        self.results = []
        self.results.extend(self._remediate_datatype_findings(datatype_findings))
        self.results.extend(self._remediate_validation_issues(before_issues))

        self._write_remediated_metadata()
        after_issues = self._revalidate_tables()
        summary = RevalidationSummary(
            before_fix_issues=len(before_issues),
            after_fix_issues=len(after_issues),
            resolved_issues=max(len(before_issues) - len(after_issues), 0),
        )
        self.write_remediation_report(self.results)
        self.write_revalidation_report(summary)
        if self.logger:
            self.logger.info(
                "Remediation complete. before=%s after=%s report=%s",
                summary.before_fix_issues,
                summary.after_fix_issues,
                self.remediation_report_path,
            )
        return self.results, summary

    @staticmethod
    def _validate_without_writing(validator: ValidationEngine) -> list[ValidationIssue]:
        validator.tables = validator._load_metadata_tables()
        validator.datatype_findings = validator._load_or_build_datatype_findings()
        issues: list[ValidationIssue] = []
        for rule in validator.rules:
            issues.extend(validator._evaluate_rule(rule))
        return validator._deduplicate(issues)

    def write_remediation_report(
        self, results: list[RemediationResult], report_path: str | Path | None = None
    ) -> None:
        path = self._resolve_path(report_path or self.remediation_report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.REPORT_COLUMNS)
            writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        "Issue": result.issue,
                        "Severity": result.severity,
                        "Recommendation": result.recommendation,
                        "Auto Fixed": str(result.auto_fixed),
                        "Fix Applied": result.fix_applied,
                        "Before Value": result.before_value,
                        "After Value": result.after_value,
                        "Status": result.status,
                        "Asset": result.asset,
                        "Manual Remediation Required": str(result.manual_remediation_required),
                        "Approval Required": str(result.approval_required),
                        "Original SQL": result.original_sql,
                        "Proposed SQL": result.proposed_sql,
                    }
                )

    def write_revalidation_report(
        self, summary: RevalidationSummary, report_path: str | Path | None = None
    ) -> None:
        path = self._resolve_path(report_path or self.revalidation_report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.REVALIDATION_COLUMNS)
            writer.writeheader()
            writer.writerow(
                {
                    "Before Fix Issues": summary.before_fix_issues,
                    "After Fix Issues": summary.after_fix_issues,
                    "Resolved Issues": summary.resolved_issues,
                }
            )

    def _remediate_datatype_findings(self, findings: list[dict[str, str]]) -> list[RemediationResult]:
        results: list[RemediationResult] = []
        for finding in findings:
            issue = self._canonical_issue(finding.get("issue_type", ""))
            rule = self.rules["auto"].get(issue)
            if not rule:
                continue

            before = finding.get("target", "")
            target_row = self._find_target_column(finding)
            source_row = self._find_source_column(finding)
            if not target_row or not source_row:
                results.append(self._result(finding, issue, False, "", before, before, "Not Applied"))
                continue

            changed = self._apply_column_action(rule["action"], source_row, target_row)
            after = self._column_type_display(target_row)
            results.append(
                self._result(
                    finding,
                    issue,
                    changed,
                    rule["action"] if changed else "",
                    before,
                    after,
                    "Resolved" if changed else "No Change Required",
                )
            )
        return results

    def _remediate_validation_issues(self, issues: list[ValidationIssue]) -> list[RemediationResult]:
        results: list[RemediationResult] = []
        for issue in issues:
            canonical = self._canonical_issue(issue.issue, issue.rule_id)
            if canonical in self.rules["manual"]:
                results.append(
                    RemediationResult(
                        issue=canonical,
                        severity=issue.severity,
                        recommendation=issue.recommendation,
                        auto_fixed=False,
                        fix_applied="",
                        before_value=issue.asset,
                        after_value=issue.asset,
                        status="Manual Remediation Required",
                        asset=issue.asset,
                        manual_remediation_required=True,
                    )
                )
                continue
            if canonical in self.rules["semi"]:
                original_sql, proposed_sql = self._propose_sql_fix(canonical, issue.asset)
                results.append(
                    RemediationResult(
                        issue=canonical,
                        severity=issue.severity,
                        recommendation=issue.recommendation,
                        auto_fixed=False,
                        fix_applied=self.rules["semi"][canonical]["action"],
                        before_value=original_sql,
                        after_value=proposed_sql,
                        status="Approval Required",
                        asset=issue.asset,
                        approval_required=True,
                        original_sql=original_sql,
                        proposed_sql=proposed_sql,
                    )
                )
                continue
            rule = self.rules["auto"].get(canonical)
            if not rule:
                continue
            changed, before, after = self._apply_metadata_action(rule["action"], issue)
            results.append(
                RemediationResult(
                    issue=canonical,
                    severity=issue.severity,
                    recommendation=issue.recommendation,
                    auto_fixed=changed,
                    fix_applied=rule["action"] if changed else "",
                    before_value=before,
                    after_value=after,
                    status="Resolved" if changed else "Not Applied",
                    asset=issue.asset,
                )
            )
        return results

    def _apply_column_action(
        self, action: str, source_row: dict[str, str], target_row: dict[str, str]
    ) -> bool:
        before = dict(target_row)
        if action in {"copy_source_precision", "expand_target_capacity"} and source_row.get("precision"):
            target_row["precision"] = source_row["precision"]
        if action in {"copy_source_scale", "expand_target_capacity"} and source_row.get("scale"):
            target_row["scale"] = source_row["scale"]
        if action in {"copy_source_length", "restore_original_length"} and source_row.get("precision"):
            target_row["precision"] = source_row["precision"]
        if action in {"standardize_unicode_string", "align_lookup_datatype"}:
            target_row["datatype"] = source_row.get("datatype", target_row.get("datatype", ""))
            if source_row.get("precision"):
                target_row["precision"] = source_row["precision"]
            if source_row.get("scale"):
                target_row["scale"] = source_row["scale"]
        if action == "copy_source_nullability" and "nullable" in source_row:
            target_row["nullable"] = source_row.get("nullable", "")
        if action == "copy_source_default_value" and "default_value" in source_row:
            target_row["default_value"] = source_row.get("default_value", "")
        return before != target_row

    def _apply_metadata_action(self, action: str, issue: ValidationIssue) -> tuple[bool, str, str]:
        if action == "add_concat_alias":
            return self._add_concat_alias(issue.asset)
        if action == "add_schema_prefix":
            return self._normalize_schema_prefix(issue.asset)
        if action == "deduplicate_column_names":
            return self._deduplicate_columns(issue.asset)
        if action == "add_missing_target_binding_metadata":
            return self._add_target_binding(issue.asset)
        if action == "convert_datetime_format":
            return self._convert_datetime_formats(issue.asset)
        return False, issue.asset, issue.asset

    def _add_concat_alias(self, asset: str) -> tuple[bool, str, str]:
        changed = False
        before_values: list[str] = []
        after_values: list[str] = []
        for table_name, field in [("sql_overrides", "sql_query"), ("ports", "expression")]:
            for row in self.tables.get(table_name, []):
                text = row.get(field, "")
                if asset and asset not in {self._asset_name(row), row.get("context_name", "")}:
                    continue
                if re.search(r"\bCONCAT\s*\(", text, re.IGNORECASE) and not re.search(
                    r"\bAS\s+[A-Za-z_][A-Za-z0-9_]*", text, re.IGNORECASE
                ):
                    proposed = re.sub(
                        r"(CONCAT\s*\([^)]*\))(?!\s+AS\b)",
                        r"\1 AS CONCAT_VALUE",
                        text,
                        count=1,
                        flags=re.IGNORECASE,
                    )
                    before_values.append(text)
                    after_values.append(proposed)
                    row[field] = proposed
                    changed = True
        return changed, "\n".join(before_values), "\n".join(after_values)

    def _normalize_schema_prefix(self, asset: str) -> tuple[bool, str, str]:
        changed = False
        before_values: list[str] = []
        after_values: list[str] = []
        for row in self.tables.get("sql_overrides", []):
            if asset and asset not in {row.get("context_name", ""), self._asset_name(row)}:
                continue
            sql = row.get("sql_query", "")
            proposed = re.sub(
                r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
                r"FROM $$SCHEMA_PREFIX.\2",
                sql,
                flags=re.IGNORECASE,
            )
            if proposed != sql:
                before_values.append(sql)
                after_values.append(proposed)
                row["sql_query"] = proposed
                changed = True
        return changed, "\n".join(before_values), "\n".join(after_values)

    def _deduplicate_columns(self, asset: str) -> tuple[bool, str, str]:
        changed = False
        before_values: list[str] = []
        after_values: list[str] = []
        for table_name, asset_field in [("source_columns", "source_name"), ("target_columns", "target_name")]:
            seen: dict[tuple[str, str, str], int] = {}
            for row in self.tables.get(table_name, []):
                if asset and row.get(asset_field, "") != asset:
                    continue
                key = (
                    row.get("file_name", ""),
                    row.get(asset_field, ""),
                    self._normalize_name(row.get("column_name", "")),
                )
                seen[key] = seen.get(key, 0) + 1
                if seen[key] > 1:
                    before_values.append(row.get("column_name", ""))
                    row["column_name"] = f"{row.get('column_name', '')}_{seen[key]}"
                    after_values.append(row["column_name"])
                    changed = True
        return changed, ", ".join(before_values), ", ".join(after_values)

    def _add_target_binding(self, asset: str) -> tuple[bool, str, str]:
        target_names = {(row.get("file_name", ""), row.get("target_name", "")) for row in self.tables.get("targets", [])}
        for row in self.tables.get("instances", []):
            if row.get("instance_type", "").upper() != "TARGET" or row.get("instance_name", "") != asset:
                continue
            key = (row.get("file_name", ""), row.get("instance_name", ""))
            if key in target_names:
                return False, asset, asset
            new_target = {
                "file_name": row.get("file_name", ""),
                "repository_name": row.get("repository_name", ""),
                "folder_name": row.get("folder_name", ""),
                "target_name": row.get("instance_name", ""),
                "database_type": "",
                "connection_name": "",
                "binding_status": "ADDED_BY_REMEDIATION",
            }
            self.tables.setdefault("targets", []).append(new_target)
            return True, "missing", json.dumps(new_target, sort_keys=True)
        return False, asset, asset

    def _convert_datetime_formats(self, asset: str) -> tuple[bool, str, str]:
        changed = False
        before_values: list[str] = []
        after_values: list[str] = []
        replacements = {
            "YYYY": "yyyy",
            "DD": "dd",
            "HH24": "HH",
            "MI": "mm",
            "SS": "ss",
        }
        for row in self.tables.get("sql_overrides", []):
            if asset and asset not in {row.get("context_name", ""), row.get("mapping_name", ""), self._asset_name(row)}:
                continue
            sql = row.get("sql_query", "")
            proposed = sql
            for old, new in replacements.items():
                proposed = re.sub(old, new, proposed)
            if proposed != sql:
                before_values.append(sql)
                after_values.append(proposed)
                row["sql_query"] = proposed
                changed = True
        return changed, "\n".join(before_values), "\n".join(after_values)

    def _propose_sql_fix(self, canonical: str, asset: str) -> tuple[str, str]:
        for row in self.tables.get("sql_overrides", []):
            if asset and asset not in {row.get("context_name", ""), row.get("mapping_name", ""), self._asset_name(row)}:
                continue
            sql = row.get("sql_query", "")
            if not sql:
                continue
            proposed = sql
            if canonical == "oracle_curly_brace_syntax":
                proposed = re.sub(r"\{([^}]+)\}", r"\1", proposed)
            elif canonical == "unsupported_database_functions":
                proposed = re.sub(r"\bNVL\s*\(", "COALESCE(", proposed, flags=re.IGNORECASE)
                proposed = re.sub(r"\bSYSDATE\b", "CURRENT_TIMESTAMP", proposed, flags=re.IGNORECASE)
            elif canonical == "post_sql_statements":
                proposed = "-- Review connector support before enabling:\n" + proposed
            elif canonical == "source_query_mismatch":
                proposed = self._ordered_select_projection(row, proposed)
            return sql, proposed
        return "", ""

    def _ordered_select_projection(self, row: dict[str, str], sql: str) -> str:
        ports = [
            port.get("port_name", "")
            for port in self.tables.get("ports", [])
            if self._transformation_key(port) == self._transformation_key(row)
        ]
        if not ports or not re.search(r"\bSELECT\b.*?\bFROM\b", sql, re.IGNORECASE | re.DOTALL):
            return sql
        return re.sub(
            r"(\bSELECT\b).*?(\bFROM\b)",
            rf"\1 {', '.join(ports)} \2",
            sql,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )

    def _revalidate_tables(self) -> list[ValidationIssue]:
        validator = ValidationEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
            rules_path=self.validation_rules_path,
        )
        validator.tables = deepcopy(self.tables)
        validator.datatype_findings = [asdict(finding) for finding in self._build_datatype_findings()]
        issues: list[ValidationIssue] = []
        for rule in validator.rules:
            issues.extend(validator._evaluate_rule(rule))
        return validator._deduplicate(issues)

    def _build_datatype_findings(self) -> list[Any]:
        harmonizer = DatatypeHarmonizationEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
        )
        sources = self._metadata_columns("source_columns", "SOURCE")
        targets = self._metadata_columns("target_columns", "TARGET")
        ports = self._ports()
        return harmonizer._deduplicate(
            [
                *harmonizer.compare_source_target(sources, targets),
                *harmonizer.compare_transformation_metadata(sources, targets, ports),
            ]
        )

    def _metadata_columns(self, table_name: str, table_type: str) -> list[MetadataColumn]:
        name_key = "source_name" if table_type == "SOURCE" else "target_name"
        return [
            MetadataColumn(
                column=row.get("column_name", ""),
                datatype=row.get("datatype", ""),
                precision=self._to_int(row.get("precision")),
                scale=self._to_int(row.get("scale")),
                table_name=row.get(name_key, ""),
                table_type=table_type,
                source_file=row.get("file_name", ""),
                repository_name=row.get("repository_name", ""),
                folder_name=row.get("folder_name", ""),
            )
            for row in self.tables.get(table_name, [])
        ]

    def _ports(self) -> list[MetadataColumn]:
        transformation_types = {
            (
                row.get("file_name", ""),
                row.get("repository_name", ""),
                row.get("folder_name", ""),
                row.get("mapping_name", ""),
                row.get("transformation_name", ""),
            ): row.get("transformation_type", "")
            for row in self.tables.get("transformations", [])
        }
        return [
            MetadataColumn(
                column=row.get("port_name", ""),
                datatype=row.get("datatype", ""),
                precision=self._to_int(row.get("precision")),
                scale=self._to_int(row.get("scale")),
                table_type=row.get("port_scope", "TRANSFORMATION"),
                mapping_name=row.get("mapping_name", ""),
                transformation_name=row.get("transformation_name", ""),
                transformation_type=transformation_types.get(self._transformation_key(row), ""),
                source_file=row.get("file_name", ""),
                repository_name=row.get("repository_name", ""),
                folder_name=row.get("folder_name", ""),
            )
            for row in self.tables.get("ports", [])
        ]

    def _write_remediated_metadata(self) -> None:
        payload = {
            "version": "1.0",
            "source": "PowerCenter metadata_tables",
            "remediation_summary": {
                "auto_fixed": sum(1 for result in self.results if result.auto_fixed),
                "approval_required": sum(1 for result in self.results if result.approval_required),
                "manual_remediation_required": sum(
                    1 for result in self.results if result.manual_remediation_required
                ),
            },
            "metadata_tables": self.tables,
        }
        self.remediated_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        with self.remediated_metadata_path.open("w", encoding="utf-8") as json_file:
            json.dump(payload, json_file, indent=2)

    def _find_source_column(self, finding: dict[str, str]) -> dict[str, str] | None:
        return self._find_column("source_columns", "source_name", finding)

    def _find_target_column(self, finding: dict[str, str]) -> dict[str, str] | None:
        return self._find_column("target_columns", "target_name", finding)

    def _find_column(self, table_name: str, asset_field: str, finding: dict[str, str]) -> dict[str, str] | None:
        source_file = finding.get("source_file", "")
        column = self._normalize_name(finding.get("column", ""))
        for row in self.tables.get(table_name, []):
            if source_file and row.get("file_name", "") != source_file:
                continue
            if self._normalize_name(row.get("column_name", "")) == column:
                return row
        return None

    def _result(
        self,
        finding: dict[str, str],
        issue: str,
        auto_fixed: bool,
        fix_applied: str,
        before: str,
        after: str,
        status: str,
    ) -> RemediationResult:
        return RemediationResult(
            issue=issue,
            severity=finding.get("severity", "MEDIUM"),
            recommendation=finding.get("recommendation", ""),
            auto_fixed=auto_fixed,
            fix_applied=fix_applied,
            before_value=before,
            after_value=after,
            status=status,
            asset=self._finding_asset(finding),
        )

    def _load_rules(self) -> dict[str, dict[str, Any]]:
        with self.rules_path.open("r", encoding="utf-8") as rules_file:
            payload = json.load(rules_file)
        return {
            "auto": {rule["issue"]: rule for rule in payload.get("auto_fix_rules", [])},
            "semi": {rule["issue"]: rule for rule in payload.get("semi_automatic_rules", [])},
            "manual": {rule["issue"]: rule for rule in payload.get("manual_rules", [])},
        }

    @staticmethod
    def _canonical_issue(text: str, rule_id: str = "") -> str:
        by_rule = {
            "VAL-001": "sql_override",
            "VAL-002": "sql_override",
            "VAL-003": "datetime_format_conversion",
            "VAL-004": "varchar_precision_doubling",
            "VAL-005": "post_sql_statements",
            "VAL-006": "parameter_file_issue",
            "VAL-008": "lookup_datatype_mismatch",
            "VAL-009": "native_precision_mismatch",
            "VAL-010": "truncation_risk",
            "VAL-011": "precision_mismatch",
            "VAL-012": "scale_mismatch",
            "VAL-013": "source_query_mismatch",
            "VAL-014": "source_query_mismatch",
            "VAL-015": "duplicate_column_names",
            "VAL-017": "target_binding_issue",
            "VAL-018": "oracle_curly_brace_syntax",
            "VAL-020": "clob_to_text_conversion",
            "VAL-021": "missing_alias",
            "VAL-022": "schema_prefix_issue",
            "VAL-023": "unicode_mismatch",
            "VAL-024": "os_command_task",
            "VAL-025": "stored_procedure_transformation",
            "VAL-028": "mapplet_nesting",
            "VAL-030": "cdc",
            "VAL-031": "pushdown_optimization",
            "VAL-032": "java_transformation",
            "VAL-033": "dll_dependency",
        }
        if rule_id in by_rule:
            return by_rule[rule_id]
        normalized = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
        aliases = {
            "varchar2_to_nvarchar2_conversion": "varchar_vs_nvarchar",
            "missing_alias_in_concat_expression": "missing_alias",
            "schema_prefix_issue_in_lookup": "schema_prefix_issue",
            "missing_target_table_binding": "target_binding_issue",
            "decimal_precision_mismatch": "precision_mismatch",
            "string_truncation_issue": "truncation_risk",
        }
        return aliases.get(normalized, normalized)

    @staticmethod
    def _finding_asset(finding: dict[str, str]) -> str:
        for field in ["mapping_name", "transformation", "source_file", "file_name"]:
            if finding.get(field):
                value = finding[field]
                return Path(value).stem if value.lower().endswith(".xml") else value
        return finding.get("column", "")

    @staticmethod
    def _column_type_display(row: dict[str, str]) -> str:
        datatype = row.get("datatype", "")
        precision = row.get("precision", "")
        scale = row.get("scale", "")
        if precision and scale:
            return f"{datatype.upper()}({precision},{scale})"
        if precision:
            return f"{datatype.upper()}({precision})"
        return datatype.upper()

    @staticmethod
    def _asset_name(row: dict[str, str]) -> str:
        for field in [
            "mapping_name",
            "session_name",
            "workflow_name",
            "context_name",
            "transformation_name",
            "instance_name",
            "source_name",
            "target_name",
            "column_name",
            "port_name",
        ]:
            if row.get(field):
                return row[field]
        return row.get("file_name", "Unknown Asset")

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
    def _normalize_name(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    @staticmethod
    def _to_int(value: object) -> int | None:
        if value in {None, ""}:
            return None
        try:
            return int(str(value).strip())
        except ValueError:
            return None

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def build_remediation_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    validation_rules_path: str | Path | None = None,
    remediation_rules_path: str | Path | None = None,
) -> tuple[list[RemediationResult], RevalidationSummary]:
    return RemediationEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        validation_rules_path=validation_rules_path,
        remediation_rules_path=remediation_rules_path,
    ).remediate()
