from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Iterable

from automation.evaluation_matrix import ReportRepository
from automation.ai.llm_client import HuggingFaceQwenRecommendationClient, RecommendationModelClient
from automation.ai.recommendation_models import (
    AIRecommendationConfig,
    FailureRecord,
    Recommendation,
    RecommendationResult,
)
from automation.ai.response_parser import RecommendationResponseParser
from business.validation.readiness_engine import RemediationReportLoader


class RecommendationEngine:
    """Generates AI recommendations for unresolved post-remediation failures."""

    def __init__(
        self,
        repository: ReportRepository | None = None,
        config: AIRecommendationConfig | None = None,
        client: RecommendationModelClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.repository = repository or ReportRepository()
        self.config = config or AIRecommendationConfig()
        self.client = client
        self.logger = logger
        self.report_loader = RemediationReportLoader(self.repository.output_folder)

    def build_failures(self) -> list[FailureRecord]:
        failures = self._from_remediation_report()
        if not failures:
            failures = self._from_validation_report()
        if self.config.max_records > 0:
            return failures[: self.config.max_records]
        return failures

    def recommend(self) -> list[RecommendationResult]:
        failures = self.build_failures()
        if not failures:
            return []
        try:
            client = self.client or HuggingFaceQwenRecommendationClient(self.config)
        except Exception as exc:
            self._log_warning("AI recommendation client unavailable: %s", exc)
            return [self._fallback_result(failure, exc, 0) for failure in failures]

        results: list[RecommendationResult] = []
        for failure in failures:
            started = time.perf_counter()
            try:
                payload = client.recommend(failure)
                recommendation = RecommendationResponseParser.parse(payload)
                elapsed = int((time.perf_counter() - started) * 1000)
                results.append(RecommendationResult(failure, recommendation, elapsed))
            except Exception as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                self._log_warning("AI recommendation failed for %s/%s: %s", failure.mapping, failure.failure_type, exc)
                results.append(self._fallback_result(failure, exc, elapsed))
        return results

    def _from_remediation_report(self) -> list[FailureRecord]:
        rows = self.repository.read_csv("remediation_report.csv")
        validation_rows = self.repository.read_csv("validation_report.csv")
        metadata = self._metadata_context()
        failures: list[FailureRecord] = []
        seen: set[tuple[str, str, str, str]] = set()
        for row in rows:
            if self._resolved(row):
                continue
            mapping = self.report_loader._mapping_from_row(row)
            failure = self._failure_from_row(row, mapping, metadata, validation_rows)
            key = self._dedupe_key(failure)
            if key in seen:
                continue
            seen.add(key)
            failures.append(failure)
        return failures

    def _from_validation_report(self) -> list[FailureRecord]:
        rows = self.repository.read_csv("validation_report.csv")
        metadata = self._metadata_context()
        failures: list[FailureRecord] = []
        seen: set[tuple[str, str, str, str]] = set()
        for row in rows:
            if self._resolved(row):
                continue
            mapping = self.report_loader._mapping_from_row(row)
            failure = self._failure_from_row(row, mapping, metadata, rows)
            key = self._dedupe_key(failure)
            if key in seen:
                continue
            seen.add(key)
            failures.append(failure)
        return failures

    def _failure_from_row(
        self,
        row: dict[str, str],
        mapping: str,
        metadata: dict[str, dict[str, str]],
        validation_rows: list[dict[str, str]],
    ) -> FailureRecord:
        context = metadata.get(mapping, {})
        asset = row.get("Asset") or row.get("Asset Name") or row.get("Before Value") or mapping
        validation_match = self._matching_validation_row(row, validation_rows)
        transformation = self._transformation_name(mapping, asset)
        return FailureRecord(
            workflow=context.get("workflow", "") or Path(row.get("Source File", "")).stem or mapping,
            mapping=mapping,
            transformation=transformation,
            object_name=asset,
            failure_type=self.report_loader.canonical_issue(row.get("Issue", "")),
            validation_rule=row.get("Rule ID") or validation_match.get("Rule ID", ""),
            validation_message=validation_match.get("Issue") or row.get("Issue", ""),
            auto_fix_status=self._auto_fix_status(row),
            severity=(row.get("Severity") or validation_match.get("Severity") or "MEDIUM").upper(),
            error_details=self._error_details(row),
            root_cause=row.get("Root Cause") or row.get("root_cause") or "",
            rule_based_recommendation=row.get("Recommendation") or validation_match.get("Recommendation", ""),
            source_file=row.get("Source File") or validation_match.get("Source File", ""),
        )

    def _metadata_context(self) -> dict[str, dict[str, str]]:
        workflows_by_file = {
            Path(row.get("file_name", "")).name: row.get("workflow_name", "")
            for row in self.repository.read_csv("metadata_tables/workflows.csv")
        }
        sessions_by_mapping = {
            row.get("mapping_name", ""): row.get("session_name", "")
            for row in self.repository.read_csv("metadata_tables/sessions.csv")
        }
        context: dict[str, dict[str, str]] = {}
        for row in self.repository.read_csv("metadata_tables/mappings.csv"):
            mapping = row.get("mapping_name", "")
            if not mapping:
                continue
            xml_name = Path(row.get("file_name", "")).name
            context[mapping] = {
                "workflow": workflows_by_file.get(xml_name, Path(xml_name).stem),
                "session": sessions_by_mapping.get(mapping, ""),
            }
        return context

    def _transformation_name(self, mapping: str, asset: str) -> str:
        normalized_asset = self.report_loader._normalize_name(asset)
        for row in self.repository.read_csv("metadata_tables/transformations.csv"):
            if row.get("mapping_name", "") != mapping:
                continue
            transformation = row.get("transformation_name", "")
            if self.report_loader._normalize_name(transformation) == normalized_asset:
                return transformation
        return ""

    @staticmethod
    def _matching_validation_row(row: dict[str, str], validation_rows: Iterable[dict[str, str]]) -> dict[str, str]:
        issue = row.get("Issue", "")
        asset = row.get("Asset", "")
        for candidate in validation_rows:
            if candidate.get("Issue") == issue and (not asset or candidate.get("Asset") == asset):
                return candidate
        return {}

    @staticmethod
    def _resolved(row: dict[str, str]) -> bool:
        return str(row.get("Auto Fixed", "")).strip().lower() == "true" or row.get("Status", "").strip().lower() in {
            "resolved",
            "suppressed",
        }

    @staticmethod
    def _auto_fix_status(row: dict[str, str]) -> str:
        if str(row.get("Auto Fixed", "")).strip().lower() == "true":
            return "Auto Fixed"
        status = row.get("Status", "").strip()
        if status:
            return status
        if str(row.get("Manual Remediation Required", "")).strip().lower() == "true":
            return "Manual Remediation Required"
        return "Not Auto Fixed"

    @staticmethod
    def _error_details(row: dict[str, str]) -> str:
        details = {
            "before_value": row.get("Before Value", ""),
            "after_value": row.get("After Value", ""),
            "fix_applied": row.get("Fix Applied", ""),
            "original_sql": row.get("Original SQL", ""),
            "proposed_sql": row.get("Proposed SQL", ""),
        }
        return json.dumps({key: value for key, value in details.items() if value}, sort_keys=True)

    @staticmethod
    def _dedupe_key(failure: FailureRecord) -> tuple[str, str, str, str]:
        return (failure.mapping, failure.failure_type, failure.object_name, Path(failure.source_file).name)

    def _fallback_result(self, failure: FailureRecord, exc: Exception, elapsed_ms: int) -> RecommendationResult:
        priority = self.assign_priority(failure)
        root_cause = failure.root_cause or self.infer_root_cause(failure)
        recommendation = failure.rule_based_recommendation or (
            "Review the unsupported or unresolved migration behavior in IDMC, redesign the affected object with "
            "supported services or transformation settings, and re-run validation after the manual change."
        )
        summary = (
            "Manual migration review is required because this issue remains unresolved after rule-based validation "
            "and auto-fix processing."
        )
        return RecommendationResult(
            failure=failure,
            recommendation=Recommendation(root_cause, recommendation, priority, summary, confidence=0),
            processing_time_ms=elapsed_ms,
            error=str(exc),
        )

    @staticmethod
    def assign_priority(failure: FailureRecord) -> str:
        text = " ".join(
            [
                failure.failure_type,
                failure.validation_message,
                failure.error_details,
                failure.auto_fix_status,
                failure.severity,
            ]
        ).lower()
        if failure.severity.upper() == "CRITICAL" or any(
            token in text
            for token in ["migration blocker", "unsupported transformation", "xml corruption", "missing object", "repository inconsistency"]
        ):
            return "Critical"
        if failure.severity.upper() == "HIGH" or any(
            token in text for token in ["manual", "unsupported", "data loss", "truncation", "not applied"]
        ):
            return "High"
        if any(token in text for token in ["mismatch", "configuration", "mapping adjustment", "datatype", "schema"]):
            return "Medium"
        return "Low"

    @staticmethod
    def infer_root_cause(failure: FailureRecord) -> str:
        issue = failure.failure_type.replace("_", " ")
        object_name = failure.object_name or failure.mapping
        limitation = "a migration limitation not covered by automated remediation"
        text = f"{failure.failure_type} {failure.validation_message}".lower()
        if "datatype" in text or "precision" in text or "scale" in text:
            limitation = "datatype compatibility differences between PowerCenter metadata and IDMC"
        elif "lookup" in text:
            limitation = "lookup transformation behavior that needs IDMC-specific review"
        elif "sql" in text or "query" in text:
            limitation = "SQL syntax or override behavior that may not translate directly to IDMC"
        elif "parameter" in text:
            limitation = "PowerCenter parameter handling that differs from IDMC parameterization"
        elif "connection" in text:
            limitation = "missing or incompatible connection metadata for IDMC"
        elif "mapplet" in text:
            limitation = "mapplet nesting or reusable logic that requires manual IDMC design"
        return f"{object_name} failed validation for {issue} due to {limitation}."

    def _log_warning(self, message: str, *args: object) -> None:
        if self.logger:
            self.logger.warning(message, *args)
