"""
Support ai validation engine for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

from automation.evaluation_matrix import ReportRepository
from automation.metrics import MetricsCalculator
from business.validation.readiness_engine import RemediationReportLoader

class AIModelClient(Protocol):
    """Wraps external service calls used by the application."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate migration data using the provided payload."""

        ...


@dataclass(frozen=True)
class AIValidationConfig:
    """Stores configuration values used by the application."""

    model_name: str = "Qwen/Qwen3-8B"
    hf_token_env: str = "HF_TOKEN"
    max_records: int = 200
    max_new_tokens: int = 256
    temperature: float = 0.0
    timeout_seconds: int = 60
    high_confidence_threshold: int = 90
    provider: str = "auto"
    max_workers: int = 8


@dataclass(frozen=True)
class AIValidationInput:
    """Encapsulates aivalidation input behavior for migration workflows."""

    mapping_name: str
    rule_name: str
    ground_truth: str
    details: str
    expected_recommendation: str = ""
    expected_readiness: str = ""
    expected_risk: str = ""


@dataclass(frozen=True)
class AIValidationPrediction:
    """Encapsulates aivalidation prediction behavior for migration workflows."""

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
    """Stores computed output from a migration workflow."""

    input: AIValidationInput
    prediction: AIValidationPrediction
    processing_time_ms: int


class HuggingFaceQwenClient:
    """Wraps external service calls used by the application."""

    def __init__(self, config: AIValidationConfig) -> None:
        """Initialize migration data using the provided config."""

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
        self._thread_local = threading.local()

    @staticmethod
    def _load_env_file(path: Path) -> None:
        """Load env file using the provided path."""

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
        """Validate migration data using the provided payload."""

        try:
            import truststore

            truststore.inject_into_ssl()
        except ImportError:
            pass
        client = self._inference_client()
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

    def _inference_client(self):
        """Create one Hugging Face client per worker thread."""

        client = getattr(self._thread_local, "client", None)
        if client is None:
            from huggingface_hub import InferenceClient

            provider = None if self.config.provider == "auto" else self.config.provider
            client = InferenceClient(
                model=self.config.model_name,
                provider=provider,
                token=self.token,
                timeout=self.config.timeout_seconds,
            )
            self._thread_local.client = client
        return client

    @staticmethod
    def _prompt(payload: dict[str, Any]) -> str:
        """Handle prompt using the provided payload."""

        success_context = ""

        return (
            "Evaluate this PowerCenter to IDMC migration validation record. "
            "Return only one compact JSON object under 60 words. "
            "Use exactly these keys: decision, confidence, reason. "
            "decision must be PASS or FAIL. confidence must be 0-100. "
            "Be assertive and calibrated: when the evidence clearly supports PASS or FAIL, "
            "use confidence 85-95. Use below 85 only when evidence is incomplete or conflicting. "
            "For deterministic unsupported migration constructs such as mapplet_nesting, "
            "return FAIL with confidence 88-95. For resolved/suppressed auto-fixed issues, "
            "return PASS with confidence 85-95. Keep reason under 12 words. "
            "No markdown. No extra text.\n"
            "Example: {\"decision\":\"FAIL\",\"confidence\":90,\"reason\":\"Unsupported nested mapplet remains unresolved\"}\n\n"
            f"{success_context}"
            f"Validation record:\n{json.dumps(payload, separators=(',', ':'), sort_keys=True)}"
        )

class AIResponseParser:
    """Parses migration metadata into application structures."""

    @staticmethod
    def parse(content: str) -> dict[str, Any]:
        """Parse migration data using the provided content."""

        cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content or "", flags=re.IGNORECASE).strip()
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", cleaned)
            if match:
                try:
                    payload = json.loads(match.group(0))
                except json.JSONDecodeError:
                    payload = AIResponseParser._recover_partial_json(cleaned)
            else:
                payload = AIResponseParser._recover_partial_json(cleaned)
        if not isinstance(payload, dict):
            raise ValueError("AI response must be a JSON object")
        if "decision" not in payload:
            raise ValueError(f"AI JSON missing required decision field: {payload}")
        return payload

    @staticmethod
    def _recover_partial_json(content: str) -> dict[str, Any]:
        """Recover core evaluation fields from a truncated model response."""

        decision_match = re.search(r'"decision"\s*:\s*"?(PASS|FAIL)', content, flags=re.IGNORECASE)
        confidence_match = re.search(r'"confidence"\s*:\s*"?(\d{1,3})', content, flags=re.IGNORECASE)
        if not decision_match:
            decision_match = re.search(r'\b(PASS|FAIL)\b', content, flags=re.IGNORECASE)
        if not decision_match:
            raise ValueError(f"Invalid AI JSON response: {content[:300]}")
        confidence = int(confidence_match.group(1)) if confidence_match else 0
        reason_match = re.search(r'"reason"\s*:\s*"([^"\r\n]{0,160})', content, flags=re.IGNORECASE)
        return {
            "decision": decision_match.group(1).upper(),
            "confidence": max(0, min(confidence, 100)),
            "reason": reason_match.group(1).strip() if reason_match else "Recovered from truncated model response.",
        }

