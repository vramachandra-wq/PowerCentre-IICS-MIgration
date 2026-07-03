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
    mapping_name: str
    rule_name: str
    ground_truth: str
    details: str
    expected_recommendation: str = ""
    expected_readiness: str = ""
    expected_risk: str = ""


@dataclass(frozen=True)
class AIValidationPrediction:
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
    input: AIValidationInput
    prediction: AIValidationPrediction
    processing_time_ms: int


class HuggingFaceQwenClient:
    """Qwen client backed by Hugging Face chat completion."""

    def __init__(self, config: AIValidationConfig) -> None:
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
        self.repository = repository
        self.report_loader = RemediationReportLoader(repository.output_folder)

    def build(self, max_records: int | None = None) -> list[AIValidationInput]:
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
        return row.get("Auto Fixed", "").strip().lower() == "true" or row.get("Status", "").strip().lower() in {
            "resolved",
            "suppressed",
        }

    @staticmethod
    def _mapping_name(row: dict[str, str]) -> str:
        for field in ["mapping_name", "Mapping Name", "Asset"]:
            if row.get(field):
                value = row[field]
                return Path(value).stem if value.lower().endswith(".xml") else value
        source_file = row.get("source_file") or row.get("Source File") or row.get("file_name") or ""
        return Path(source_file).stem if source_file else "UNMAPPED_ASSET"

    @staticmethod
    def _index(rows: Iterable[dict[str, str]], key: str) -> dict[str, dict[str, str]]:
        return {row.get(key, ""): row for row in rows if row.get(key)}


class AIValidationEngine:
    """Runs the configured AI model against rule-engine ground-truth records."""

    def __init__(
        self,
        repository: ReportRepository | None = None,
        config: AIValidationConfig | None = None,
        client: AIModelClient | None = None,
    ) -> None:
        self.repository = repository or ReportRepository()
        self.config = config or AIValidationConfig()
        self.client = client

    def validate(self) -> list[AIValidationResult]:
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
