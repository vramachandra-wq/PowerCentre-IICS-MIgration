from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from utils.config_loader import AppConfig


@dataclass(frozen=True)
class ComplexityResult:
    file_name: str
    folder_name: str
    mapping_name: str
    transformation_count: int
    complexity: str
    score: int
    reason: str


class ComplexityClassifier:
    """Rule-based complexity classifier for representative PowerCenter mappings."""

    COMPLEX_TYPES = {
        "aggregator",
        "joiner",
        "sequence generator",
        "stored procedure",
        "union",
    }
    MEDIUM_TYPES = {
        "expression",
        "filter",
        "lookup",
        "lookup procedure",
        "router",
    }

    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(config.paths.output_folder)
        self.metadata_folder = self.output_folder / "metadata_tables"

    def classify(self) -> list[ComplexityResult]:
        mappings = self._read_csv("mappings.csv")
        transformations = self._read_csv("transformations.csv")
        instances = self._read_csv("instances.csv")

        transformations_by_mapping = self._group_rows(transformations)
        instances_by_mapping = self._group_rows(instances)

        results: list[ComplexityResult] = []
        for mapping in mappings:
            key = self._mapping_key(mapping)
            mapping_transformations = transformations_by_mapping.get(key, [])
            mapping_instances = instances_by_mapping.get(key, [])
            result = self._classify_mapping(mapping, mapping_transformations, mapping_instances)
            results.append(result)

        return sorted(results, key=lambda item: (item.file_name, item.mapping_name))

    def write_report(self, results: Iterable[ComplexityResult]) -> None:
        rows = list(results)
        self.output_folder.mkdir(parents=True, exist_ok=True)
        csv_path = self.output_folder / "complexity_classification_report.csv"
        markdown_path = self.output_folder / "complexity_classification_report.md"

        with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "XML",
                    "Folder",
                    "Mapping",
                    "Transformation Count",
                    "Complexity",
                    "Score",
                    "Reason",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        "XML": row.file_name,
                        "Folder": row.folder_name,
                        "Mapping": row.mapping_name,
                        "Transformation Count": row.transformation_count,
                        "Complexity": row.complexity,
                        "Score": row.score,
                        "Reason": row.reason,
                    }
                )

        lines = [
            "# Day 5 Complexity Classification Report",
            "",
            "## Rule-Based Mapping Complexity",
            "",
            "| XML | Mapping | Transformation Count | Complexity | Score | Reason |",
            "|---|---|---:|---|---:|---|",
        ]
        for row in rows:
            lines.append(
                "| "
                f"{row.file_name} | "
                f"{row.mapping_name} | "
                f"{row.transformation_count} | "
                f"{row.complexity} | "
                f"{row.score} | "
                f"{row.reason} |"
            )
        lines.extend(
            [
                "",
                "## Scoring Rules",
                "",
                "| Signal | Score Impact |",
                "|---|---:|",
                "| Transformation count 5-10 | +20 |",
                "| Transformation count >10 | +25 |",
                "| Lookup exists | +15 |",
                "| SQL override exists | +20 |",
                "| SQL override minimum band | Medium |",
                "| Expression logic exists | +10 |",
                "| Router or Filter exists | +10 |",
                "| Stored Procedure exists | +20 |",
                "| Mapplet exists | +15 |",
                "| Nested/multiple mapplets exist | +25 |",
                "| Aggregator, Joiner, Union, or Sequence Generator exists | +15 each |",
                "",
                "Complexity bands: Simple = 1-30, Medium = 31-70, Complex = 71-100.",
            ]
        )
        markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        self.logger.info("Complexity classification written to %s and %s", csv_path, markdown_path)

    def _classify_mapping(
        self,
        mapping: dict[str, str],
        transformations: list[dict[str, str]],
        instances: list[dict[str, str]],
    ) -> ComplexityResult:
        transformation_count = self._to_int(mapping.get("transformation_count", "0"))
        sql_override_count = self._to_int(mapping.get("sql_override_count", "0"))
        transformation_types = {
            row.get("transformation_type", "").strip().lower() for row in transformations
        }
        instance_types = {row.get("transformation_type", "").strip().lower() for row in instances}
        all_types = transformation_types | instance_types

        mapplet_count = sum(1 for row in instances if row.get("transformation_type", "").strip().lower() == "mapplet")
        score = 10
        reasons: list[str] = []

        if transformation_count > 10:
            score += 25
            reasons.append(">10 transformations")
        elif transformation_count >= 5:
            score += 20
            reasons.append("5-10 transformations")
        else:
            reasons.append("<5 transformations")

        if self._contains_type(all_types, {"lookup", "lookup procedure"}):
            score += 15
            reasons.append("Lookup exists")

        if sql_override_count > 0:
            score += 20
            reasons.append("SQL override")

        if "expression" in all_types:
            score += 10
            reasons.append("Expression logic")

        if self._contains_type(all_types, {"router", "filter"}):
            score += 10
            reasons.append("Router/Filter")

        if self._contains_type(all_types, {"stored procedure"}):
            score += 20
            reasons.append("Stored procedure")

        if mapplet_count > 1:
            score += 25
            reasons.append("Nested/multiple mapplets")
        elif mapplet_count == 1:
            score += 15
            reasons.append("Mapplet")

        for complex_type in sorted(self.COMPLEX_TYPES - {"stored procedure"}):
            if self._contains_type(all_types, {complex_type}):
                score += 15
                reasons.append(complex_type.title())

        if sql_override_count > 0:
            score = max(score, 31)

        score = min(score, 100)
        complexity = self._complexity_band(score)
        return ComplexityResult(
            file_name=mapping.get("file_name", ""),
            folder_name=mapping.get("folder_name", ""),
            mapping_name=mapping.get("mapping_name", ""),
            transformation_count=transformation_count,
            complexity=complexity,
            score=score,
            reason=", ".join(reasons) if reasons else "No complexity signals",
        )

    @staticmethod
    def _complexity_band(score: int) -> str:
        if score <= 30:
            return "Simple"
        if score <= 70:
            return "Medium"
        return "Complex"

    def _read_csv(self, file_name: str) -> list[dict[str, str]]:
        path = self.metadata_folder / file_name
        if not path.exists():
            raise FileNotFoundError(f"Required metadata table not found: {path}")
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    @staticmethod
    def _group_rows(rows: Iterable[dict[str, str]]) -> dict[tuple[str, str, str], list[dict[str, str]]]:
        grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        for row in rows:
            grouped.setdefault(ComplexityClassifier._mapping_key(row), []).append(row)
        return grouped

    @staticmethod
    def _mapping_key(row: dict[str, str]) -> tuple[str, str, str]:
        return (
            row.get("file_name", ""),
            row.get("folder_name", ""),
            row.get("mapping_name", ""),
        )

    @staticmethod
    def _contains_type(types: set[str], expected: set[str]) -> bool:
        return any(any(item == value or value in item for value in expected) for item in types)

    @staticmethod
    def _to_int(value: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate
