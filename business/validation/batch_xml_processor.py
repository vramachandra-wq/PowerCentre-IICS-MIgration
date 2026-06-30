from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from business.validation.xml_comparison_engine import XmlComparisonEngine
from business.validation.xml_remediation_engine import XmlChange, XmlRemediationEngine


class BatchXmlProcessor:
    """Coordinates multi-XML remediation and dashboard-ready XML reports."""

    def __init__(self, input_folder: str | Path = "input_xml", output_folder: str | Path = "output") -> None:
        self.project_root = Path.cwd()
        self.input_folder = self._resolve_path(input_folder)
        self.output_folder = self._resolve_path(output_folder)
        self.reports_folder = self.output_folder / "reports"
        self.remediation_engine = XmlRemediationEngine(input_folder=self.input_folder, output_folder=self.output_folder)
        self.comparison_engine = XmlComparisonEngine(output_folder=self.output_folder)

    def run(self) -> dict[str, int]:
        changes = self.remediation_engine.remediate_all()
        self.comparison_engine.write_change_summary(changes)
        self.reports_folder.mkdir(parents=True, exist_ok=True)
        self._write_xml_remediation_report(changes)
        self._write_migration_improvement_report(changes)
        self._write_consolidated_dashboard(changes)
        return {
            "xml_files": len(list(self.remediation_engine.remediated_folder.glob("*_remediated.xml"))),
            "changes": len([change for change in changes if change.status == "AUTO_FIXED"]),
            "manual_flags": len([change for change in changes if change.status == "MANUAL_REMEDIATION_REQUIRED"]),
        }

    def _write_xml_remediation_report(self, changes: list[XmlChange]) -> None:
        remediation = self._read_csv(self.output_folder / "remediation_report.csv")
        readiness = {row.get("mapping_name", ""): row for row in self._read_csv(self.output_folder / "migration_readiness_report.csv")}
        risk = {row.get("mapping_name", ""): row for row in self._read_csv(self.output_folder / "risk_assessment_report.csv")}
        mapping_to_xml = self._mapping_to_xml()
        asset_to_mapping = self._asset_to_mapping(mapping_to_xml)
        rows: list[dict[str, object]] = []

        by_mapping: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in remediation:
            asset = row.get("Asset", "")
            mapping = asset if asset in mapping_to_xml else asset_to_mapping.get(self._normalize(asset), asset)
            by_mapping[mapping].append(row)

        for mapping, items in sorted(by_mapping.items()):
            xml_file = mapping_to_xml.get(mapping, "")
            ready = readiness.get(mapping, {})
            risk_row = risk.get(mapping, {})
            auto_fixed = len([row for row in items if self._truthy(row.get("Auto Fixed")) or row.get("Status", "").lower() == "resolved"])
            manual_review = len([row for row in items if self._truthy(row.get("Approval Required"))])
            manual_remediation = len([row for row in items if self._truthy(row.get("Manual Remediation Required"))])
            issues_before = len(items)
            rows.append(
                {
                    "xml_file": xml_file,
                    "mapping_name": mapping,
                    "issues_before": issues_before,
                    "issues_after": max(0, issues_before - auto_fixed),
                    "issues_resolved": auto_fixed,
                    "auto_fixed": auto_fixed,
                    "manual_review": manual_review,
                    "manual_remediation": manual_remediation,
                    "readiness_before": ready.get("readiness_before", ""),
                    "readiness_after": ready.get("readiness_after", ""),
                    "risk_before": risk_row.get("risk_score", ""),
                    "risk_after": risk_row.get("risk_score", ""),
                }
            )
        self._write_csv(self.reports_folder / "xml_remediation_report.csv", rows)

    def _write_migration_improvement_report(self, changes: list[XmlChange]) -> None:
        readiness = self._read_csv(self.output_folder / "migration_readiness_report.csv")
        risk = {row.get("mapping_name", ""): row for row in self._read_csv(self.output_folder / "risk_assessment_report.csv")}
        mapping_to_xml = self._mapping_to_xml()
        rows: list[dict[str, object]] = []
        for row in readiness:
            mapping = row.get("mapping_name", "")
            before = self._to_float(row.get("readiness_before"))
            after = self._to_float(row.get("readiness_after"))
            issues_before = self._to_int(row.get("issues_found"))
            issues_after = self._to_int(row.get("issues_remaining"))
            risk_score = self._to_int(risk.get(mapping, {}).get("risk_score"))
            rows.append(
                {
                    "mapping_name": mapping,
                    "xml_file": mapping_to_xml.get(mapping, ""),
                    "readiness_before": before,
                    "readiness_after": after,
                    "risk_before": risk_score,
                    "risk_after": risk_score,
                    "issues_before": issues_before,
                    "issues_after": issues_after,
                    "improvement_percentage": round(after - before, 2),
                }
            )
        self._write_csv(self.reports_folder / "migration_improvement_report.csv", rows)

    def _write_consolidated_dashboard(self, changes: list[XmlChange]) -> None:
        inventory = self._inventory_by_xml()
        complexity = self._complexity_by_xml()
        remediation_rows = self._read_csv(self.reports_folder / "xml_remediation_report.csv")
        by_xml: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in remediation_rows:
            by_xml[row.get("xml_file", "")].append(row)

        rows: list[dict[str, object]] = []
        for xml_file, counts in sorted(inventory.items()):
            remediation = by_xml.get(xml_file, [])
            complexity_label = complexity.get(xml_file, "")
            rows.append(
                {
                    "xml_file": xml_file,
                    "workflow_count": counts.get("WORKFLOW", 0),
                    "session_count": counts.get("SESSION", 0),
                    "mapping_count": counts.get("MAPPING", 0),
                    "transformation_count": counts.get("TRANSFORMATION", 0),
                    "complexity_before": complexity_label,
                    "complexity_after": complexity_label,
                    "issues_before": sum(self._to_int(row.get("issues_before")) for row in remediation),
                    "issues_after": sum(self._to_int(row.get("issues_after")) for row in remediation),
                    "auto_fixed": sum(self._to_int(row.get("auto_fixed")) for row in remediation),
                    "manual_review": sum(self._to_int(row.get("manual_review")) for row in remediation),
                    "manual_remediation": sum(self._to_int(row.get("manual_remediation")) for row in remediation),
                    "readiness_before": self._avg([self._to_float(row.get("readiness_before")) for row in remediation]),
                    "readiness_after": self._avg([self._to_float(row.get("readiness_after")) for row in remediation]),
                    "risk_before": sum(self._to_int(row.get("risk_before")) for row in remediation),
                    "risk_after": sum(self._to_int(row.get("risk_after")) for row in remediation),
                }
            )
        self._write_csv(self.reports_folder / "consolidated_migration_dashboard.csv", rows)

    def _inventory_by_xml(self) -> dict[str, Counter[str]]:
        tables = {
            "workflows.csv": ("WORKFLOW", "workflow_name"),
            "sessions.csv": ("SESSION", "session_name"),
            "mappings.csv": ("MAPPING", "mapping_name"),
            "transformations.csv": ("TRANSFORMATION", "transformation_name"),
        }
        inventory: dict[str, Counter[str]] = defaultdict(Counter)
        for file_name, (object_type, name_field) in tables.items():
            for row in self._read_csv(self.output_folder / "metadata_tables" / file_name):
                if row.get(name_field):
                    inventory[row.get("file_name", "")][object_type] += 1
        return inventory

    def _mapping_to_xml(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for row in self._read_csv(self.output_folder / "complexity_classification_report.csv"):
            if row.get("Mapping") and row.get("XML"):
                mapping[row["Mapping"]] = row["XML"]
        for row in self._read_csv(self.output_folder / "metadata_tables" / "mappings.csv"):
            if row.get("mapping_name") and row.get("file_name"):
                mapping.setdefault(row["mapping_name"], row["file_name"])
        return mapping

    def _asset_to_mapping(self, mapping_to_xml: dict[str, str]) -> dict[str, str]:
        index = {self._normalize(mapping): mapping for mapping in mapping_to_xml}
        metadata_folder = self.output_folder / "metadata_tables"
        asset_fields = {
            "source_columns.csv": ["source_name", "column_name"],
            "target_columns.csv": ["target_name", "column_name"],
            "sources.csv": ["source_name"],
            "targets.csv": ["target_name"],
            "transformations.csv": ["transformation_name"],
            "ports.csv": ["transformation_name", "port_name"],
            "instances.csv": ["instance_name", "transformation_name"],
            "sql_overrides.csv": ["context_name", "parent_name"],
            "sessions.csv": ["session_name"],
        }
        for file_name, fields in asset_fields.items():
            for row in self._read_csv(metadata_folder / file_name):
                mapping = row.get("mapping_name", "")
                if not mapping or mapping not in mapping_to_xml:
                    continue
                for field in fields:
                    if row.get(field):
                        index.setdefault(self._normalize(row[field]), mapping)
        return index

    def _complexity_by_xml(self) -> dict[str, str]:
        grouped: dict[str, Counter[str]] = defaultdict(Counter)
        for row in self._read_csv(self.output_folder / "complexity_classification_report.csv"):
            grouped[row.get("XML", "")][row.get("Complexity", "")] += 1
        return {xml_file: counts.most_common(1)[0][0] for xml_file, counts in grouped.items() if counts}

    @staticmethod
    def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    @staticmethod
    def _truthy(value: object) -> bool:
        return str(value or "").strip().lower() in {"true", "yes", "y", "1", "resolved"}

    @staticmethod
    def _to_int(value: object) -> int:
        try:
            return int(float(str(value or "0")))
        except ValueError:
            return 0

    @staticmethod
    def _to_float(value: object) -> float:
        try:
            return float(str(value or "0"))
        except ValueError:
            return 0.0

    @staticmethod
    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 2) if values else 0.0

    @staticmethod
    def _normalize(value: str) -> str:
        import re

        return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def run_batch_xml_remediation(input_folder: str | Path = "input_xml", output_folder: str | Path = "output") -> dict[str, int]:
    return BatchXmlProcessor(input_folder=input_folder, output_folder=output_folder).run()


if __name__ == "__main__":
    print(run_batch_xml_remediation())
