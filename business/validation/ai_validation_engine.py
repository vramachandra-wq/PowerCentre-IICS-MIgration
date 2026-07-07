"""
Module: business/validation/ai_validation_engine.py

Purpose:
    This module supports migration validation and readiness logic for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the migration validation and readiness logic area and evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from automation.evaluation_matrix import ReportRepository
from automation.metrics import MetricsCalculator
from business.validation.readiness_engine import RemediationReportLoader

class AIModelClient(Protocol):
    """Swappable LLM client used by the AI validation layer."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Executes the validate workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                payload (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        ...


@dataclass(frozen=True)
class AIValidationConfig:
    """Runtime settings for the model-backed validation layer."""

    model_name: str = "Qwen/Qwen3-8B"
    hf_token_env: str = "HF_TOKEN"
    max_records: int = 200
    max_new_tokens: int = 256
    temperature: float = 0.0
    timeout_seconds: int = 60
    high_confidence_threshold: int = 90
    provider: str = "auto"


@dataclass(frozen=True)
class AIValidationInput:
    """
    Represents the AIValidationInput component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    mapping_name: str
    rule_name: str
    ground_truth: str
    details: str
    expected_recommendation: str = ""
    expected_readiness: str = ""
    expected_risk: str = ""


@dataclass(frozen=True)
class AIValidationPrediction:
    """
    Represents the AIValidationPrediction component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    decision: str
    confidence: int
    reason: str = ""
    recommendation: str = ""
    readiness_prediction: str = ""
    risk_prediction: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    error: str = ""


