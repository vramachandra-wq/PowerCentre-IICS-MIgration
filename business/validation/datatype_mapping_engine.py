"""
Support datatype mapping engine for migration business logic.
Parses, validates, assesses, and remediates PowerCenter metadata.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DatatypeSpec:
    """Encapsulates datatype spec behavior for migration workflows."""

    raw: str
    base_type: str
    canonical_type: str
    idmc_type: str
    family: str
    precision: int | None = None
    scale: int | None = None
    length: int | None = None
    unicode: bool = False
    valid: bool = True
    message: str = ""
    recommendation: str = ""


class DatatypeMappingEngine:
    """Runs focused migration processing and analysis logic."""

    TYPE_PATTERN = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 ]*)\s*(?:\(([^)]*)\))?\s*$")

    def __init__(self, rules_path: str | Path | None = None) -> None:
        """Initialize migration data using the provided rules_path."""

        self.project_root = Path.cwd()
        self.rules_path = self._resolve_path(
            rules_path or Path("common/config/datatype_mapping_rules.json")
        )
        with self.rules_path.open("r", encoding="utf-8") as rules_file:
            self.rules: dict[str, Any] = json.load(rules_file)

        self.datatypes: dict[str, dict[str, Any]] = {
            key.upper(): value for key, value in self.rules["datatypes"].items()
        }
        self.aliases: dict[str, str] = {
            key.upper(): value.upper() for key, value in self.rules.get("aliases", {}).items()
        }

    def map_datatype(
        self,
        datatype: str,
        precision: int | str | None = None,
        scale: int | str | None = None,
        length: int | str | None = None,
    ) -> DatatypeSpec:
        """Map datatype for the migration workflow."""

        parsed_type, parsed_precision, parsed_scale = self._parse_datatype(datatype)
        base_type = self._canonical_base_type(parsed_type, parsed_precision, parsed_scale)
        rule = self.datatypes.get(base_type)
        if rule is None:
            return DatatypeSpec(
                raw=str(datatype or ""),
                base_type=base_type,
                canonical_type="UNKNOWN",
                idmc_type="UNKNOWN",
                family="UNKNOWN",
                valid=False,
                message=f"Unsupported datatype: {datatype}",
                recommendation="Add datatype mapping rule before migration.",
            )

        final_precision = self._to_int(precision, parsed_precision)
        final_scale = self._to_int(scale, parsed_scale)
        final_length = self._to_int(length, None)

        if rule.get("supports_length") and final_length is None:
            final_length = final_precision or rule.get("default_length")
            final_precision = None
        if rule.get("supports_precision") and final_precision is None:
            final_precision = rule.get("default_precision")
        if rule.get("supports_scale") and final_scale is None:
            final_scale = rule.get("default_scale")
        if not rule.get("supports_scale", False):
            final_scale = 0 if final_scale is None else final_scale

        return DatatypeSpec(
            raw=str(datatype or ""),
            base_type=base_type,
            canonical_type=str(rule["canonical"]),
            idmc_type=str(rule["idmc_type"]),
            family=str(rule["family"]),
            precision=final_precision,
            scale=final_scale,
            length=final_length,
            unicode=bool(rule.get("unicode", False)),
            valid=True,
            recommendation=str(rule.get("recommendation", "")),
        )

    def validate_datatype(
        self,
        datatype: str,
        precision: int | str | None = None,
        scale: int | str | None = None,
        length: int | str | None = None,
    ) -> dict[str, Any]:
        """Validate datatype for the migration workflow."""

        mapped = self.map_datatype(datatype, precision=precision, scale=scale, length=length)
        issues: list[str] = []

        if not mapped.valid:
            issues.append(mapped.message)
        if mapped.family == "NUMERIC" and mapped.scale and mapped.canonical_type in {"INTEGER", "BIGINT", "SMALLINT"}:
            issues.append("Integer datatype cannot safely retain non-zero scale.")
        if mapped.precision is not None and mapped.precision > self.rules["defaults"]["number_precision"]:
            issues.append("Precision exceeds default IDMC decimal precision.")
        if mapped.length is not None and mapped.length <= 0:
            issues.append("String length must be greater than zero.")

        return {
            "datatype": datatype,
            "valid": mapped.valid and not issues,
            "mapped_type": mapped.idmc_type,
            "canonical_type": mapped.canonical_type,
            "family": mapped.family,
            "issues": issues,
            "recommendation": self.suggest_datatype_fix(datatype, precision, scale, length),
        }

    def suggest_datatype_fix(
        self,
        datatype: str,
        precision: int | str | None = None,
        scale: int | str | None = None,
        length: int | str | None = None,
    ) -> str:
        """Handle suggest datatype fix for the migration workflow."""

        mapped = self.map_datatype(datatype, precision=precision, scale=scale, length=length)
        if not mapped.valid:
            return mapped.recommendation
        if mapped.family == "NUMERIC" and mapped.scale and mapped.scale > 0:
            return "Retain original precision and scale."
        if mapped.family == "STRING" and mapped.unicode:
            return "Use Unicode-capable IDMC String and retain length."
        return mapped.recommendation

    def issue_rule(self, issue_code: str) -> dict[str, str]:
        """Handle issue rule using the provided issue_code."""

        return self.rules.get("issue_rules", {}).get(
            issue_code,
            {"severity": "MEDIUM", "recommendation": "Review datatype compatibility before migration."},
        )

    def are_compatible(self, left: DatatypeSpec, right: DatatypeSpec) -> bool:
        """Handle are compatible using the provided left and right."""

        if not left.valid or not right.valid:
            return False
        if left.family == right.family:
            return True
        family_rule = self.rules.get("families", {}).get(left.family, {})
        return right.family in family_rule.get("compatible_with", [])

    def _parse_datatype(self, datatype: str) -> tuple[str, int | None, int | None]:
        """Parse datatype using the provided datatype."""

        value = str(datatype or "").strip().upper()
        match = self.TYPE_PATTERN.match(value)
        if not match:
            return value, None, None

        base_type = re.sub(r"\s+", " ", match.group(1).strip().upper())
        precision = None
        scale = None
        params = match.group(2)
        if params:
            parts = [part.strip() for part in params.split(",")]
            if parts:
                precision = self._to_int(parts[0], None)
            if len(parts) > 1:
                scale = self._to_int(parts[1], None)
        return base_type, precision, scale

    def _canonical_base_type(
        self, parsed_type: str, parsed_precision: int | None, parsed_scale: int | None
    ) -> str:
        """Handle canonical base type for the migration workflow."""

        if parsed_type in self.datatypes:
            return parsed_type
        signature = f"{parsed_type}()"
        if signature in self.aliases:
            return self.aliases[signature]
        if parsed_precision is not None and parsed_scale is not None:
            signature = f"{parsed_type}(P,S)"
            if signature in self.aliases:
                return self.aliases[signature]
        return self.aliases.get(parsed_type, parsed_type)

    @staticmethod
    def _to_int(*values: object) -> int | None:
        """Handle to int using the provided values."""

        for value in values:
            if value in {None, ""}:
                continue
            try:
                return int(str(value).strip())
            except ValueError:
                continue
        return None

    def _resolve_path(self, path: str | Path) -> Path:
        """Handle resolve path using the provided path."""

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate


_DEFAULT_ENGINE: DatatypeMappingEngine | None = None


def _engine() -> DatatypeMappingEngine:
    """Handle engine for the migration workflow."""

    global _DEFAULT_ENGINE
    if _DEFAULT_ENGINE is None:
        _DEFAULT_ENGINE = DatatypeMappingEngine()
    return _DEFAULT_ENGINE


def map_datatype(
    datatype: str,
    precision: int | str | None = None,
    scale: int | str | None = None,
    length: int | str | None = None,
) -> DatatypeSpec:
    """Map datatype for the migration workflow."""

    return _engine().map_datatype(datatype, precision=precision, scale=scale, length=length)


def validate_datatype(
    datatype: str,
    precision: int | str | None = None,
    scale: int | str | None = None,
    length: int | str | None = None,
) -> dict[str, Any]:
    """Validate datatype for the migration workflow."""

    return _engine().validate_datatype(datatype, precision=precision, scale=scale, length=length)


def suggest_datatype_fix(
    datatype: str,
    precision: int | str | None = None,
    scale: int | str | None = None,
    length: int | str | None = None,
) -> str:
    """Handle suggest datatype fix for the migration workflow."""

    return _engine().suggest_datatype_fix(datatype, precision=precision, scale=scale, length=length)
