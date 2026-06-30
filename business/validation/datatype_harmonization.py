from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from business.validation.datatype_mapping_engine import DatatypeMappingEngine, DatatypeSpec
from common.config.config import AppConfig


@dataclass(frozen=True)
class MetadataColumn:
    column: str
    datatype: str
    precision: int | None
    scale: int | None
    table_name: str = ""
    table_type: str = ""
    mapping_name: str = ""
    transformation_name: str = ""
    transformation_type: str = ""
    source_file: str = ""
    repository_name: str = ""
    folder_name: str = ""


@dataclass(frozen=True)
class DatatypeMismatch:
    column: str
    source: str
    target: str
    severity: str
    recommendation: str
    issue_type: str
    transformation: str = ""
    mapping_name: str = ""
    source_file: str = ""


class DatatypeHarmonizationEngine:
    """Compares source, target, and transformation metadata using JSON datatype rules."""

    REPORT_COLUMNS = [
        "column",
        "source",
        "target",
        "severity",
        "recommendation",
        "issue_type",
        "transformation",
        "mapping_name",
        "source_file",
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
        self.report_path = self.output_folder / "datatype_mismatch_report.csv"
        self.mapping_engine = DatatypeMappingEngine(rules_path=rules_path)

    def harmonize(self) -> list[DatatypeMismatch]:
        source_columns = self._load_columns(self.metadata_folder / "source_columns.csv", "SOURCE")
        target_columns = self._load_columns(self.metadata_folder / "target_columns.csv", "TARGET")
        transformation_columns = self._load_ports(self.metadata_folder / "ports.csv")

        findings: list[DatatypeMismatch] = []
        findings.extend(self.compare_source_target(source_columns, target_columns))
        findings.extend(self.compare_transformation_metadata(source_columns, target_columns, transformation_columns))

        deduped = self._deduplicate(findings)
        self.write_report(deduped)
        if self.logger:
            self.logger.info("Datatype mismatch report written to %s. rows=%s", self.report_path, len(deduped))
        return deduped

    def compare_source_target(
        self,
        source_columns: Iterable[MetadataColumn],
        target_columns: Iterable[MetadataColumn],
    ) -> list[DatatypeMismatch]:
        targets_by_context = self._index_columns(target_columns)
        findings: list[DatatypeMismatch] = []
        for source_column in source_columns:
            context = (source_column.source_file, source_column.repository_name, source_column.folder_name)
            target_column = targets_by_context.get(context, {}).get(self._normalize_name(source_column.column))
            if not target_column:
                continue
            findings.extend(self._compare_pair(source_column, target_column, "source_target"))
        return findings

    def compare_transformation_metadata(
        self,
        source_columns: Iterable[MetadataColumn],
        target_columns: Iterable[MetadataColumn],
        transformation_columns: Iterable[MetadataColumn],
    ) -> list[DatatypeMismatch]:
        columns_by_context = self._index_columns([*source_columns, *target_columns])
        findings: list[DatatypeMismatch] = []
        for port in transformation_columns:
            context = (port.source_file, port.repository_name, port.folder_name)
            related = columns_by_context.get(context, {}).get(self._normalize_name(port.column))
            if not related:
                continue
            findings.extend(self._compare_pair(related, port, "transformation"))
            if port.transformation_type.upper() == "LOOKUP":
                findings.extend(self._compare_pair(related, port, "lookup"))
        return findings

    def write_report(self, findings: list[DatatypeMismatch], report_path: str | Path | None = None) -> None:
        path = self._resolve_path(report_path or self.report_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(asdict(finding) for finding in findings)

    def _compare_pair(
        self,
        left_column: MetadataColumn,
        right_column: MetadataColumn,
        comparison_scope: str,
    ) -> list[DatatypeMismatch]:
        left = self.mapping_engine.map_datatype(
            left_column.datatype,
            precision=left_column.precision,
            scale=left_column.scale,
        )
        right = self.mapping_engine.map_datatype(
            right_column.datatype,
            precision=right_column.precision,
            scale=right_column.scale,
        )

        findings: list[DatatypeMismatch] = []
        self._append_if(findings, not self.mapping_engine.are_compatible(left, right), "datatype_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._precision_mismatch(left, right), "precision_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._scale_mismatch(left, right), "scale_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._length_mismatch(left, right), "length_mismatch", left_column, right_column, left, right)
        self._append_if(findings, left.unicode != right.unicode and left.family == right.family == "STRING", "unicode_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._varchar_vs_nvarchar(left, right), "varchar_vs_nvarchar", left_column, right_column, left, right)
        self._append_if(findings, self._decimal_vs_double(left, right), "decimal_vs_double", left_column, right_column, left, right)
        self._append_if(findings, self._native_precision_mismatch(left, right), "native_precision_mismatch", left_column, right_column, left, right)
        self._append_if(findings, self._truncation_risk(left, right), "truncation_risk", left_column, right_column, left, right)
        self._append_if(findings, left.base_type == "CLOB" or right.base_type == "CLOB", "clob_to_text_conversion", left_column, right_column, left, right)
        if comparison_scope == "lookup" and findings:
            findings.append(self._finding("lookup_datatype_mismatch", left_column, right_column, left, right))
        return findings

    def _append_if(
        self,
        findings: list[DatatypeMismatch],
        condition: bool,
        issue_code: str,
        left_column: MetadataColumn,
        right_column: MetadataColumn,
        left: DatatypeSpec,
        right: DatatypeSpec,
    ) -> None:
        if condition:
            findings.append(self._finding(issue_code, left_column, right_column, left, right))

    def _finding(
        self,
        issue_code: str,
        left_column: MetadataColumn,
        right_column: MetadataColumn,
        left: DatatypeSpec,
        right: DatatypeSpec,
    ) -> DatatypeMismatch:
        rule = self.mapping_engine.issue_rule(issue_code)
        return DatatypeMismatch(
            column=left_column.column,
            source=self._display_type(left),
            target=self._display_type(right),
            severity=rule["severity"],
            recommendation=rule["recommendation"],
            issue_type=issue_code,
            transformation=right_column.transformation_name,
            mapping_name=right_column.mapping_name or left_column.mapping_name,
            source_file=right_column.source_file or left_column.source_file,
        )

    @staticmethod
    def _precision_mismatch(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        return left.family in {"NUMERIC", "FLOATING"} and right.family in {"NUMERIC", "FLOATING"} and left.precision != right.precision

    @staticmethod
    def _scale_mismatch(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        return left.family in {"NUMERIC", "FLOATING"} and right.family in {"NUMERIC", "FLOATING"} and left.scale != right.scale

    @staticmethod
    def _length_mismatch(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        return left.family == right.family == "STRING" and left.length is not None and right.length is not None and left.length != right.length

    @staticmethod
    def _varchar_vs_nvarchar(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        return {left.base_type, right.base_type} & {"VARCHAR", "VARCHAR2"} and {left.base_type, right.base_type} & {"NCHAR", "NVARCHAR2"}

    @staticmethod
    def _decimal_vs_double(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        return {left.family, right.family} == {"NUMERIC", "FLOATING"}

    @staticmethod
    def _native_precision_mismatch(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        return (
            left.family in {"NUMERIC", "FLOATING"}
            and right.family in {"NUMERIC", "FLOATING"}
            and left.precision is not None
            and right.precision is not None
            and abs(left.precision - right.precision) >= 10
        )

    @staticmethod
    def _truncation_risk(left: DatatypeSpec, right: DatatypeSpec) -> bool:
        if left.family == right.family == "STRING" and left.length and right.length:
            return right.length < left.length
        if left.family in {"NUMERIC", "FLOATING"} and right.family in {"NUMERIC", "FLOATING"}:
            return (
                left.precision is not None
                and right.precision is not None
                and right.precision < left.precision
            ) or (
                left.scale is not None
                and right.scale is not None
                and right.scale < left.scale
            )
        return False

    @staticmethod
    def _display_type(spec: DatatypeSpec) -> str:
        if spec.length is not None:
            return f"{spec.canonical_type}({spec.length})"
        if spec.precision is not None and spec.scale is not None:
            return f"{spec.canonical_type}({spec.precision},{spec.scale})"
        if spec.precision is not None:
            return f"{spec.canonical_type}({spec.precision})"
        return spec.canonical_type

    def _load_columns(self, path: Path, table_type: str) -> list[MetadataColumn]:
        rows = self._read_csv(path)
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
            for row in rows
        ]

    def _load_ports(self, path: Path) -> list[MetadataColumn]:
        transformations = {
            (
                row.get("file_name", ""),
                row.get("repository_name", ""),
                row.get("folder_name", ""),
                row.get("mapping_name", ""),
                row.get("transformation_name", ""),
            ): row.get("transformation_type", "")
            for row in self._read_csv(self.metadata_folder / "transformations.csv")
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
                transformation_type=transformations.get(
                    (
                        row.get("file_name", ""),
                        row.get("repository_name", ""),
                        row.get("folder_name", ""),
                        row.get("mapping_name", ""),
                        row.get("transformation_name", ""),
                    ),
                    "",
                ),
                source_file=row.get("file_name", ""),
                repository_name=row.get("repository_name", ""),
                folder_name=row.get("folder_name", ""),
            )
            for row in self._read_csv(path)
        ]

    @staticmethod
    def _index_columns(columns: Iterable[MetadataColumn]) -> dict[tuple[str, str, str], dict[str, MetadataColumn]]:
        indexed: dict[tuple[str, str, str], dict[str, MetadataColumn]] = {}
        for column in columns:
            context = (column.source_file, column.repository_name, column.folder_name)
            indexed.setdefault(context, {})[DatatypeHarmonizationEngine._normalize_name(column.column)] = column
        return indexed

    @staticmethod
    def _deduplicate(findings: Iterable[DatatypeMismatch]) -> list[DatatypeMismatch]:
        seen: set[tuple[str, str, str, str, str]] = set()
        deduped: list[DatatypeMismatch] = []
        for finding in findings:
            key = (finding.column, finding.issue_type, finding.source, finding.target, finding.transformation)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(finding)
        return deduped

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

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            raise FileNotFoundError(f"Required datatype harmonization input not found: {path}")
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def build_datatype_mismatch_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    rules_path: str | Path | None = None,
) -> list[DatatypeMismatch]:
    return DatatypeHarmonizationEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        rules_path=rules_path,
    ).harmonize()