@dataclass(frozen=True)
class AIValidationResult:
    """
    Represents the AIValidationResult component in the migration validation and readiness logic area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    input: AIValidationInput
    prediction: AIValidationPrediction
    processing_time_ms: int


class HuggingFaceQwenClient:
    """Qwen client backed by Hugging Face chat completion."""

    def __init__(self, config: AIValidationConfig) -> None:
        """
        Executes the __init__ workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                config (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            self._load_env_file(Path(".env"))
        token = os.getenv(config.hf_token_env)
    
        if not token:
            raise ValueError(f"Missing Hugging Face token in environment variable {config.hf_token_env}")
        self.config = config
        self.token = token

    @staticmethod
    def _load_env_file(path: Path) -> None:
        """
        Executes the _load_env_file workflow for migration validation and readiness logic.
        
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
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        if not path.exists():
            return
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Executes the validate workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                payload (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        try:
            import truststore

            truststore.inject_into_ssl()
        except ImportError:
            pass
        from huggingface_hub import InferenceClient

        provider = None if self.config.provider == "auto" else self.config.provider
        client = InferenceClient(
            model=self.config.model_name,
            provider=provider,
            token=self.token,
            timeout=self.config.timeout_seconds,
        )
        prompt = self._prompt(payload)
        response = client.chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "You validate PowerCenter to IDMC migration findings. Return JSON only. /no_think",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=self.config.max_new_tokens,
            temperature=self.config.temperature,
        )
        content = response.choices[0].message.content or "{}"
        result = AIResponseParser.parse(content)
        usage = getattr(response, "usage", None)
        if usage:
            result.setdefault("prompt_tokens", int(getattr(usage, "prompt_tokens", 0) or 0))
            result.setdefault("completion_tokens", int(getattr(usage, "completion_tokens", 0) or 0))
            result.setdefault("total_tokens", int(getattr(usage, "total_tokens", 0) or 0))
        return result

    @staticmethod
    def _prompt(payload: dict[str, Any]) -> str:
        """
        Executes the _prompt workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                payload (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return (
            "Compare the supplied migration validation record against IDMC migration rules. "
            "Return only valid JSON with keys: decision, confidence, reason, recommendation, "
            "readiness_prediction, risk_prediction. decision must be PASS or FAIL. "
            "confidence must be 0-100.\n\n"
            f"Validation record:\n{json.dumps(payload, indent=2, sort_keys=True)}"
        )


class AIResponseParser:
    """Parses strict JSON model output and normalizes malformed or partial responses."""

    @staticmethod
    def parse(content: str) -> dict[str, Any]:
        """
        Executes the parse workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                content (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content or "", flags=re.IGNORECASE).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if not match:
                raise ValueError(f"Invalid AI JSON response: {cleaned[:300]}")
            payload = json.loads(match.group(0))
        if not isinstance(payload, dict):
            raise ValueError("AI response must be a JSON object")
        if "decision" not in payload:
            raise ValueError(f"AI JSON missing required decision field: {payload}")
        return payload


class AIValidationInputBuilder:
    """Builds model inputs from rule-engine reports without duplicating validation logic."""

    def __init__(self, repository: ReportRepository) -> None:
        """
        Executes the __init__ workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                repository (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.repository = repository
        self.report_loader = RemediationReportLoader(repository.output_folder)

    def build(self, max_records: int | None = None) -> list[AIValidationInput]:
        """
        Executes the build workflow for migration validation and readiness logic.
        
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
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        readiness = self._index(self.repository.read_csv("post_remediation_migration_readiness_report.csv"), "mapping_name")
        risk = self._index(self.repository.read_csv("risk_assessment_report.csv"), "mapping_name")
        remediation_rows = self.repository.read_csv("remediation_report.csv")
        validation_rows = self.repository.read_csv("validation_report.csv")

        inputs = [self._from_remediation(row, readiness, risk) for row in remediation_rows]
        if not inputs:
            inputs = [self._from_validation(row, readiness, risk) for row in validation_rows]
        if max_records is not None and max_records > 0:
            return self._balanced_sample(inputs, max_records)
        return inputs


    @staticmethod
    def _balanced_sample(inputs: list[AIValidationInput], max_records: int) -> list[AIValidationInput]:
        """
        Executes the _balanced_sample workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                inputs (object): Value supplied by the caller and used by the workflow.
                max_records (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        failures = [item for item in inputs if item.ground_truth == "FAIL"]
        passes = [item for item in inputs if item.ground_truth == "PASS"]
        selected = failures[:max_records]
        remaining = max_records - len(selected)
        if remaining > 0:
            selected.extend(passes[:remaining])
        return selected

    def _from_remediation(
        self,
        row: dict[str, str],
        readiness: dict[str, dict[str, str]],
        risk: dict[str, dict[str, str]],
    ) -> AIValidationInput:
        """
        Executes the _from_remediation workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                row (object): Value supplied by the caller and used by the workflow.
                readiness (object): Value supplied by the caller and used by the workflow.
                risk (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        mapping = self.report_loader._mapping_from_row(row) or self._mapping_name(row)
        readiness_row = readiness.get(mapping, {})
        risk_row = risk.get(mapping, {})
        ground_truth = "PASS" if self._resolved(row) else "FAIL"
        return AIValidationInput(
            mapping_name=mapping,
            rule_name=row.get("Issue", ""),
            ground_truth=ground_truth,
            details=(
                f"Severity={row.get('Severity', '')}; Status={row.get('Status', '')}; "
                f"Auto Fixed={row.get('Auto Fixed', '')}; Before={row.get('Before Value', '')}; "
                f"After={row.get('After Value', '')}"
            ),
            expected_recommendation=row.get("Recommendation", ""),
            expected_readiness=readiness_row.get("readiness_category", ""),
            expected_risk=risk_row.get("risk_level", ""),
        )

    def _from_validation(
        self,
        row: dict[str, str],
        readiness: dict[str, dict[str, str]],
        risk: dict[str, dict[str, str]],
    ) -> AIValidationInput:
        """
        Executes the _from_validation workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                row (object): Value supplied by the caller and used by the workflow.
                readiness (object): Value supplied by the caller and used by the workflow.
                risk (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        mapping = self.report_loader._mapping_from_row(row) or self._mapping_name(row)
        readiness_row = readiness.get(mapping, {})
        risk_row = risk.get(mapping, {})
        return AIValidationInput(
            mapping_name=mapping,
            rule_name=row.get("Rule ID") or row.get("Issue", ""),
            ground_truth="FAIL",
            details=f"Issue={row.get('Issue', '')}; Severity={row.get('Severity', '')}; Asset={row.get('Asset', '')}",
            expected_recommendation=row.get("Recommendation", ""),
            expected_readiness=readiness_row.get("readiness_category", ""),
            expected_risk=risk_row.get("risk_level", ""),
        )

    @staticmethod
    def _resolved(row: dict[str, str]) -> bool:
        """
        Executes the _resolved workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                row (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return row.get("Auto Fixed", "").strip().lower() == "true" or row.get("Status", "").strip().lower() in {
            "resolved",
            "suppressed",
        }

    @staticmethod
    def _mapping_name(row: dict[str, str]) -> str:
        """
        Executes the _mapping_name workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                row (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        for field in ["mapping_name", "Mapping Name", "Asset"]:
            if row.get(field):
                value = row[field]
                return Path(value).stem if value.lower().endswith(".xml") else value
        source_file = row.get("source_file") or row.get("Source File") or row.get("file_name") or ""
        return Path(source_file).stem if source_file else "UNMAPPED_ASSET"

    @staticmethod
    def _index(rows: Iterable[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
        """
        Executes the _index workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                rows (object): Value supplied by the caller and used by the workflow.
                key (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return {row.get(key, ""): row for row in rows if row.get(key)}


class AIValidationEngine:
    """Runs the configured AI model against rule-engine ground-truth records."""

    def __init__(
        self,
        repository: ReportRepository | None = None,
        config: AIValidationConfig | None = None,
        client: AIModelClient | None = None,
    ) -> None:
        """
        Executes the __init__ workflow for migration validation and readiness logic.
        
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
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.repository = repository or ReportRepository()
        self.config = config or AIValidationConfig()
        self.client = client

    def validate(self) -> list[AIValidationResult]:
        """
        Executes the validate workflow for migration validation and readiness logic.
        
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
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        inputs = AIValidationInputBuilder(self.repository).build(self.config.max_records)
        if not inputs:
            return []
        try:
            client = self.client or HuggingFaceQwenClient(self.config)
        except Exception as exc:
            return [self._error_result(item, exc, 0) for item in inputs]

        results: list[AIValidationResult] = []
        for item in inputs:
            started = time.perf_counter()
            try:
                raw = client.validate(asdict(item))
                elapsed = int((time.perf_counter() - started) * 1000)
                results.append(AIValidationResult(item, self._prediction(raw), elapsed))
            except Exception as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                results.append(self._error_result(item, exc, elapsed))
        return results

    @staticmethod
    def _prediction(payload: dict[str, Any]) -> AIValidationPrediction:
        """
        Executes the _prediction workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                payload (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        confidence = max(0, min(MetricsCalculator.to_int(payload.get("confidence", 0)), 100))
        return AIValidationPrediction(
            decision=str(payload.get("decision", "UNKNOWN") or "UNKNOWN").upper(),
            confidence=confidence,
            reason=str(payload.get("reason", "") or ""),
            recommendation=str(payload.get("recommendation", "") or ""),
            readiness_prediction=str(payload.get("readiness_prediction", "") or ""),
            risk_prediction=str(payload.get("risk_prediction", "") or ""),
            prompt_tokens=MetricsCalculator.to_int(payload.get("prompt_tokens", 0)),
            completion_tokens=MetricsCalculator.to_int(payload.get("completion_tokens", 0)),
            total_tokens=MetricsCalculator.to_int(payload.get("total_tokens", 0)),
        )

    @staticmethod
    def _error_result(item: AIValidationInput, exc: Exception, elapsed_ms: int) -> AIValidationResult:
        """
        Executes the _error_result workflow for migration validation and readiness logic.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                item (object): Value supplied by the caller and used by the workflow.
                exc (object): Value supplied by the caller and used by the workflow.
                elapsed_ms (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that evaluates rules, remediation outcomes, risk, readiness, AI validation metrics, and XML comparison results. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return AIValidationResult(
            input=item,
            prediction=AIValidationPrediction(
                decision="ERROR",
                confidence=0,
                reason="AI validation failed.",
                error=str(exc),
            ),
            processing_time_ms=elapsed_ms,
        )
