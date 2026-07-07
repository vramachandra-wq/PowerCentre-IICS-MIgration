"""
Module: api/ai_services.py

Purpose:
    This module supports FastAPI service layer for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the FastAPI service layer area and exposes validation, recommendation, and evaluation results to UI and integration clients. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import csv
import json
import logging
import time
from pathlib import Path
from typing import Any

from automation.ai import AIRecommendationConfig, AIRecommendationService
from automation.automated_validation_framework import AutomatedValidationFramework
from automation.ai.llm_client import RecommendationModelClient
from automation.evaluation_matrix import ReportRepository



class AutomationConfigReader:
    """Reads API-relevant automation settings from automation_config.json."""

    DEFAULT_CONFIG_PATH = Path("config/automation_config.json")

    def __init__(self, config_path: str | Path | None = None) -> None:
        """
        Executes the __init__ workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                config_path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.config_path = Path(config_path or self.DEFAULT_CONFIG_PATH)

    def load(self) -> dict[str, Any]:
        """
        Executes the load workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not self.config_path.exists():
            return {}
        with self.config_path.open("r", encoding="utf-8-sig") as config_file:
            payload = json.load(config_file)
        return payload if isinstance(payload, dict) else {}

    def ai_validation_max_records(self) -> int | None:
        """
        Executes the ai_validation_max_records workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return self._max_records("ai_validation")

    def ai_recommendation_config(self) -> AIRecommendationConfig:
        # Mirror only AI recommendation settings into the automation-layer config object.
        """
        Executes the ai_recommendation_config workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        )

    def output_folder(self) -> Path:
        """
        Executes the output_folder workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        value = self.load().get("output_folder", "output")
        return self._resolve(value)

    def reports_folder(self) -> Path:
        """
        Executes the reports_folder workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        payload = self.load()
        exports = payload.get("exports", {}) if isinstance(payload, dict) else {}
        value = exports.get("reports_folder", "output/automation") if isinstance(exports, dict) else "output/automation"
        return self._resolve(value)

    def _max_records(self, section: str) -> int | None:
        """
        Executes the _max_records workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                section (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        payload = self.load().get(section, {})
        if not isinstance(payload, dict):
            return None
        try:
            return int(payload.get("max_records"))
        except (TypeError, ValueError):
            return None

    def _resolve(self, path: object) -> Path:
        """
        Executes the _resolve workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        candidate = Path(str(path))
        if candidate.is_absolute():
            return candidate
        return Path.cwd() / candidate

class APIReportError(ValueError):
    """Raised when an API report source is missing or invalid."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        """
        Executes the __init__ workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                message (object): Value supplied by the caller and used by the workflow.
                status_code (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        super().__init__(message)
        self.status_code = status_code


class AIRecommendationAPIService:
    """Thin API adapter over the automation-layer recommendation service."""

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
        """
        Executes the __init__ workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                repository (object): Value supplied by the caller and used by the workflow.
                config (object): Value supplied by the caller and used by the workflow.
                client (object): Value supplied by the caller and used by the workflow.
                logger (object): Value supplied by the caller and used by the workflow.
                config_reader (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.repository = repository or ReportRepository()
        self.config_reader = config_reader or AutomationConfigReader()
        self.config = config or self.config_reader.ai_recommendation_config()
        self.client = client
        self.logger = logger

    def recommend(self, max_records: int | None = None) -> list[dict[str, Any]]:
        """
        Executes the recommend workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                max_records (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
            )
        try:
            service = AIRecommendationService(self.repository, config, self.client, self.logger)
            results, _ = service.run()
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

    def _validate_report(self, relative_path: str, required_columns: set[str]) -> None:
        """
        Executes the _validate_report workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                relative_path (object): Value supplied by the caller and used by the workflow.
                required_columns (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the _log_info workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                message (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if self.logger:
            self.logger.info(message, *args)

    def _log_error(self, message: str, *args: object) -> None:
        """
        Executes the _log_error workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                message (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if self.logger:
            self.logger.error(message, *args)

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        """
        Executes the _elapsed_ms workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                started (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return int((time.perf_counter() - started) * 1000)


class AIEvaluationAPIService:
    """Reads the existing AI evaluation summary and exposes the approved metrics only."""

    MATRIX_COLUMNS = [
        "Average Confidence",
        "F1 Score",
        "ML Accuracy",
        "ML Precision",
        "Model Success Rate",
        "Recall",
        "Total Evaluations",
    ]

    def __init__(
        self,
        repository: ReportRepository | None = None,
        logger: logging.Logger | None = None,
        config_reader: AutomationConfigReader | None = None,
    ) -> None:
        """
        Executes the __init__ workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                repository (object): Value supplied by the caller and used by the workflow.
                logger (object): Value supplied by the caller and used by the workflow.
                config_reader (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.repository = repository or ReportRepository()
        self.logger = logger
        self.config_reader = config_reader or AutomationConfigReader()

    def evaluation(self, refresh: bool = False) -> dict[str, dict[str, Any]]:
        """
        Executes the evaluation workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                refresh (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self._refresh_automation_outputs_if_needed(force=refresh)
        dataset_response = self._evaluation_from_dataset()
        if dataset_response:
            return dataset_response

        path = self._summary_path()
        if not path.exists():
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
        response = {
            "matrix": {
                "Average Confidence": self._number(matrix.get("Average Confidence")),
                "F1 Score": self._number(matrix.get("F1 Score")),
                "ML Accuracy": self._number(matrix.get("ML Accuracy", matrix.get("Accuracy"))),
                "ML Precision": self._number(matrix.get("ML Precision", matrix.get("Precision"))),
                "Model Success Rate": self._number(matrix.get("Model Success Rate")),
                "Recall": self._number(matrix.get("Recall")),
                "Total Evaluations": self._number(matrix.get("Total Evaluations")),
            }
        }
        if self.logger:
            self.logger.info("AI evaluation API completed from %s", path)
        return response

    def _evaluation_from_dataset(self) -> dict[str, dict[str, Any]]:
        """
        Executes the _evaluation_from_dataset workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
            }
        }
        if self.logger:
            self.logger.info("AI evaluation API completed from %s", path)
        return response

    def _refresh_automation_outputs_if_needed(self, force: bool = False) -> None:
        """
        Executes the _refresh_automation_outputs_if_needed workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                force (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not self._uses_configured_repository():
            return
        expected_records = self.config_reader.ai_validation_max_records()
        if not force and (expected_records is None or self._dataset_row_count() == expected_records):
            return
        self._log_info(
            "Refreshing automation outputs from FastAPI. expected_ai_validation_records=%s current_records=%s force=%s",
            expected_records,
            self._dataset_row_count(),
            force,
        )
        AutomatedValidationFramework(config_path=self.config_reader.config_path).run()

    def _uses_configured_repository(self) -> bool:
        """
        Executes the _uses_configured_repository workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return (
            self.repository.output_folder.resolve() == self.config_reader.output_folder().resolve()
            and self.repository.reports_folder.resolve() == self.config_reader.reports_folder().resolve()
        )

    def _dataset_row_count(self) -> int:
        """
        Executes the _dataset_row_count workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        path = self._dataset_path()
        if not path.exists():
            return 0
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return sum(1 for _ in csv.DictReader(csv_file))

    def _log_info(self, message: str, *args: object) -> None:
        """
        Executes the _log_info workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                message (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if self.logger:
            self.logger.info(message, *args)
    def _summary_path(self) -> Path:
        """
        Executes the _summary_path workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        candidates = [
            self.repository.reports_folder / "ai_evaluation_summary.json",
            self.repository.output_folder / "automation" / "ai_evaluation_summary.json",
        ]
        for path in candidates:
            if path.exists():
                return path
        return candidates[0]

    def _dataset_path(self) -> Path:
        """
        Executes the _dataset_path workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the _number workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if value in {None, ""}:
            return 0
        try:
            number = float(str(value))
        except ValueError:
            return 0
        return int(number) if number.is_integer() else number

    @classmethod
    def _average(cls, values: Any) -> int | float:
        """
        Executes the _average workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                values (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        numbers = [float(value) for value in values if cls._is_number(value)]
        if not numbers:
            return 0
        average = round(sum(numbers) / len(numbers), 2)
        return int(average) if average.is_integer() else average

    @staticmethod
    def _percentage(numerator: int, denominator: int) -> int | float:
        """
        Executes the _percentage workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                numerator (object): Value supplied by the caller and used by the workflow.
                denominator (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if denominator <= 0:
            return 0
        value = round((numerator / denominator) * 100, 2)
        return int(value) if value.is_integer() else value

    @staticmethod
    def _decision(value: object) -> str:
        """
        Executes the _decision workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        normalized = str(value or "").strip().upper()
        if normalized in {"PASS", "PASSED", "READY", "RESOLVED", "TRUE", "YES"}:
            return "PASS"
        if normalized in {"FAIL", "FAILED", "NOT_READY", "NOT READY", "OPEN", "FALSE", "NO"}:
            return "FAIL"
        return normalized or "UNKNOWN"

    @staticmethod
    def _is_number(value: object) -> bool:
        """
        Executes the _is_number workflow for FastAPI service layer.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                value (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        try:
            float(str(value))
        except (TypeError, ValueError):
            return False
        return True






