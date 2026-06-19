from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

from utils.config_loader import AppConfig


class EnterpriseReportBuilder:
    """Builds stakeholder and engineering reports from generated metadata tables."""

    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(config.paths.output_folder)
        self.metadata_folder = self.output_folder / "metadata_tables"
        self.canonical_folder = self.output_folder / "canonical" / "tables"
        self.enterprise_folder = self.output_folder / "enterprise"

    def build_reports(self) -> dict[str, int]:
        self.enterprise_folder.mkdir(parents=True, exist_ok=True)

        asset_inventory = self._build_asset_inventory()
        transformation_counts = self._build_transformation_type_counts()
        mapping_catalog = self._build_mapping_catalog()
        executive_summary = self._build_executive_summary(asset_inventory, transformation_counts, mapping_catalog)

        self._write_csv("asset_inventory.csv", asset_inventory)
        self._write_csv("transformation_type_summary.csv", transformation_counts)
        self._write_csv("mapping_migration_catalog.csv", mapping_catalog)
        self._write_json("executive_summary.json", executive_summary)
        self._write_markdown(executive_summary, asset_inventory, transformation_counts, mapping_catalog)

        summary = {
            "asset_inventory_rows": len(asset_inventory),
            "transformation_type_rows": len(transformation_counts),
            "mapping_catalog_rows": len(mapping_catalog),
        }
        self.logger.info("Enterprise reports written to %s. %s", self.enterprise_folder, summary)
        return summary

    def _build_asset_inventory(self) -> list[dict[str, object]]:
        xml_folder = self._resolve_path(self.config.paths.xml_folder)
        xml_files = sorted({path.name for path in xml_folder.glob("*.XML")} | {path.name for path in xml_folder.glob("*.xml")})
        table_names = ["workflows", "sessions", "mappings", "sources", "targets", "transformations"]
        tables = {name: self._read_csv(self.metadata_folder / f"{name}.csv") for name in table_names}

        rows: list[dict[str, object]] = []
        for xml_file in xml_files:
            rows.append(
                {
                    "XML": xml_file,
                    "Workflow": self._count_by_file(tables["workflows"], xml_file),
                    "Session": self._count_by_file(tables["sessions"], xml_file),
                    "Mapping": self._count_by_file(tables["mappings"], xml_file),
                    "Source": self._count_by_file(tables["sources"], xml_file),
                    "Target": self._count_by_file(tables["targets"], xml_file),
                    "Transformations": self._count_by_file(tables["transformations"], xml_file),
                }
            )
        return rows

    def _build_transformation_type_counts(self) -> list[dict[str, object]]:
        transformations = self._read_csv(self.metadata_folder / "transformations.csv")
        counter = Counter(row.get("transformation_type", "") for row in transformations)
        return [
            {"Transformation": transformation_type, "Count": count}
            for transformation_type, count in sorted(counter.items())
        ]

    def _build_mapping_catalog(self) -> list[dict[str, object]]:
        mappings = self._read_csv(self.canonical_folder / "canonical_mappings.csv")
        transformations = self._read_csv(self.canonical_folder / "canonical_transformations.csv")
        sql_overrides = self._read_csv(self.canonical_folder / "canonical_sql_overrides.csv")

        transformation_types_by_mapping: dict[str, set[str]] = defaultdict(set)
        for transformation in transformations:
            transformation_types_by_mapping[transformation.get("mapping_id", "")].add(
                transformation.get("transformation_type", "")
            )

        sql_override_count_by_mapping = Counter(row.get("mapping_id", "") for row in sql_overrides)
        rows: list[dict[str, object]] = []
        for mapping in mappings:
            mapping_id = mapping.get("mapping_id", "")
            rows.append(
                {
                    "Mapping ID": mapping_id,
                    "Mapping Name": mapping.get("mapping_name", ""),
                    "XML": mapping.get("source_file", ""),
                    "Repository": mapping.get("repository_name", ""),
                    "Folder": mapping.get("folder_name", ""),
                    "Sources": mapping.get("sources", ""),
                    "Targets": mapping.get("targets", ""),
                    "Transformation Count": mapping.get("transformation_count", "0"),
                    "Connector Count": mapping.get("connector_count", "0"),
                    "SQL Override Count": sql_override_count_by_mapping.get(mapping_id, 0),
                    "Transformation Types": " | ".join(sorted(transformation_types_by_mapping.get(mapping_id, set()))),
                    "Complexity": mapping.get("complexity", ""),
                }
            )
        return sorted(rows, key=lambda row: (str(row["XML"]), str(row["Mapping Name"])))

    def _build_executive_summary(
        self,
        asset_inventory: list[dict[str, object]],
        transformation_counts: list[dict[str, object]],
        mapping_catalog: list[dict[str, object]],
    ) -> dict[str, object]:
        canonical_assets = self._read_csv(self.canonical_folder / "canonical_assets.csv")
        canonical_columns = self._read_csv(self.canonical_folder / "canonical_columns.csv")
        canonical_connectors = self._read_csv(self.canonical_folder / "canonical_connectors.csv")
        canonical_sql = self._read_csv(self.canonical_folder / "canonical_sql_overrides.csv")
        complexity_counter = Counter(row.get("Complexity", "") for row in mapping_catalog)
        asset_type_counter = Counter(row.get("asset_type", "") for row in canonical_assets)

        return {
            "input_xml_files": len(asset_inventory),
            "asset_inventory": {
                "workflows": sum(int(row["Workflow"]) for row in asset_inventory),
                "sessions": sum(int(row["Session"]) for row in asset_inventory),
                "mappings": sum(int(row["Mapping"]) for row in asset_inventory),
                "sources": sum(int(row["Source"]) for row in asset_inventory),
                "targets": sum(int(row["Target"]) for row in asset_inventory),
                "transformations": sum(int(row["Transformations"]) for row in asset_inventory),
            },
            "canonical_repository": {
                "assets": len(canonical_assets),
                "mappings": len(mapping_catalog),
                "columns": len(canonical_columns),
                "connectors": len(canonical_connectors),
                "sql_overrides": len(canonical_sql),
                "asset_types": dict(sorted(asset_type_counter.items())),
            },
            "mapping_complexity": dict(sorted(complexity_counter.items())),
            "transformation_types": {
                row["Transformation"]: row["Count"] for row in transformation_counts
            },
        }

    def _write_markdown(
        self,
        summary: dict[str, object],
        asset_inventory: list[dict[str, object]],
        transformation_counts: list[dict[str, object]],
        mapping_catalog: list[dict[str, object]],
    ) -> None:
        markdown_path = self.enterprise_folder / "enterprise_migration_report.md"
        lines = [
            "# Enterprise PowerCenter to IICS Metadata Report",
            "",
            "## Executive Summary",
            "",
            f"- Input XML files analyzed: {summary['input_xml_files']}",
            f"- Canonical assets: {summary['canonical_repository']['assets']}",
            f"- Canonical mappings: {summary['canonical_repository']['mappings']}",
            f"- Canonical columns: {summary['canonical_repository']['columns']}",
            f"- Connectors / data-flow links: {summary['canonical_repository']['connectors']}",
            f"- SQL overrides: {summary['canonical_repository']['sql_overrides']}",
            "",
            "## Mapping Complexity",
            "",
            "| Complexity | Mapping Count |",
            "|---|---:|",
        ]
        for complexity, count in summary["mapping_complexity"].items():
            lines.append(f"| {complexity} | {count} |")

        lines.extend(["", "## Asset Inventory", "", "| XML | Workflow | Session | Mapping | Source | Target | Transformations |", "|---|---:|---:|---:|---:|---:|---:|"])
        for row in asset_inventory:
            lines.append(
                f"| {row['XML']} | {row['Workflow']} | {row['Session']} | {row['Mapping']} | "
                f"{row['Source']} | {row['Target']} | {row['Transformations']} |"
            )

        lines.extend(["", "## Transformation Types", "", "| Transformation | Count |", "|---|---:|"])
        for row in transformation_counts:
            lines.append(f"| {row['Transformation']} | {row['Count']} |")

        lines.extend(
            [
                "",
                "## High Complexity Mapping Focus",
                "",
                "| Mapping | XML | Transformations | SQL Overrides | Connectors | Transformation Types |",
                "|---|---|---:|---:|---:|---|",
            ]
        )
        for row in mapping_catalog:
            if row["Complexity"] == "HIGH":
                lines.append(
                    f"| {self._md(row['Mapping Name'])} | {self._md(row['XML'])} | {row['Transformation Count']} | "
                    f"{row['SQL Override Count']} | {row['Connector Count']} | {self._md(row['Transformation Types'])} |"
                )

        lines.extend(
            [
                "",
                "## Repository Architecture",
                "",
                "The enterprise repository consolidates all XML metadata into six normalized tables: "
                "`assets`, `mappings`, `transformations`, `columns_metadata`, `sql_overrides`, and `connectors`. "
                "Each row keeps traceability back to the XML source file, repository, folder, and mapping.",
                "",
                "This structure is intentionally metadata-category based rather than one-table-per-XML. "
                "It supports portfolio reporting now and PowerCenter-vs-IICS comparison later.",
            ]
        )
        markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_csv(self, file_name: str, rows: list[dict[str, object]]) -> None:
        path = self.enterprise_folder / file_name
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def _write_json(self, file_name: str, payload: dict[str, object]) -> None:
        (self.enterprise_folder / file_name).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            raise FileNotFoundError(f"Required report input not found: {path}")
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    @staticmethod
    def _count_by_file(rows: Iterable[dict[str, str]], file_name: str) -> int:
        return sum(1 for row in rows if row.get("file_name") == file_name)

    @staticmethod
    def _md(value: object) -> str:
        return str(value).replace("|", "\\|")

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate
