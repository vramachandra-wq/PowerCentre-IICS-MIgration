"""Registry for IDMC DTEMPLATE transformation prototypes.

Native IDMC mappings cannot be assembled safely by guessing transformation
classes. The registry records which real exported prototypes are available and
whether the full PowerCenter canvas compiler can be enabled.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_NATIVE_TYPES = (
    "source",
    "target",
    "source_qualifier",
    "expression",
    "lookup",
    "filter",
    "update_strategy",
    "mapplet",
)


@dataclass(frozen=True)
class PrototypeStatus:
    transformation_type: str
    available: bool
    source_path: str = ""


@dataclass(frozen=True)
class RegistryStatus:
    complete: bool
    prototypes: list[PrototypeStatus]

    @property
    def missing_types(self) -> list[str]:
        return [item.transformation_type for item in self.prototypes if not item.available]

    def to_dict(self) -> dict[str, object]:
        return {
            "complete": self.complete,
            "missingTypes": self.missing_types,
            "prototypes": [asdict(item) for item in self.prototypes],
        }


class DtemplateClassRegistry:
    """Discover real IDMC DTEMPLATE prototype exports by transformation type."""

    def __init__(self, root: str | Path = "reference_packages/iics_native_classes") -> None:
        self.root = Path(root)

    def status(self, required_types: Iterable[str] = REQUIRED_NATIVE_TYPES) -> RegistryStatus:
        statuses = [self._status_for_type(item) for item in required_types]
        return RegistryStatus(complete=all(item.available for item in statuses), prototypes=statuses)

    def write_status_report(self, path: str | Path) -> RegistryStatus:
        status = self.status()
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(status.to_dict(), indent=2), encoding="utf-8")
        return status

    def _status_for_type(self, transformation_type: str) -> PrototypeStatus:
        type_dir = self.root / transformation_type
        if not type_dir.exists():
            return PrototypeStatus(transformation_type, False)
        for candidate in sorted(type_dir.rglob("*.DTEMPLATE.zip")):
            if self._looks_like_dtemplate(candidate):
                return PrototypeStatus(transformation_type, True, str(candidate))
        for candidate in sorted(type_dir.rglob("*.zip")):
            nested = self._first_nested_dtemplate(candidate)
            if nested:
                return PrototypeStatus(transformation_type, True, f"{candidate}!{nested}")
        return PrototypeStatus(transformation_type, False)

    @staticmethod
    def _looks_like_dtemplate(path: Path) -> bool:
        try:
            with zipfile.ZipFile(path) as package:
                names = set(package.namelist())
                if not {"mappingTemplate.json", "fileRecord.json"}.issubset(names):
                    return False
                return any(name.startswith("bin/") and name.endswith(".bin") for name in names)
        except (OSError, zipfile.BadZipFile):
            return False

    @classmethod
    def _first_nested_dtemplate(cls, path: Path) -> str:
        try:
            with zipfile.ZipFile(path) as package:
                for member in package.namelist():
                    if not member.endswith(".DTEMPLATE.zip"):
                        continue
                    try:
                        data = package.read(member)
                    except KeyError:
                        continue
                    nested_path = Path(member)
                    # Validate via an in-memory temp-like read without writing.
                    try:
                        import io

                        with zipfile.ZipFile(io.BytesIO(data)) as nested_package:
                            names = set(nested_package.namelist())
                            if {"mappingTemplate.json", "fileRecord.json"}.issubset(names):
                                return str(nested_path)
                    except (OSError, zipfile.BadZipFile):
                        continue
        except (OSError, zipfile.BadZipFile):
            return ""
        return ""
