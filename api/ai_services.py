"""
Support ai services for API endpoints and service integration.
Keeps request handling and AI workflow access organized.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any

from automation.ai import AIRecommendationConfig, AIRecommendationService
from automation.ai.llm_client import RecommendationModelClient
from automation.evaluation_matrix import ReportRepository
from business.validation.ai_evaluation import AIEvaluationBuilder
from business.validation.ai_validation_engine import AIValidationConfig, AIValidationEngine



class AutomationConfigReader:
    """Encapsulates automation config reader behavior for migration workflows."""

    DEFAULT_CONFIG_PATH = Path("config/automation_config.json")

    def __init__(self, config_path: str | Path | None = None) -> None:
        """Initialize migration data using the provided config_path."""

        self.config_path = Path(config_path or self.DEFAULT_CONFIG_PATH)

    def load(self) -> dict[str, Any]:
        """Load migration data for the migration workflow."""

        if not self.config_path.exists():
            return {}
        with self.config_path.open("r", encoding="utf-8-sig") as config_file:
            payload = json.load(config_file)
        return payload if isinstance(payload, dict) else {}

    def ai_validation_max_records(self) -> int | None:
        """Handle ai validation max records for the migration workflow."""

        return self._max_records("ai_validation")

    def ai_validation_config(self) -> AIValidationConfig:
        """Read AI evaluation settings from the latest automation config file."""

        payload = self.load().get("ai_validation", {})
        if not isinstance(payload, dict):
            payload = {}
        defaults = AIValidationConfig()
        return AIValidationConfig(
            model_name=str(payload.get("model_name", defaults.model_name)),
            hf_token_env=str(payload.get("hf_token_env", defaults.hf_token_env)),
            max_records=int(payload.get("max_records", defaults.max_records)),
            max_new_tokens=int(payload.get("max_new_tokens", defaults.max_new_tokens)),
            temperature=float(payload.get("temperature", defaults.temperature)),
            timeout_seconds=int(payload.get("timeout_seconds", defaults.timeout_seconds)),
            high_confidence_threshold=int(payload.get("high_confidence_threshold", defaults.high_confidence_threshold)),
            provider=str(payload.get("provider", defaults.provider)),
            max_workers=int(payload.get("max_workers", defaults.max_workers)),
        )
    def ai_recommendation_config(self) -> AIRecommendationConfig:
        # Mirror only AI recommendation settings into the automation-layer config object.
        """Handle ai recommendation config for the migration workflow."""

        payload = self.load().get("ai_recommendation", {})
        if not isinstance(payload, dict):
            payload = {}
        defaults = AIRecommendationConfig()
        return AIRecommendationConfig(
            model_name=str(payload.get("model_name", defaults.model_name)),
            hf_token_env=str(payload.get("hf_token_env", defaults.hf_token_env)),
            max_records=int(payload.get("max_records", defaults.max_records)),
            max_new_tokens=int(payload.get("max_new_tokens", defaults.max_new_tokens)),
            temperature=float(payload.get("temperature", defaults.temperature)),
            timeout_seconds=int(payload.get("timeout_seconds", defaults.timeout_seconds)),
            provider=str(payload.get("provider", defaults.provider)),
            enabled=bool(payload.get("enabled", defaults.enabled)),
            issue_definitions_path=str(payload.get("issue_definitions_path", defaults.issue_definitions_path)),
            max_workers=int(payload.get("max_workers", defaults.max_workers)),
        )

    def output_folder(self) -> Path:
        """Handle output folder for the migration workflow."""

        value = self.load().get("output_folder", "output")
        return self._resolve(value)

    def reports_folder(self) -> Path:
        """Handle reports folder for the migration workflow."""

        payload = self.load()
        exports = payload.get("exports", {}) if isinstance(payload, dict) else {}
        value = exports.get("reports_folder", "output/automation") if isinstance(exports, dict) else "output/automation"
        return self._resolve(value)

    def _max_records(self, section: str) -> int | None:
        """Handle max records using the provided section."""

        payload = self.load().get(section, {})
        if not isinstance(payload, dict):
            return None
        try:
            return int(payload.get("max_records"))
        except (TypeError, ValueError):
            return None

    def _resolve(self, path: object) -> Path:
        """Handle resolve using the provided path."""

        candidate = Path(str(path))
        if candidate.is_absolute():
            return candidate
        return Path.cwd() / candidate

class APIReportError(ValueError):
    """Represents a migration-specific error condition."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        """Initialize migration data using the provided message and status_code."""

        super().__init__(message)
        self.status_code = status_code


class AIRecommendationAPIService:
    """Coordinates service operations for migration workflows."""

    RESPONSE_COLUMNS = [
        "Workflow -> Session -> Mapping -> Transformations",
        "Assets",
        "Failures",
        "Root Cause",
        "AI Recommendation",
        "Priority",
        "AI Summary",
    ]
    VALIDATION_COLUMNS = {"Issue", "Severity"}

    def __init__(
        self,
        repository: ReportRepository | None = None,
        config: AIRecommendationConfig | None = None,
        client: RecommendationModelClient | None = None,
        logger: logging.Logger | None = None,
        config_reader: AutomationConfigReader | None = None,
    ) -> None:
        """Initialize migration data for the migration workflow."""

        self.repository = repository or ReportRepository()
        self.config_reader = config_reader or AutomationConfigReader()
        self.config = config or self.config_reader.ai_recommendation_config()
        self.client = client
        self.logger = logger

    def recommend(self, max_records: int | None = None) -> list[dict[str, Any]]:
        """Recommend migration data using the provided max_records."""

        started = time.perf_counter()
        self._validate_report("validation_report.csv", self.VALIDATION_COLUMNS)
        config = self.config
        if max_records is not None:
            # Preserve all configured model settings while applying the request row limit.
            config = AIRecommendationConfig(
                model_name=config.model_name,
                hf_token_env=config.hf_token_env,
                max_records=max_records,
                max_new_tokens=config.max_new_tokens,
                temperature=config.temperature,
                timeout_seconds=config.timeout_seconds,
                provider=config.provider,
                enabled=config.enabled,
                issue_definitions_path=config.issue_definitions_path,
                max_workers=config.max_workers,
            )
        try:
            service = AIRecommendationService(self.repository, config, self.client, self.logger)
            results, _ = service.run()
            total_elapsed_ms = int((time.perf_counter() - started) * 1000)
            # Return the same user-facing columns as the generated CSV report.
            rows = [
                {
                    "Workflow -> Session -> Mapping -> Transformations": AIRecommendationService.hierarchy(result),
                    "Assets": result.failure.object_name,
                    "Failures": result.failure.failure_type,
                    "Root Cause": result.recommendation.root_cause,
                    "AI Recommendation": result.recommendation.recommendation,
                    "Priority": result.recommendation.priority,
                    "AI Summary": result.recommendation.summary,
                    "Recommendation Time (sec)": round(total_elapsed_ms / 1000, 2),
                    "Full Automation Time (sec)": self._automation_timing().get("Full Automation Time (sec)", 0),
                }
                for result in results
            ]
            self._log_info("AI recommendation API completed. rows=%s elapsed_ms=%s", len(rows), self._elapsed_ms(started))
            return rows
        except APIReportError:
            raise
        except Exception as exc:
            self._log_error("AI recommendation API failed: %s", exc)
            raise APIReportError(str(exc), status_code=500) from exc

    def _automation_timing(self) -> dict[str, Any]:
        """Read the latest automation timing summary if it exists."""

        candidates = [
            self.repository.reports_folder / "automation_timing_summary.json",
            self.repository.output_folder / "automation" / "automation_timing_summary.json",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as json_file:
                    payload = json.load(json_file)
            except ValueError:
                return {}
            return payload if isinstance(payload, dict) else {}
        return {}
    def _validate_report(self, relative_path: str, required_columns: set[str]) -> None:
        """Validate report using the provided relative_path and required_columns."""

        path = self.repository.output_folder / relative_path
        path = self.repository._preferred_existing_path(path)
        if not path.exists():
            raise APIReportError(f"Missing report: {relative_path}", status_code=404)
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            fieldnames = set(reader.fieldnames or [])
            missing = sorted(required_columns - fieldnames)
            if missing:
                raise APIReportError(
                    f"Invalid report format for {relative_path}. Missing column(s): {', '.join(missing)}",
                    status_code=422,
                )

    def _log_info(self, message: str, *args: object) -> None:
        """Handle log info using the provided message and args."""

        if self.logger:
            self.logger.info(message, *args)

    def _log_error(self, message: str, *args: object) -> None:
        """Handle log error using the provided message and args."""

        if self.logger:
            self.logger.error(message, *args)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        """Handle elapsed ms using the provided started."""

        return int((time.perf_counter() - started) * 1000)


class AIEvaluationAPIService:
    """Coordinates service operations for migration workflows."""

    MATRIX_COLUMNS = [
        "Average Confidence",
        "F1 Score",
        "ML Accuracy",
        "ML Precision",
        "Model Success Rate",
        "Recall",
        "Total Evaluations",
        "AI Evaluation Time (sec)",
        "Full Automation Time (sec)",
        "End-to-End Process Time (with MySQL) (sec)",
    ]

    def __init__(
        self,
        repository: ReportRepository | None = None,
        logger: logging.Logger | None = None,
        config_reader: AutomationConfigReader | None = None,
    ) -> None:
        """Initialize migration data for the migration workflow."""

        self.repository = repository or ReportRepository()
        self.logger = logger
        self.config_reader = config_reader or AutomationConfigReader()

    def evaluation(self, refresh: bool = False) -> dict[str, dict[str, Any]]:
        """Handle evaluation using the provided refresh."""

        self._refresh_automation_outputs_if_needed(force=refresh)
        path = self._summary_path()
        if not path.exists():
            dataset_response = self._evaluation_from_dataset()
            if dataset_response:
                return dataset_response
            raise APIReportError("Missing report: ai_evaluation_summary.json", status_code=404)
        try:
            import json

            with path.open("r", encoding="utf-8") as json_file:
                payload = json.load(json_file)
        except ValueError as exc:
            raise APIReportError("Invalid AI evaluation summary JSON", status_code=422) from exc
        matrix = payload.get("matrix", {})
        if not isinstance(matrix, dict):
            raise APIReportError("Invalid AI evaluation summary format", status_code=422)
        timing = self._automation_timing()
        response = {
            "matrix": {
                "Average Confidence": self._number(matrix.get("Average Confidence")),
                "F1 Score": self._number(matrix.get("F1 Score")),
                "ML Accuracy": self._number(matrix.get("ML Accuracy", matrix.get("Accuracy"))),
                "ML Precision": self._number(matrix.get("ML Precision", matrix.get("Precision"))),
                "Model Success Rate": self._number(matrix.get("Model Success Rate")),
                "Recall": self._number(matrix.get("Recall")),
                "Total Evaluations": self._number(matrix.get("Total Evaluations")),
                "AI Evaluation Time (sec)": self._number(matrix.get("AI Evaluation Time (sec)", matrix.get("Total Processing Time (sec)"))),
                "Full Automation Time (sec)": self._number(timing.get("Full Automation Time (sec)")),
                "End-to-End Process Time (with MySQL) (sec)": self._number(timing.get("End-to-End Process Time (with MySQL) (sec)")),
            }
        }
        if self.logger:
            self.logger.info("AI evaluation API completed from %s", path)
        return response

    def _evaluation_from_dataset(self) -> dict[str, dict[str, Any]]:
        """Handle evaluation from dataset for the migration workflow."""

        path = self._dataset_path()
        if not path.exists():
            return {}
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            rows = list(csv.DictReader(csv_file))
        if not rows:
            return {}

        valid_rows = [
            row
            for row in rows
            if self._decision(row.get("ground_truth")) in {"PASS", "FAIL"}
            and self._decision(row.get("ml_decision")) in {"PASS", "FAIL"}
        ]
        if not valid_rows:
            return {
                "matrix": {
                    "Average Confidence": self._average(row.get("confidence") for row in rows),
                    "F1 Score": 0,
                    "ML Accuracy": 0,
                    "ML Precision": 0,
                    "Model Success Rate": 0,
                    "Recall": 0,
                    "Total Evaluations": len(rows),
                    "AI Evaluation Time (sec)": round(max((self._number(row.get("processing_time_ms")) for row in rows), default=0) / 1000, 2),
                    "Full Automation Time (sec)": self._number(self._automation_timing().get("Full Automation Time (sec)")),
                    "End-to-End Process Time (with MySQL) (sec)": self._number(self._automation_timing().get("End-to-End Process Time (with MySQL) (sec)")),
                }
            }

        tp = tn = fp = fn = 0
        for row in valid_rows:
            expected = self._decision(row.get("ground_truth"))
            predicted = self._decision(row.get("ml_decision"))
            if expected == "FAIL" and predicted == "FAIL":
                tp += 1
            elif expected == "PASS" and predicted == "PASS":
                tn += 1
            elif expected == "PASS" and predicted == "FAIL":
                fp += 1
            elif expected == "FAIL" and predicted == "PASS":
                fn += 1

        precision = self._percentage(tp, tp + fp)
        recall = self._percentage(tp, tp + fn)
        f1_score = round((2 * precision * recall) / (precision + recall), 2) if precision + recall else 0
        response = {
            "matrix": {
                "Average Confidence": self._average(row.get("confidence") for row in valid_rows),
                "F1 Score": f1_score,
                "ML Accuracy": self._percentage(tp + tn, len(valid_rows)),
                "ML Precision": precision,
                "Model Success Rate": self._percentage(len(valid_rows), len(rows)),
                "Recall": recall,
                "Total Evaluations": len(rows),
                "AI Evaluation Time (sec)": round(max((self._number(row.get("processing_time_ms")) for row in rows), default=0) / 1000, 2),
                "Full Automation Time (sec)": self._number(self._automation_timing().get("Full Automation Time (sec)")),
                "End-to-End Process Time (with MySQL) (sec)": self._number(self._automation_timing().get("End-to-End Process Time (with MySQL) (sec)")),
            }
        }
        if self.logger:
            self.logger.info("AI evaluation API completed from %s", path)
        return response

    def _refresh_automation_outputs_if_needed(self, force: bool = False) -> None:
        """Refresh only AI evaluation artifacts when explicitly requested by the UI."""

        if not force:
            return
        config = self.config_reader.ai_validation_config()
        started = time.perf_counter()
        validation_engine = AIValidationEngine(self.repository, config)
        ai_results = validation_engine.validate()
        builder = AIEvaluationBuilder(
            self.repository,
            high_confidence_threshold=config.high_confidence_threshold,
        )
        ai_dataset = builder.build_dataset(ai_results)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        ai_summary = builder.summarize(ai_results, ai_dataset, elapsed_ms, config.max_records)
        builder.write(ai_dataset, ai_summary)
        error_rows = [row for row in ai_dataset if row.get("ml_decision") == "ERROR"]
        if error_rows:
            self._log_info(
                "AI evaluation refresh completed with error rows. rows=%s errors=%s elapsed_ms=%s max_records=%s",
                len(ai_dataset),
                len(error_rows),
                elapsed_ms,
                config.max_records,
            )
        else:
            self._log_info(
                "AI evaluation refresh completed. rows=%s elapsed_ms=%s max_records=%s",
                len(ai_dataset),
                elapsed_ms,
                config.max_records,
            )
        return

    def _summary_configured_max_records(self) -> int | None:
        """Return the max_records value used to generate the current AI summary."""

        path = self._summary_path()
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as json_file:
                payload = json.load(json_file)
        except ValueError:
            return None
        matrix = payload.get("matrix", {}) if isinstance(payload, dict) else {}
        value = matrix.get("Configured Max Records") if isinstance(matrix, dict) else None
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            return None
    def _uses_configured_repository(self) -> bool:
        """Handle uses configured repository for the migration workflow."""

        return (
            self.repository.output_folder.resolve() == self.config_reader.output_folder().resolve()
            and self.repository.reports_folder.resolve() == self.config_reader.reports_folder().resolve()
        )

    def _dataset_row_count(self) -> int:
        """Handle dataset row count for the migration workflow."""

        path = self._dataset_path()
        if not path.exists():
            return 0
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return sum(1 for _ in csv.DictReader(csv_file))

    def _log_info(self, message: str, *args: object) -> None:
        """Handle log info using the provided message and args."""

        if self.logger:
            self.logger.info(message, *args)
    def _automation_timing(self) -> dict[str, Any]:
        """Read the latest automation timing summary if it exists."""

        candidates = [
            self.repository.reports_folder / "automation_timing_summary.json",
            self.repository.output_folder / "automation" / "automation_timing_summary.json",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                with path.open("r", encoding="utf-8") as json_file:
                    payload = json.load(json_file)
            except ValueError:
                return {}
            return payload if isinstance(payload, dict) else {}
        return {}
    def _summary_path(self) -> Path:
        """Handle summary path for the migration workflow."""

        candidates = [
            self.repository.reports_folder / "ai_evaluation_summary.json",
            self.repository.output_folder / "automation" / "ai_evaluation_summary.json",
        ]
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    def _dataset_path(self) -> Path:
        """Handle dataset path for the migration workflow."""

        candidates = [
            self.repository.reports_folder / "ai_evaluation_dataset.csv",
            self.repository.output_folder / "automation" / "ai_evaluation_dataset.csv",
        ]
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    @staticmethod
    def _number(value: object) -> int | float:
        """Handle number using the provided value."""

        if value in {None, ""}:
            return 0
        try:
            number = float(str(value))
        except ValueError:
            return 0
        return int(number) if number.is_integer() else number

    @classmethod
    def _average(cls, values: Any) -> int | float:
        """Handle average using the provided values."""

        numbers = [float(value) for value in values if cls._is_number(value)]
        if not numbers:
            return 0
        average = round(sum(numbers) / len(numbers), 2)
        return int(average) if average.is_integer() else average

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> int | float:
        """Handle percentage using the provided numerator and denominator."""

        if denominator <= 0:
            return 0
        value = round((numerator / denominator) * 100, 2)
        return int(value) if value.is_integer() else value

    @staticmethod
    def _decision(value: object) -> str:
        """Handle decision using the provided value."""

        normalized = str(value or "").strip().upper()
        if normalized in {"PASS", "PASSED", "READY", "RESOLVED", "TRUE", "YES"}:
            return "PASS"
        if normalized in {"FAIL", "FAILED", "NOT_READY", "NOT READY", "OPEN", "FALSE", "NO"}:
            return "FAIL"
        return normalized or "UNKNOWN"

    @staticmethod
    def _is_number(value: object) -> bool:
        """Handle is number using the provided value."""

        try:
            float(str(value))
        except (TypeError, ValueError):
            return False
        return True








