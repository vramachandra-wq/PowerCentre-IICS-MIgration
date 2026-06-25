from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from common.config.config import AppConfig


@dataclass(frozen=True)
class IssueRecord:
    mapping_name: str
    issue: str
    severity: str
    category: str
    status: str
    auto_fixed: bool = False
    approval_required: bool = False
    manual_remediation_required: bool = False
    source: str = ""


@dataclass(frozen=True)
class ReadinessRecord:
    mapping_name: str
    issues_found: int
    issues_auto_fixed: int
    issues_remaining: int
    readiness_before: int
    readiness_after: int
    readiness_category: str


class Day3ReportLoader:
    """Loads Day-1/Day-2 CSV artifacts into normalized issue records."""

    def __init__(
        self,
        output_folder: str | Path,
        scoring_rules_path: str | Path = "common/config/readiness_rules.json",
    ) -> None:
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(output_folder)
        self.scoring_rules_path = self._resolve_path(scoring_rules_path)
        self.rules = self._load_rules()
        self.mapping_names, self.xml_to_mapping = self._load_mapping_catalog()
        self.asset_to_mapping = self._load_asset_mapping_index()

    def load_before_issues(self) -> list[IssueRecord]:
        return [
            *self._load_datatype_issues(self.output_folder / "datatype_mismatch_report.csv"),
            *self._load_validation_issues(self.output_folder / "validation_report.csv"),
        ]

    def load_remediation_issues(self) -> list[IssueRecord]:
        path = self.output_folder / "remediation_report.csv"
        rows = self._read_csv(path)
        records: list[IssueRecord] = []
        for row in rows:
            issue = self.canonical_issue(row.get("Issue", ""))
            status = row.get("Status", "")
            records.append(
                IssueRecord(
                    mapping_name=self._mapping_from_row(row),
                    issue=issue,
                    severity=row.get("Severity", "MEDIUM").upper(),
                    category=self.issue_category(issue),
                    status=status,
                    auto_fixed=self._truthy(row.get("Auto Fixed")),
                    approval_required=self._truthy(row.get("Approval Required")) or status.lower() == "approval required",
                    manual_remediation_required=self._truthy(row.get("Manual Remediation Required"))
                    or "manual" in status.lower(),
                    source="remediation_report",
                )
            )
        return records

    def unresolved_issues(self) -> list[IssueRecord]:
        before = self.load_before_issues()
        remediation = self.load_remediation_issues()
        auto_fixed_counts: dict[tuple[str, str], int] = {}
        for issue in remediation:
            if issue.auto_fixed or issue.status.lower() == "resolved":
                key = (issue.mapping_name, issue.issue)
                auto_fixed_counts[key] = auto_fixed_counts.get(key, 0) + 1

        remaining: list[IssueRecord] = []
        for issue in before:
            key = (issue.mapping_name, issue.issue)
            if auto_fixed_counts.get(key, 0) > 0:
                auto_fixed_counts[key] -= 1
                continue
            remaining.append(issue)
        return remaining

    def issue_category(self, issue: str) -> str:
        risk_factor = self.rules.get("risk_factors", {}).get(issue)
        if risk_factor:
            return str(risk_factor.get("category", "metadata"))
        if any(token in issue for token in ["datatype", "precision", "scale", "unicode", "truncation"]):
            return "datatype"
        if any(token in issue for token in ["sql", "query", "alias", "function", "brace"]):
            return "sql"
        if any(token in issue for token in ["connection", "parameter", "binding", "schema", "runtime"]):
            return "runtime"
        if any(token in issue for token in ["transformation", "lookup", "mapplet", "sequence", "java"]):
            return "transformation"
        if any(token in issue for token in ["cdc", "pushdown", "dll", "sap", "mainframe"]):
            return "manual"
        return "metadata"

    def score_readiness(self, issues: Iterable[IssueRecord]) -> int:
        base_score = int(self.rules.get("base_score", 100))
        severity_penalties = self.rules.get("severity_penalties", {})
        multipliers = self.rules.get("category_penalty_multipliers", {})
        penalty = 0.0
        for issue in issues:
            severity_penalty = float(severity_penalties.get(issue.severity.upper(), 5))
            multiplier = float(multipliers.get(issue.category, 1.0))
            penalty += severity_penalty * multiplier
        return max(0, min(100, round(base_score - penalty)))

    def readiness_category(self, score: int) -> str:
        for band in self.rules.get("readiness_categories", []):
            if int(band["min"]) <= score <= int(band["max"]):
                return str(band["category"])
        return "HIGH RISK"

    def canonical_issue(self, text: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "_", str(text or "").lower()).strip("_")
        aliases = {
            "decimal_precision_mismatch": "precision_mismatch",
            "scale_mismatch_detected": "scale_mismatch",
            "string_truncation_issue": "truncation_risk",
            "varchar2_to_nvarchar2_conversion": "unicode_mismatch",
            "missing_target_table_binding": "target_binding_issue",
            "physical_connection_mandatory_issue": "missing_connection",
            "parameter_file_conversion_issue": "parameter_file_issue",
            "oracle_curly_brace_syntax": "oracle_curly_brace_syntax",
            "post_sql_incompatibility": "unsupported_sql",
            "session_sql_override_precedence_issue": "sql_override_conflict",
            "mapping_sql_override_precedence_issue": "sql_override_conflict",
            "source_query_column_count_mismatch": "source_query_mismatch",
            "source_query_column_order_mismatch": "source_query_mismatch",
            "stored_procedure_transformation": "stored_procedure_transformation",
            "dynamic_lookup": "dynamic_lookup",
            "sequence_generator": "sequence_generator",
            "missing_command_task_conversion": "os_command_task",
        }
        for key, canonical in aliases.items():
            if key in value:
                return canonical
        sentence_aliases = [
            ("physical_connection_metadata_is_missing", "missing_connection"),
            ("target_instance", "target_binding_issue"),
            ("not_bound_to_a_target_definition", "target_binding_issue"),
            ("parameter_file", "parameter_file_issue"),
            ("datetime_parameter_format_conversion", "datetime_format_conversion"),
            ("concat_expression_appears_without", "missing_alias"),
            ("hard_coded_schema_prefix", "schema_prefix_issue"),
            ("source_query_selected", "source_query_mismatch"),
            ("select_list_order_differs", "source_query_mismatch"),
            ("oracle_curly_brace_syntax_detected", "oracle_curly_brace_syntax"),
            ("post_sql_incompatibility_detected", "unsupported_sql"),
            ("stored_procedure_transformation_found", "stored_procedure_transformation"),
            ("java_transformation_found", "java_transformation"),
            ("mapplet_nesting_detected", "mapplet_nesting"),
            ("dll_dependency_detected", "dll_dependency"),
            ("pushdown_optimization_detected", "pushdown_optimization"),
            ("cdc_detected", "cdc"),
        ]
        for token, canonical in sentence_aliases:
            if token in value:
                return canonical
        if "precision_mismatch" in value:
            return "precision_mismatch"
        if "scale_mismatch" in value:
            return "scale_mismatch"
        if "lookup_datatype_mismatch" in value:
            return "lookup_datatype_mismatch"
        if "native_precision_mismatch" in value:
            return "native_precision_mismatch"
        if "unicode_mismatch" in value:
            return "unicode_mismatch"
        if "truncation_risk" in value:
            return "truncation_risk"
        if "schema_prefix" in value:
            return "schema_prefix_issue"
        if "target_binding" in value:
            return "target_binding_issue"
        if "java_transformation" in value:
            return "java_transformation"
        if "mapplet_nesting" in value:
            return "mapplet_nesting"
        if "pushdown_optimization" in value:
            return "pushdown_optimization"
        if "dll_dependency" in value:
            return "dll_dependency"
        return value

    def _load_datatype_issues(self, path: Path) -> list[IssueRecord]:
        records: list[IssueRecord] = []
        for row in self._read_csv(path):
            issue = self.canonical_issue(row.get("issue_type", "datatype_mismatch"))
            records.append(
                IssueRecord(
                    mapping_name=self._mapping_from_row(row),
                    issue=issue,
                    severity=row.get("severity", "MEDIUM").upper(),
                    category=self.issue_category(issue),
                    status="Open",
                    source="datatype_mismatch_report",
                )
            )
        return records

    def _load_validation_issues(self, path: Path) -> list[IssueRecord]:
        records: list[IssueRecord] = []
        for row in self._read_csv(path):
            issue = self.canonical_issue(row.get("Issue", ""))
            status = row.get("Status", "Open") or "Open"
            records.append(
                IssueRecord(
                    mapping_name=self._mapping_from_row(row),
                    issue=issue,
                    severity=row.get("Severity", "MEDIUM").upper(),
                    category=self.issue_category(issue),
                    status=status,
                    auto_fixed=self._truthy(row.get("Auto Fixed")),
                    source="validation_report",
                )
            )
        return records

    def _mapping_from_row(self, row: dict[str, str]) -> str:
        for field in ["mapping_name", "Mapping Name", "transformation"]:
            if row.get(field):
                mapped = self._resolve_mapping_name(row[field])
                if mapped:
                    return mapped
        source_file = row.get("source_file") or row.get("Source File") or row.get("file_name") or ""
        if source_file:
            mapped = self.xml_to_mapping.get(Path(source_file).name) or self.xml_to_mapping.get(Path(source_file).stem)
            if mapped:
                return mapped
        for field in ["Asset", "Asset Name"]:
            if row.get(field):
                mapped = self._resolve_mapping_name(row[field])
                if mapped:
                    return mapped
        return sorted(self.mapping_names)[0] if self.mapping_names else "UNMAPPED_ASSET"

    def _resolve_mapping_name(self, value: str) -> str:
        cleaned = self._clean_mapping_name(value)
        if not self.mapping_names:
            return cleaned
        if cleaned in self.mapping_names:
            return cleaned
        return self.asset_to_mapping.get(self._normalize_name(cleaned), "")

    def _load_mapping_catalog(self) -> tuple[set[str], dict[str, str]]:
        path = self.output_folder / "complexity_classification_report.csv"
        mapping_names: set[str] = set()
        xml_to_mapping: dict[str, str] = {}
        for row in self._read_csv(path):
            mapping = row.get("Mapping", "")
            xml_name = row.get("XML", "")
            if not mapping:
                continue
            mapping_names.add(mapping)
            if xml_name:
                xml_to_mapping[Path(xml_name).name] = mapping
                xml_to_mapping[Path(xml_name).stem] = mapping
        return mapping_names, xml_to_mapping

    def _load_asset_mapping_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        metadata_folder = self.output_folder / "metadata_tables"
        if not metadata_folder.exists():
            return index

        table_asset_fields = {
            "source_columns.csv": ["source_name", "column_name"],
            "target_columns.csv": ["target_name", "column_name"],
            "sources.csv": ["source_name"],
            "targets.csv": ["target_name"],
            "transformations.csv": ["mapping_name", "transformation_name"],
            "ports.csv": ["mapping_name", "transformation_name", "port_name"],
            "instances.csv": ["mapping_name", "instance_name", "transformation_name"],
            "sql_overrides.csv": ["mapping_name", "context_name", "parent_name"],
            "sessions.csv": ["mapping_name", "session_name"],
        }
        for file_name, asset_fields in table_asset_fields.items():
            for row in self._read_csv(metadata_folder / file_name):
                mapping = row.get("mapping_name", "")
                if not mapping:
                    source_file = row.get("file_name", "")
                    mapping = self.xml_to_mapping.get(Path(source_file).name, "")
                if mapping not in self.mapping_names:
                    continue
                for field in asset_fields:
                    if row.get(field):
                        index.setdefault(self._normalize_name(row[field]), mapping)
        return index

    @staticmethod
    def _clean_mapping_name(value: str) -> str:
        cleaned = str(value or "").strip()
        if cleaned.lower().endswith(".xml"):
            return Path(cleaned).stem
        return cleaned or "UNMAPPED_ASSET"

    @staticmethod
    def _normalize_name(value: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    @staticmethod
    def _truthy(value: object) -> bool:
        return str(value or "").strip().lower() in {"true", "yes", "y", "1", "resolved"}

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    def _load_rules(self) -> dict[str, Any]:
        with self.scoring_rules_path.open("r", encoding="utf-8") as rules_file:
            return json.load(rules_file)

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


class MigrationReadinessEngine:
    """Calculates before/after migration readiness using unresolved issue penalties only."""

    REPORT_COLUMNS = [
        "mapping_name",
        "issues_found",
        "issues_auto_fixed",
        "issues_remaining",
        "readiness_before",
        "readiness_after",
        "readiness_category",
    ]

    def __init__(
        self,
        config: AppConfig | None = None,
        logger=None,
        output_folder: str | Path | None = None,
        scoring_rules_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.logger = logger
        configured_output = output_folder or (config.paths.output_folder if config else "output")
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(configured_output)
        self.report_path = self.output_folder / "migration_readiness_report.csv"
        self.loader = Day3ReportLoader(
            self.output_folder,
            scoring_rules_path or Path("common/config/readiness_rules.json"),
        )

    def build_report(self) -> list[ReadinessRecord]:
        before = self.loader.load_before_issues()
        remaining = self.loader.unresolved_issues()
        remediation = self.loader.load_remediation_issues()
        mappings = sorted(
            self.loader.mapping_names
            or {issue.mapping_name for issue in [*before, *remaining, *remediation]}
            or {"UNMAPPED_ASSET"}
        )

        records: list[ReadinessRecord] = []
        for mapping in mappings:
            before_for_mapping = [issue for issue in before if issue.mapping_name == mapping]
            remaining_for_mapping = [issue for issue in remaining if issue.mapping_name == mapping]
            auto_fixed = [
                issue
                for issue in remediation
                if issue.mapping_name == mapping and (issue.auto_fixed or issue.status.lower() == "resolved")
            ]
            readiness_before = self.loader.score_readiness(before_for_mapping)
            readiness_after = self.loader.score_readiness(remaining_for_mapping)
            records.append(
                ReadinessRecord(
                    mapping_name=mapping,
                    issues_found=len(before_for_mapping),
                    issues_auto_fixed=len(auto_fixed),
                    issues_remaining=len(remaining_for_mapping),
                    readiness_before=readiness_before,
                    readiness_after=readiness_after,
                    readiness_category=self.loader.readiness_category(readiness_after),
                )
            )
        self.write_report(records)
        if self.logger:
            self.logger.info("Migration readiness report written to %s. rows=%s", self.report_path, len(records))
        return records

    def write_report(self, records: list[ReadinessRecord], report_path: str | Path | None = None) -> None:
        path = self._resolve_path(report_path or self.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            csv_file = path.open("w", newline="", encoding="utf-8")
        except PermissionError:
            fallback_path = path.with_name(f"{path.stem}_latest{path.suffix}")
            csv_file = fallback_path.open("w", newline="", encoding="utf-8")
        with csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(record.__dict__ for record in records)

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def build_migration_readiness_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    scoring_rules_path: str | Path | None = None,
) -> list[ReadinessRecord]:
    return MigrationReadinessEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        scoring_rules_path=scoring_rules_path,
    ).build_report()
