from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from automation.evaluation_matrix import CanonicalEvaluationObject, EvaluationMatrixRecord, ReportRepository


class EvaluationDatasetBuilder:
    """Creates compact AI-ready datasets from evaluation matrix records."""

    FIELDNAMES = [
        "mapping_name",
        "xml_name",
        "complexity_score",
        "complexity_category",
        "validation_failures",
        "auto_fixed",
        "remaining",
        "risk_score",
        "risk_category",
        "top_risk",
        "readiness",
        "migration_status",
    ]

    def __init__(self, repository: ReportRepository | None = None) -> None:
        self.repository = repository or ReportRepository()

    def build(self, records: Iterable[EvaluationMatrixRecord]) -> list[dict[str, object]]:
        dataset: list[dict[str, object]] = []
        for record in records:
            dataset.append(
                {
                    "mapping_name": record.mapping,
                    "xml_name": record.xml_name,
                    "complexity_score": record.complexity_score,
                    "complexity_category": record.complexity_category,
                    "validation_failures": record.validation_failed,
                    "auto_fixed": record.auto_fixed,
                    "remaining": record.remaining_issues,
                    "risk_score": record.risk_score,
                    "risk_category": record.risk_category,
                    "top_risk": record.top_risk_factor,
                    "readiness": record.readiness_after,
                    "migration_status": record.migration_status,
                }
            )
        return dataset

    def build_canonical_dataset(self, objects: Iterable[CanonicalEvaluationObject]) -> list[dict[str, object]]:
        return [asdict(item) for item in objects]

    def write(
        self,
        dataset: list[dict[str, object]],
        canonical_dataset: list[dict[str, object]] | None = None,
    ) -> dict[str, Path]:
        return {
            "csv": self.repository.write_csv("evaluation_dataset.csv", dataset, self.FIELDNAMES),
            "json": self.repository.write_json("evaluation_dataset.json", canonical_dataset or dataset),
        }
