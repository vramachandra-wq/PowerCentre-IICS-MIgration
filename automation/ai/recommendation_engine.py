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
        migration_context = self._migration_context()
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
            migration_context=migration_context,
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
            if "manual" in status.lower():
                return "Needs Migration Review"
            return status
        if str(row.get("Manual Remediation Required", "")).strip().lower() == "true":
            return "Needs Migration Review"
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
        recommendation = RecommendationResponseParser._sanitize_text(self._consultant_recommendation(failure, priority))
        summary = self._executive_summary(failure, priority)
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
            limitation = "mapplet nesting or reusable logic that requires IDMC design review"
        return f"{object_name} failed validation for {issue} due to {limitation}."

    @classmethod
    def _consultant_recommendation(cls, failure: FailureRecord, priority: str) -> str:
        issue = failure.failure_type.replace("_", " ")
        object_name = failure.object_name or failure.mapping
        context = failure.migration_context
        readiness = cls._number(context.get("estimated_migration_readiness"))
        success_rate = cls._number(context.get("migration_success_rate"))
        base_guidance = failure.rule_based_recommendation.strip()

        if "mapplet" in failure.failure_type.lower():
            action = (
                "Rework the reusable logic into an IDMC-supported mapping design, validating port alignment, "
                "execution order, and reusable component behavior before deployment."
            )
        elif any(token in failure.failure_type.lower() for token in ["datatype", "precision", "scale", "truncation"]):
            action = (
                "Align the affected source, transformation, and target metadata with IDMC-supported datatype, "
                "precision, scale, and length handling, then validate row counts and representative data samples."
            )
        elif "lookup" in failure.failure_type.lower():
            action = (
                "Review the lookup configuration against IDMC transformation capabilities, replace unsupported "
                "PowerCenter-specific behavior with supported lookup settings, and validate cache and match behavior."
            )
        elif any(token in failure.failure_type.lower() for token in ["sql", "query", "schema"]):
            action = (
                "Refactor the SQL or schema-dependent logic for the target IDMC runtime and database connector, "
                "then validate generated queries, pushdown behavior, and expected result sets."
            )
        elif "connection" in failure.failure_type.lower():
            action = (
                "Update the IDMC connection configuration and object bindings, confirm credential and connector "
                "compatibility, and validate runtime execution through the associated mapping task."
            )
        else:
            action = (
                "Assess the unresolved construct against IDMC-supported design patterns, apply the appropriate "
                "configuration update, and validate the migrated behavior through mapping task execution."
            )

        rule_context = f" Existing rule guidance should be incorporated: {base_guidance}" if base_guidance else ""
        return (
            f"{priority} priority migration assistance is recommended for {object_name} because the {issue} finding "
            f"remains outside automated conversion coverage. {action}{rule_context} "
            f"This recommendation supports a readiness posture of {readiness:g}% and a conversion success rate of "
            f"{success_rate:g}%, while reducing deployment risk through focused functional validation."
        )

    def _migration_context(self) -> dict[str, object]:
        matrix_rows = self.repository.read_csv("automation/evaluation_matrix.csv")
        validation_summary = self.repository.read_json("automation/validation_summary.json")
        consolidated = self.repository.read_json("automation/consolidated_findings.json")
        ai_summary = self.repository.read_json("automation/ai_evaluation_summary.json")
        ai_matrix = ai_summary.get("matrix", {}) if isinstance(ai_summary, dict) else {}

        total_mappings = len(matrix_rows)
        successful_conversions = sum(
            1
            for row in matrix_rows
            if row.get("migration_status", "").upper() in {"READY", "READY_WITH_MONITORING"}
        )
        success_rate = self._percentage(successful_conversions, total_mappings)
        average_readiness = self._average(row.get("readiness_after") for row in matrix_rows)
        average_risk = self._average(row.get("risk_after") for row in matrix_rows)
        high_risk_mappings = sum(
            1 for row in matrix_rows if row.get("risk_category", "").upper() in {"HIGH", "CRITICAL"}
        )
        unsupported_objects = sum(1 for row in matrix_rows if self._to_int(row.get("manual_remediation")) > 0)
        readiness = 0.0
        if isinstance(validation_summary, dict):
            readiness = self._number(validation_summary.get("overall_readiness"))
        return {
            "migration_success_rate": success_rate,
            "successful_conversions": successful_conversions,
            "total_mappings": total_mappings,
            "validation_accuracy": self._number(ai_matrix.get("Valid Prediction Accuracy") or ai_matrix.get("Accuracy")),
            "rule_engine_findings": consolidated.get("total_validation_failures", 0)
            if isinstance(consolidated, dict)
            else 0,
            "ai_assisted_recommendations": self._to_int(ai_matrix.get("Total Rules")),
            "unsupported_object_count": unsupported_objects,
            "high_risk_mapping_count": high_risk_mappings,
            "average_risk_score": average_risk,
            "estimated_migration_readiness": readiness or average_readiness,
        }

    @classmethod
    def _executive_summary(cls, failure: FailureRecord, priority: str) -> str:
        context = failure.migration_context
        success_rate = cls._number(context.get("migration_success_rate"))
        successful = cls._to_int(context.get("successful_conversions"))
        total = cls._to_int(context.get("total_mappings"))
        validation_accuracy = cls._number(context.get("validation_accuracy"))
        readiness = cls._number(context.get("estimated_migration_readiness"))
        findings = cls._to_int(context.get("rule_engine_findings"))
        ai_recommendations = cls._to_int(context.get("ai_assisted_recommendations"))
        unsupported = cls._to_int(context.get("unsupported_object_count"))
        high_risk = cls._to_int(context.get("high_risk_mapping_count"))

        if success_rate > 95:
            posture = "excellent migration readiness with minimal post-conversion review effort"
        elif success_rate >= 80:
            posture = "strong migration readiness with focused AI-assisted validation recommendations"
        else:
            posture = "moderate migration complexity that benefits from phased remediation before deployment"

        return (
            f"The migration assessment indicates {posture}. "
            f"{successful} of {total} mappings are currently tracking as successful conversions, with an estimated "
            f"readiness score of {readiness:g}% and validation accuracy of {validation_accuracy:g}%. "
            f"The rule engine identified {findings} validation findings, while {ai_recommendations} AI-assisted "
            f"recommendations highlight platform-specific behavior, unsupported constructs, or configuration areas "
            f"that need migration review. The current item is classified as {priority} priority, with {unsupported} "
            f"unsupported or complex objects and {high_risk} high-risk mappings visible in the assessment baseline. "
            "Addressing these recommendations is expected to improve conversion quality, strengthen functional "
            "validation, and reduce deployment risk. Overall, the migration remains technically feasible when the "
            "identified recommendations are incorporated into the readiness plan."
        )

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round((numerator / denominator) * 100, 2)

    @classmethod
    def _average(cls, values: Iterable[object]) -> float:
        numbers = [cls._number(value) for value in values if cls._is_number(value)]
        if not numbers:
            return 0.0
        return round(sum(numbers) / len(numbers), 2)

    @staticmethod
    def _number(value: object) -> float:
        try:
            return float(str(value))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _to_int(value: object) -> int:
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _is_number(value: object) -> bool:
        try:
            float(str(value))
        except (TypeError, ValueError):
            return False
        return True

    def _log_warning(self, message: str, *args: object) -> None:
        if self.logger:
            self.logger.warning(message, *args)
