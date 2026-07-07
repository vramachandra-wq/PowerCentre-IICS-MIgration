"""
Support xml comparison engine for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from business.validation.xml_remediation_engine import XmlChange


class XmlComparisonEngine:
    """Runs focused migration processing and analysis logic."""

    REPORT_COLUMNS = [
        "xml_file",
        "object_type",
        "object_name",
        "attribute",
        "before_value",
        "after_value",
        "rule_applied",
        "status",
        "timestamp",
    ]

    def __init__(self, output_folder: str | Path = "output") -> None:
        """Initialize migration data using the provided output_folder."""

        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(output_folder)
        self.reports_folder = self.output_folder / "reports"

    def write_change_summary(self, changes: list[XmlChange]) -> Path:
        """Handle write change summary using the provided changes."""

        self.reports_folder.mkdir(parents=True, exist_ok=True)
        path = self.reports_folder / "xml_change_summary.csv"
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=self.REPORT_COLUMNS)
            writer.writeheader()
            writer.writerows(asdict(change) for change in changes)
        return path

    def _resolve_path(self, path: str | Path) -> Path:
        """Handle resolve path using the provided path."""

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate
