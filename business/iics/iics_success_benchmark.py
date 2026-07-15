"""Benchmark IICS import packages against known-good success references."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TaskflowFingerprint:
    """Structural fingerprint of a TASKFLOW.xml asset."""

    file_path: str
    taskflow_name: str
    service_titles: list[str]
    service_count: int
    mtt_guid_count: int
    process_object_refs: list[str]
    process_object_names: list[str]
    has_parallel: bool
    exclusive_count: int
    assignment_titles: list[str]
    has_flow: bool
    has_service: bool


@dataclass(frozen=True)
class PackageFingerprint:
    """High-level fingerprint of an IICS export zip."""

    package_path: str
    profile: str
    taskflows: list[TaskflowFingerprint]
    dtemplate_count: int
    mtt_count: int
    has_export_metadata: bool
    has_checksum: bool
    exported_object_types: list[str]


@dataclass
class SuccessCheck:
    """One pass/fail check against success criteria."""

    name: str
    passed: bool
    expected: Any
    actual: Any
    message: str = ""


@dataclass
class SuccessBenchmarkResult:
    """Outcome of comparing a package to a success profile."""

    package_path: str
    profile: str
    passed: bool
    checks: list[SuccessCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_path": self.package_path,
            "profile": self.profile,
            "passed": self.passed,
            "checks": [asdict(check) for check in self.checks],
        }


class IICSSuccessBenchmark:
    """Load gold-standard packages and validate generated exports against them."""

    DEFAULT_CRITERIA_PATH = Path("common/config/iics_success_criteria.json")

    def __init__(
        self,
        project_root: str | Path | None = None,
        criteria_path: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root or Path.cwd())
        self.criteria_path = self._resolve(criteria_path or self.DEFAULT_CRITERIA_PATH)
        self.criteria = self._load_criteria()

    def reference_package(self, profile: str) -> Path | None:
        profile_cfg = self.criteria.get("profiles", {}).get(profile) or {}
        package = profile_cfg.get("reference_package")
        if not package:
            return None
        resolved = self._resolve(package)
        return resolved if resolved.exists() else None

    def fingerprint_package(self, package_path: str | Path, profile: str | None = None) -> PackageFingerprint:
        package_path = Path(package_path)
        taskflows: list[TaskflowFingerprint] = []
        dtemplate_count = 0
        mtt_count = 0
        has_export_metadata = False
        has_checksum = False
        exported_object_types: list[str] = []

        with zipfile.ZipFile(package_path) as package:
            for name in package.namelist():
                if name.endswith(".DTEMPLATE.zip"):
                    dtemplate_count += 1
                elif name.endswith(".MTT.zip"):
                    mtt_count += 1
                elif name == "exportMetadata.v2.json":
                    has_export_metadata = True
                    metadata = json.loads(package.read(name).decode("utf-8"))
                    exported_object_types = sorted(
                        {
                            str(item.get("objectType"))
                            for item in metadata.get("exportedObjects", [])
                            if item.get("objectType")
                        }
                    )
                elif name.endswith("exportPackage.chksum"):
                    has_checksum = True
                elif name.endswith(".TASKFLOW.xml"):
                    text = package.read(name).decode("utf-8")
                    taskflows.append(self._fingerprint_taskflow(name, text))

        resolved_profile = profile or self._infer_profile(taskflows, mtt_count)
        return PackageFingerprint(
            package_path=str(package_path),
            profile=resolved_profile,
            taskflows=taskflows,
            dtemplate_count=dtemplate_count,
            mtt_count=mtt_count,
            has_export_metadata=has_export_metadata,
            has_checksum=has_checksum,
            exported_object_types=exported_object_types,
        )

    def validate_package(
        self,
        package_path: str | Path,
        profile: str | None = None,
    ) -> SuccessBenchmarkResult:
        fingerprint = self.fingerprint_package(package_path, profile=profile)
        profile_name = profile or fingerprint.profile
        profile_cfg = self.criteria.get("profiles", {}).get(profile_name)
        if not profile_cfg:
            return SuccessBenchmarkResult(
                package_path=str(package_path),
                profile=profile_name,
                passed=False,
                checks=[
                    SuccessCheck(
                        name="profile_known",
                        passed=False,
                        expected=list(self.criteria.get("profiles", {})),
                        actual=profile_name,
                        message=f"Unknown success profile: {profile_name}",
                    )
                ],
            )

        checks = self._build_checks(fingerprint, profile_cfg)
        return SuccessBenchmarkResult(
            package_path=str(package_path),
            profile=profile_name,
            passed=all(check.passed for check in checks),
            checks=checks,
        )

    def training_context(self, profile: str | None = None) -> dict[str, Any]:
        """Return structured success criteria for AI prompts and documentation."""

        profiles = self.criteria.get("profiles", {})
        if profile:
            selected = {profile: profiles.get(profile, {})}
        else:
            selected = profiles
        return {
            "version": self.criteria.get("version"),
            "description": self.criteria.get("description"),
            "profiles": selected,
        }

    def _resolve(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path

    def _load_criteria(self) -> dict[str, Any]:
        with self.criteria_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _fingerprint_taskflow(file_path: str, text: str) -> TaskflowFingerprint:
        name_match = re.search(r"<types1:Name>([^<]+)</types1:Name>", text)
        service_titles = re.findall(r"<service\b[\s\S]*?<title>(.*?)</title>", text)
        assignment_titles = [
            title
            for title in re.findall(r"<title>([^<]+)</title>", text)
            if title.startswith("Assignment_")
        ]
        po_refs = re.findall(r'referenceTo">\$po:([^<]+)', text)
        po_names = re.findall(r"<processObject\b[^>]*\bname=\"([^\"]+)\"", text)
        return TaskflowFingerprint(
            file_path=file_path,
            taskflow_name=name_match.group(1) if name_match else "",
            service_titles=service_titles,
            service_count=len(service_titles),
            mtt_guid_count=len(re.findall(r'name="GUID"[^>]*>([^<]+)', text)),
            process_object_refs=po_refs,
            process_object_names=po_names,
            has_parallel='type="parallel"' in text,
            exclusive_count=text.count('type="exclusive"'),
            assignment_titles=assignment_titles,
            has_flow="<flow" in text,
            has_service="<service" in text,
        )

    @staticmethod
    def _infer_profile(taskflows: list[TaskflowFingerprint], mtt_count: int) -> str:
        if not taskflows:
            return "single_session" if mtt_count <= 1 else "multi_session"
        primary = taskflows[0]
        if primary.has_parallel or mtt_count > 1 or primary.mtt_guid_count > 1:
            return "multi_session"
        return "single_session"

    def _build_checks(self, fingerprint: PackageFingerprint, profile_cfg: dict[str, Any]) -> list[SuccessCheck]:
        checks: list[SuccessCheck] = []
        taskflow_rules = profile_cfg.get("taskflow", {})
        package_rules = profile_cfg.get("package", {})
        primary = fingerprint.taskflows[0] if fingerprint.taskflows else None

        checks.append(
            self._check(
                "has_export_metadata",
                fingerprint.has_export_metadata,
                package_rules.get("requires_export_metadata", True),
            )
        )
        checks.append(
            self._check(
                "has_checksum",
                fingerprint.has_checksum,
                package_rules.get("requires_checksum", True),
            )
        )
        checks.append(
            self._check(
                "dtemplate_count_min",
                fingerprint.dtemplate_count,
                package_rules.get("min_dtemplate_count", 1),
                comparator="gte",
            )
        )
        checks.append(
            self._check(
                "mtt_count_min",
                fingerprint.mtt_count,
                package_rules.get("min_mtt_count", 1),
                comparator="gte",
            )
        )

        required_types = package_rules.get("required_exported_types", [])
        if required_types:
            missing = [item for item in required_types if item not in fingerprint.exported_object_types]
            checks.append(
                SuccessCheck(
                    name="required_exported_types",
                    passed=not missing,
                    expected=required_types,
                    actual=fingerprint.exported_object_types,
                    message=f"Missing exported object types: {missing}" if missing else "",
                )
            )

        if primary:
            checks.append(self._check("taskflow_has_flow", primary.has_flow, taskflow_rules.get("requires_flow", True)))
            checks.append(self._check("taskflow_has_service", primary.has_service, taskflow_rules.get("requires_service", True)))
            checks.append(
                self._check(
                    "taskflow_service_count_min",
                    primary.service_count,
                    taskflow_rules.get("min_service_count", 1),
                    comparator="gte",
                )
            )
            checks.append(
                self._check(
                    "taskflow_mtt_guid_count_min",
                    primary.mtt_guid_count,
                    taskflow_rules.get("min_mtt_guid_count", 1),
                    comparator="gte",
                )
            )
            checks.append(
                self._check(
                    "taskflow_has_parallel",
                    primary.has_parallel,
                    taskflow_rules.get("requires_parallel", False),
                )
            )
            checks.append(
                self._check(
                    "taskflow_exclusive_count_min",
                    primary.exclusive_count,
                    taskflow_rules.get("min_exclusive_count", 0),
                    comparator="gte",
                )
            )

            required_assignments = taskflow_rules.get("required_assignment_titles", [])
            if required_assignments:
                missing = [item for item in required_assignments if item not in primary.assignment_titles]
                checks.append(
                    SuccessCheck(
                        name="required_assignment_titles",
                        passed=not missing,
                        expected=required_assignments,
                        actual=primary.assignment_titles,
                        message=f"Missing assignment steps: {missing}" if missing else "",
                    )
                )

            if taskflow_rules.get("requires_process_object_refs", True):
                checks.append(
                    self._check(
                        "taskflow_process_object_refs",
                        len(primary.process_object_refs) > 0,
                        True,
                        message="Taskflow must declare $po: Process Object references",
                    )
                )

        return checks

    @staticmethod
    def _check(
        name: str,
        actual: Any,
        expected: Any,
        *,
        comparator: str = "eq",
        message: str = "",
    ) -> SuccessCheck:
        if comparator == "gte":
            passed = actual >= expected
        else:
            passed = actual == expected
        return SuccessCheck(
            name=name,
            passed=passed,
            expected=expected,
            actual=actual,
            message=message or ("" if passed else f"{name} expected {expected}, got {actual}"),
        )


def validate_iics_success_package(
    package_path: str | Path,
    profile: str | None = None,
    *,
    project_root: str | Path | None = None,
) -> SuccessBenchmarkResult:
    """Validate one package against configured IICS success criteria."""

    return IICSSuccessBenchmark(project_root=project_root).validate_package(package_path, profile=profile)