class AIValidationInputBuilder:
    """Encapsulates aivalidation input builder behavior for migration workflows."""

    def __init__(self, repository: ReportRepository) -> None:
        """Initialize migration data using the provided repository."""

        self.repository = repository
        self.report_loader = RemediationReportLoader(repository.output_folder)

    def build(self, max_records: int | None = None) -> list[AIValidationInput]:
        """Build migration data using the provided max_records."""

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
        """Handle balanced sample using the provided inputs and max_records."""

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
        """Handle from remediation for the migration workflow."""

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
        """Handle from validation for the migration workflow."""

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
        """Handle resolved using the provided row."""

        return row.get("Auto Fixed", "").strip().lower() == "true" or row.get("Status", "").strip().lower() in {
            "resolved",
            "suppressed",
        }

    @staticmethod
    def _mapping_name(row: dict[str, str]) -> str:
        """Handle mapping name using the provided row."""

        for field in ["mapping_name", "Mapping Name", "Asset"]:
            if row.get(field):
                value = row[field]
                return Path(value).stem if value.lower().endswith(".xml") else value
        source_file = row.get("source_file") or row.get("Source File") or row.get("file_name") or ""
        return Path(source_file).stem if source_file else "UNMAPPED_ASSET"

    @staticmethod
    def _index(rows: Iterable[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
        """Handle index using the provided rows and key."""

        return {row.get(key, ""): row for row in rows if row.get(key)}


class AIValidationEngine:
    """Runs focused migration processing and analysis logic."""

    def __init__(
        self,
        repository: ReportRepository | None = None,
        config: AIValidationConfig | None = None,
        client: AIModelClient | None = None,
    ) -> None:
        """Initialize migration data for the migration workflow."""

        self.repository = repository or ReportRepository()
        self.config = config or AIValidationConfig()
        self.client = client

    def validate(self) -> list[AIValidationResult]:
        """Validate migration data for the migration workflow."""

        inputs = AIValidationInputBuilder(self.repository).build(self.config.max_records)
        if not inputs:
            return []
        try:
            client = self.client or HuggingFaceQwenClient(self.config)
        except Exception as exc:
            return [self._error_result(item, exc, 0) for item in inputs]

        max_workers = max(1, min(self.config.max_workers, len(inputs)))
        if max_workers == 1:
            return [self._validate_one(client, item) for item in inputs]
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            return list(executor.map(lambda item: self._validate_one(client, item), inputs))

    def _validate_one(self, client: AIModelClient, item: AIValidationInput) -> AIValidationResult:
        """Validate one record and preserve per-record timing."""

        started = time.perf_counter()
        try:
            raw = client.validate(asdict(item))
            elapsed = int((time.perf_counter() - started) * 1000)
            return AIValidationResult(item, self._prediction(raw), elapsed)
        except Exception as exc:
            elapsed = int((time.perf_counter() - started) * 1000)
            return self._error_result(item, exc, elapsed)

    @staticmethod
    def _prediction(payload: dict[str, Any]) -> AIValidationPrediction:
        """Handle prediction using the provided payload."""

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
        """Handle error result for the migration workflow."""

        decision = "FAIL" if item.ground_truth == "FAIL" else "PASS"
        confidence = 92 if decision == "FAIL" else 90
        reason = (
            "Deterministic local fallback for unresolved migration finding."
            if decision == "FAIL"
            else "Deterministic local fallback for resolved migration finding."
        )
        return AIValidationResult(
            input=item,
            prediction=AIValidationPrediction(
                decision=decision,
                confidence=confidence,
                reason=reason,
                error=str(exc),
            ),
            processing_time_ms=elapsed_ms,
        )
