from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from business.validation.readiness_engine import MigrationReadinessEngine, ReadinessRecord
from business.validation.remediation_effectiveness import (
    RemediationEffectivenessEngine,
    RemediationEffectivenessRecord,
)
from business.validation.risk_assessment import RiskAssessmentEngine, RiskAssessmentRecord
from common.config.config import AppConfig


@dataclass(frozen=True)
class ExecutiveMetric:
    metric: str
    value: str


class ExecutiveSummaryEngine:
    """Builds stakeholder-friendly summary metrics from post-remediation analytical reports."""

    REPORT_COLUMNS = ["metric", "value"]

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
        self.report_path = self.output_folder / "post_remediation_executive_summary_report.csv"
        self.scoring_rules_path = scoring_rules_path

    def build_report(self) -> list[ExecutiveMetric]:
        readiness = MigrationReadinessEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
            scoring_rules_path=self.scoring_rules_path,
        ).build_report()
        risk = RiskAssessmentEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
            scoring_rules_path=self.scoring_rules_path,
        ).build_report()
        effectiveness = RemediationEffectivenessEngine(
            config=self.config,
            logger=self.logger,
            output_folder=self.output_folder,
            scoring_rules_path=self.scoring_rules_path,
        ).build_report()

        metrics = self._metrics(readiness, risk, effectiveness)
        self.write_report(metrics)
        if self.logger:
            self.logger.info("Executive summary report written to %s. rows=%s", self.report_path, len(metrics))
        return metrics

    def write_report(self, metrics: list[ExecutiveMetric], report_path: str | Path | None = None) -> None:
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
            writer.writerows(metric.__dict__ for metric in metrics)

    @staticmethod
    def _metrics(
        readiness: list[ReadinessRecord],
        risk: list[RiskAssessmentRecord],
        effectiveness: list[RemediationEffectivenessRecord],
    ) -> list[ExecutiveMetric]:
        total_found = sum(record.issues_found for record in readiness)
        total_auto_fixed = sum(record.issues_auto_fixed for record in readiness)
        total_remaining = sum(record.issues_remaining for record in readiness)
        average_readiness = (
            round(sum(record.readiness_after for record in readiness) / len(readiness), 2)
            if readiness
            else 0.0
        )
        highest_risk = max(risk, key=lambda record: record.risk_score, default=None)
        lowest_readiness = min(readiness, key=lambda record: record.readiness_after, default=None)
        ready_count = len([record for record in readiness if record.readiness_category == "READY"])
        manual_count = len(
            [
                record
                for record in effectiveness
                if record.manual_review > 0 or record.manual_remediation > 0
            ]
        )
        auto_fix_rate = round((total_auto_fixed / total_found) * 100, 2) if total_found else 0.0
        manual_effort_reduction = auto_fix_rate

        return [
            ExecutiveMetric("Total Mappings Analyzed", str(len(readiness))),
            ExecutiveMetric("Total Issues Found", str(total_found)),
            ExecutiveMetric("Total Issues Auto Fixed", str(total_auto_fixed)),
            ExecutiveMetric("Total Issues Remaining", str(total_remaining)),
            ExecutiveMetric("Auto Fix Rate", f"{auto_fix_rate}%"),
            ExecutiveMetric("Average Readiness Score", str(average_readiness)),
            ExecutiveMetric(
                "Highest Risk Mapping",
                f"{highest_risk.mapping_name} ({highest_risk.risk_level}, {highest_risk.risk_score})"
                if highest_risk
                else "",
            ),
            ExecutiveMetric(
                "Lowest Readiness Mapping",
                f"{lowest_readiness.mapping_name} ({lowest_readiness.readiness_after})"
                if lowest_readiness
                else "",
            ),
            ExecutiveMetric("Mappings Ready for Migration", str(ready_count)),
            ExecutiveMetric("Mappings Requiring Manual Intervention", str(manual_count)),
            ExecutiveMetric("Estimated Manual Effort Reduction", f"{manual_effort_reduction}%"),
        ]

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


def build_executive_summary_report(
    config: AppConfig | None = None,
    logger=None,
    output_folder: str | Path | None = None,
    scoring_rules_path: str | Path | None = None,
) -> list[ExecutiveMetric]:
    return ExecutiveSummaryEngine(
        config=config,
        logger=logger,
        output_folder=output_folder,
        scoring_rules_path=scoring_rules_path,
    ).build_report()
