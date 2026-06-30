from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from business.validation.readiness_engine import Day3ReportLoader, IssueRecord
from common.config.config import AppConfig


@dataclass(frozen=True)
class RiskAssessmentRecord:
    mapping_name: str
    risk_score: int
    risk_level: str
    top_risk_factor: str


class RiskAssessmentEngine:
    """Scores residual migration risk from remaining unresolved issues only."""

    REPORT_COLUMNS = ["mapping_name", "risk_score", "risk_level", "top_risk_factor"]

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
        self.report_path = self.output_folder / "risk_assessment_report.csv"
        self.loader = Day3ReportLoader(
            self.output_folder,
            scoring_rules_path or Path("common/config/readiness_rules.json"),
        )

    def build_report(self) -> list[RiskAssessmentRecord]:
        remaining = self.loader.unresolved_issues()
        before = self.loader.load_before_issues()
        remediation = self.loader.load_remediation_issues()
        mappings = sorted(
            self.loader.mapping_names
            or {issue.mapping_name for issue in [*before, *remaining, *remediation]}
            or {"UNMAPPED_ASSET"}
        )
        records: list[RiskAssessmentRecord] = []
        for mapping in mappings:
            issues = [issue for issue in remaining if issue.mapping_name == mapping]
            scored = [(issue, self._risk_score(issue)) for issue in issues]
            risk_score = sum(score for _, score in scored)
            top_issue = max(scored, key=lambda item: item[1])[0].issue if scored else "none"
            records.append(
                RiskAssessmentRecord(
                    mapping_name=mapping,
                    risk_score=risk_score,
                    risk_level=self._risk_level(risk_score),
                    top_risk_factor=top_issue,
                )
            )
        self.write_report(records)
        if self.logger:
            self.logger.info("Risk assessment report written to %s. rows=%s", self.report_path, len(records))
        return records

    def write_report(self, records: list[RiskAssessmentRecord], report_path: str | Path | None = None) -> None:
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

    def _risk_score(self, issue: IssueRecord) -> int:
        risk_factors = self.loader.rules.get("risk_factors", {})
        if issue.issue in risk_factors:
            return int(risk_factors[issue.issue]["score"])
        defaults = self.loader.rules.get("default_risk_score", {})
        return int(defaults.get(issue.severity.upper(), 8))

    def _risk_level(self, score: int) -> str:
        for band in self.loader.rules.get("risk_levels", []):
            if int(band["min"]) <= score <= int(band["max"]):
                return str(band["level"])
        return "CRITICAL"

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def build_risk_assessment_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    scoring_rules_path: str | Path | None = None,
) -> list[RiskAssessmentRecord]:
    return RiskAssessmentEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        scoring_rules_path=scoring_rules_path,
    ).build_report()
