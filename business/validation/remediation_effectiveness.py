from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from business.validation.readiness_engine import RemediationReportLoader
from common.config.config import AppConfig


@dataclass(frozen=True)
class RemediationEffectivenessRecord:
    mapping_name: str
    issues_found: int
    auto_fixed: int
    manual_review: int
    manual_remediation: int
    auto_fix_percentage: float


class RemediationEffectivenessEngine:
    """Calculates measurable automation lift from remediation outputs."""

    REPORT_COLUMNS = [
        "mapping_name",
        "issues_found",
        "auto_fixed",
        "manual_review",
        "manual_remediation",
        "auto_fix_percentage",
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
        self.project_root = Path.cwd()
        configured_output = output_folder or (config.paths.output_folder if config else "output")
        self.output_folder = self._resolve_path(configured_output)
        self.report_path = self.output_folder / "post_remediation_auto_fix_effectiveness_report.csv"
        self.loader = RemediationReportLoader(
            self.output_folder,
            scoring_rules_path or Path("common/config/readiness_rules.json"),
        )

    def build_report(self) -> list[RemediationEffectivenessRecord]:
        remediation = self.loader.load_remediation_issues()
        mappings = sorted(
            {issue.mapping_name for issue in remediation}
            or self.loader.mapping_names
            or {"UNMAPPED_ASSET"}
        )
        records: list[RemediationEffectivenessRecord] = []
        for mapping in mappings:
            remediation_for_mapping = [issue for issue in remediation if issue.mapping_name == mapping]
            found = len(remediation_for_mapping)
            auto_fixed = len(
                [
                    issue
                    for issue in remediation_for_mapping
                    if issue.mapping_name == mapping and (issue.auto_fixed or issue.status.lower() == "resolved")
                ]
            )
            auto_fixed = min(auto_fixed, found)
            manual_review = len(
                [issue for issue in remediation_for_mapping if issue.approval_required]
            )
            manual_remediation = len(
                [
                    issue
                    for issue in remediation_for_mapping
                    if issue.manual_remediation_required
                ]
            )
            records.append(
                RemediationEffectivenessRecord(
                    mapping_name=mapping,
                    issues_found=found,
                    auto_fixed=auto_fixed,
                    manual_review=manual_review,
                    manual_remediation=manual_remediation,
                    auto_fix_percentage=round((auto_fixed / found) * 100, 2) if found else 0.0,
                )
            )
        self.write_report(records)
        if self.logger:
            self.logger.info(
                "Remediation effectiveness report written to %s. rows=%s", self.report_path, len(records)
            )
        return records

    def write_report(
        self, records: list[RemediationEffectivenessRecord], report_path: str | Path | None = None
    ) -> None:
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


def build_remediation_effectiveness_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    scoring_rules_path: str | Path | None = None,
) -> list[RemediationEffectivenessRecord]:
    return RemediationEffectivenessEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        scoring_rules_path=scoring_rules_path,
    ).build_report()
