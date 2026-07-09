"""
IICS Package Processor — ingests a client-provided IICS export zip, validates
every asset, produces a clean import-ready zip and audit reports.

Supported asset types
---------------------
  MTT        Mapping Task Template   (.MTT.zip   → mtTask.json + metadata.meta)
  DTEMPLATE  Design Template         (.DTEMPLATE.zip → mappingTemplate.json + fileRecord.json + bin/)
  TASKFLOW   Task Flow               (.TASKFLOW.xml  wrapped in aetgt:getResponse)
  Connection Oracle / generic conn   (.Connection.zip)
  AgentGroup Secure Agent Group      (.AgentGroup.zip)
  Project    IICS Project            (.Project.json)
  Folder     IICS Folder             (.Folder.json)

Output (written to <output_dir>/iics/)
---------------------------------------
  iics_import_package.zip       — validated, ready-to-import zip
  asset_inventory.csv           — complete asset listing
  validation_report.csv         — per-asset validation results
  checksum_report.csv           — checksum verification results
  summary.json                  — overall statistics
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from business.iics.checksum_utils import (
    build_checksum_file,
    parse_checksum_file,
    sha256_hex,
    validate_zip_checksums,
)


# ── domain types ─────────────────────────────────────────────────────────────

@dataclass
class IICSAsset:
    object_guid: str
    object_name: str
    object_type: str
    path: str
    file_path: str        # relative path inside the package zip
    valid: bool = True
    issues: list[str] = field(default_factory=list)
    checksum_ok: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PackageValidationResult:
    total_assets: int = 0
    valid_assets: int = 0
    invalid_assets: int = 0
    checksum_failures: int = 0
    missing_files: int = 0
    asset_types: dict[str, int] = field(default_factory=dict)
    assets: list[IICSAsset] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


# ── processor ────────────────────────────────────────────────────────────────

class IICSPackageProcessor:
    """Validate and repackage a client-supplied IICS export zip."""

    REQUIRED_ROOT_FILES = {"exportMetadata.v2.json", "exportPackage.chksum"}
    ASSET_FILE_EXTENSIONS = {
        ".MTT.zip", ".DTEMPLATE.zip", ".TASKFLOW.xml",
        ".Connection.zip", ".AgentGroup.zip",
        ".Project.json", ".Folder.json",
    }
    ASSET_TYPE_LABELS = {
        "MTT": "Mapping Task Template",
        "DTEMPLATE": "Design Template (Mapping)",
        "TASKFLOW": "Task Flow / Workflow",
        "Connection": "Database Connection",
        "AgentGroup": "Secure Agent Group",
        "Project": "IICS Project",
        "Folder": "IICS Folder",
    }

    def __init__(
        self,
        input_zip: str | Path,
        output_dir: str | Path = "output/iics",
        logger: logging.Logger | None = None,
    ) -> None:
        self.input_zip = Path(input_zip)
        self.output_dir = Path(output_dir)
        self.logger = logger or logging.getLogger(__name__)
        self._work_dir: Path | None = None

    # ── public entry point ───────────────────────────────────────────────────

    def process(self) -> dict[str, Any]:
        """Full pipeline: extract → validate → repackage → report."""
        self.logger.info("IICS Package Processor starting. input=%s", self.input_zip)

        if not self.input_zip.exists():
            raise FileNotFoundError(f"Input zip not found: {self.input_zip}")

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._work_dir = self.output_dir / "_work"
        if self._work_dir.exists():
            shutil.rmtree(self._work_dir)
        self._work_dir.mkdir(parents=True)

        try:
            self._extract_input()
            manifest = self._load_manifest()
            checksums = self._load_checksums()
            assets = self._discover_assets(manifest)
            self._validate_assets(assets, checksums)
            result = self._build_result(assets)
            self._write_reports(result)
            output_zip = self._repackage(result)
            summary = self._build_summary(result, output_zip)
            self._write_summary(summary)
            self.logger.info(
                "IICS package processing complete. valid=%d invalid=%d output=%s",
                result.valid_assets, result.invalid_assets, output_zip,
            )
            return summary
        finally:
            if self._work_dir and self._work_dir.exists():
                shutil.rmtree(self._work_dir, ignore_errors=True)

    # ── pipeline steps ───────────────────────────────────────────────────────

    def _extract_input(self) -> None:
        self.logger.info("Extracting input zip ...")
        with zipfile.ZipFile(self.input_zip, "r") as zf:
            zf.extractall(self._work_dir)
        self.logger.info("Extraction complete. files=%d", sum(1 for _ in self._work_dir.rglob("*") if _.is_file()))

    def _load_manifest(self) -> dict[str, Any]:
        manifest_path = self._work_dir / "exportMetadata.v2.json"
        if not manifest_path.exists():
            raise FileNotFoundError("exportMetadata.v2.json not found in package — invalid IICS export.")
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.logger.info(
            "Manifest loaded. job=%s org=%s objects=%d",
            manifest.get("name"), manifest.get("sourceOrgName"),
            len(manifest.get("exportedObjects", [])),
        )
        return manifest

    def _load_checksums(self) -> dict[str, str]:
        chksum_path = self._work_dir / "exportPackage.chksum"
        if not chksum_path.exists():
            self.logger.warning("exportPackage.chksum not found — skipping checksum validation.")
            return {}
        checksums = parse_checksum_file(chksum_path.read_text(encoding="utf-8"))
        self.logger.info("Checksums loaded. entries=%d", len(checksums))
        return checksums

    def _discover_assets(self, manifest: dict[str, Any]) -> list[IICSAsset]:
        """Build asset list from manifest, then locate each file on disk."""
        assets: list[IICSAsset] = []
        exported = manifest.get("exportedObjects", [])

        for obj in exported:
            guid = obj.get("objectGuid", "")
            name = obj.get("objectName", "")
            obj_type = obj.get("objectType", "")
            path = obj.get("path", "")
            meta = obj.get("metadata", {})

            file_path = self._locate_asset_file(name, obj_type, path)
            asset = IICSAsset(
                object_guid=guid,
                object_name=name,
                object_type=obj_type,
                path=path,
                file_path=file_path or "",
                metadata=meta,
            )
            if not file_path:
                asset.valid = False
                asset.issues.append(f"Asset file not found on disk for {obj_type} '{name}'")
            assets.append(asset)

        self.logger.info("Assets discovered from manifest. count=%d", len(assets))
        return assets

    def _locate_asset_file(self, name: str, obj_type: str, path: str) -> str | None:
        """Return the relative file path inside the work dir, or None."""
        relative_dir = path.lstrip("/").replace("/", "/")
        candidates = []

        ext_map = {
            "MTT": f"{name}.MTT.zip",
            "DTEMPLATE": f"{name}.DTEMPLATE.zip",
            "TASKFLOW": f"{name}.TASKFLOW.xml",
            "Connection": f"{name}.Connection.zip",
            "AgentGroup": f"{name}.AgentGroup.zip",
            "Project": f"{name}.Project.json",
            "Folder": f"{name}.Folder.json",
        }

        expected_filename = ext_map.get(obj_type)
        if not expected_filename:
            return None

        for candidate in self._work_dir.rglob(expected_filename):
            return str(candidate.relative_to(self._work_dir)).replace("\\", "/")

        return None

    def _validate_assets(self, assets: list[IICSAsset], checksums: dict[str, str]) -> None:
        """Validate each asset: file presence, internal structure, checksum."""
        for asset in assets:
            if not asset.file_path:
                continue

            abs_path = self._work_dir / asset.file_path

            # checksum verification (Java Properties format: path=HASH)
            if checksums and asset.file_path in checksums:
                expected = checksums[asset.file_path]
                actual = sha256_hex(abs_path.read_bytes())
                if actual.upper() != expected.upper():
                    asset.checksum_ok = False
                    asset.valid = False
                    asset.issues.append(f"Checksum mismatch: expected={expected} actual={actual}")

            # type-specific structural validation
            if asset.object_type == "MTT":
                self._validate_mtt(asset, abs_path)
            elif asset.object_type == "DTEMPLATE":
                self._validate_dtemplate(asset, abs_path)
            elif asset.object_type == "TASKFLOW":
                self._validate_taskflow(asset, abs_path)
            elif asset.object_type in ("Connection", "AgentGroup"):
                self._validate_generic_zip(asset, abs_path)
            elif asset.object_type in ("Project", "Folder"):
                self._validate_json_asset(asset, abs_path)

    def _validate_mtt(self, asset: IICSAsset, path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if "mtTask.json" not in names:
                    asset.valid = False
                    asset.issues.append("MTT zip missing required mtTask.json")
                else:
                    task_data = json.loads(zf.read("mtTask.json"))
                    if not isinstance(task_data, list) or not task_data:
                        asset.valid = False
                        asset.issues.append("mtTask.json is empty or not a list")
                    else:
                        task = task_data[0]
                        asset.metadata["task_name"] = task.get("name", "")
                        asset.metadata["mapping_id"] = task.get("mappingId", "")
                        asset.metadata["runtime_env"] = task.get("runtimeEnvironmentId", "")
                        asset.metadata["valid_flag"] = task.get("valid", None)

                if "metadata.meta" not in names:
                    asset.issues.append("MTT zip missing metadata.meta (non-critical)")
        except zipfile.BadZipFile as e:
            asset.valid = False
            asset.issues.append(f"MTT zip is corrupt: {e}")

    def _validate_dtemplate(self, asset: IICSAsset, path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                required = {"mappingTemplate.json", "fileRecord.json"}
                missing = required - set(names)
                if missing:
                    asset.valid = False
                    asset.issues.append(f"DTEMPLATE missing: {', '.join(missing)}")
                else:
                    tpl = json.loads(zf.read("mappingTemplate.json"))
                    if isinstance(tpl, list) and tpl:
                        t = tpl[0]
                        asset.metadata["template_name"] = t.get("name", "")
                        asset.metadata["tasks"] = t.get("tasks", 0)
                        asset.metadata["has_parameters"] = t.get("hasParameters", False)
                        asset.metadata["valid_flag"] = t.get("valid", None)

                bin_files = [n for n in names if n.startswith("bin/") and n.endswith(".bin")]
                if not bin_files:
                    asset.valid = False
                    asset.issues.append("DTEMPLATE missing bin/*.bin mapping content")
                else:
                    asset.metadata["bin_files"] = bin_files
        except zipfile.BadZipFile as e:
            asset.valid = False
            asset.issues.append(f"DTEMPLATE zip is corrupt: {e}")

    def _validate_taskflow(self, asset: IICSAsset, path: Path) -> None:
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            ns_map = {
                "aetgt": "http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd",
                "types1": "http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd",
                "tf": "http://schemas.active-endpoints.com/appmodules/screenflow/2010/10/avosScreenflow.xsd",
            }
            item = root.find(".//{http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd}Item")
            if item is None:
                asset.issues.append("TASKFLOW XML: no Item element found (may still be valid)")
            else:
                name_el = item.find("{http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd}Name")
                guid_el = item.find("{http://schemas.active-endpoints.com/appmodules/repository/2010/10/avrepository.xsd}GUID")
                if name_el is not None:
                    asset.metadata["taskflow_name"] = name_el.text
                if guid_el is not None:
                    asset.metadata["taskflow_guid"] = guid_el.text
        except ET.ParseError as e:
            asset.valid = False
            asset.issues.append(f"TASKFLOW XML parse error: {e}")

    def _validate_generic_zip(self, asset: IICSAsset, path: Path) -> None:
        try:
            with zipfile.ZipFile(path) as zf:
                if not zf.namelist():
                    asset.valid = False
                    asset.issues.append(f"{asset.object_type} zip is empty")
        except zipfile.BadZipFile as e:
            asset.valid = False
            asset.issues.append(f"{asset.object_type} zip is corrupt: {e}")

    def _validate_json_asset(self, asset: IICSAsset, path: Path) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            props = {}
            if isinstance(data, dict):
                for p in data.get("properties", []):
                    if isinstance(p, dict) and p.get("name"):
                        props[p["name"]] = p.get("value")
            asset.metadata["parsed_properties"] = len(props)
        except (json.JSONDecodeError, OSError) as e:
            asset.valid = False
            asset.issues.append(f"{asset.object_type} JSON parse error: {e}")

    # ── result assembly ──────────────────────────────────────────────────────

    def _build_result(self, assets: list[IICSAsset]) -> PackageValidationResult:
        result = PackageValidationResult(assets=assets)
        result.total_assets = len(assets)
        for a in assets:
            result.asset_types[a.object_type] = result.asset_types.get(a.object_type, 0) + 1
            if a.valid:
                result.valid_assets += 1
            else:
                result.invalid_assets += 1
            if not a.checksum_ok:
                result.checksum_failures += 1
            if not a.file_path:
                result.missing_files += 1
        return result

    # ── repackaging ──────────────────────────────────────────────────────────

    def _repackage(self, result: PackageValidationResult) -> Path:
        """Build the output IICS import zip from validated content."""
        job_name = f"job-{int(time.time() * 1000)}"
        output_zip = self.output_dir / "iics_import_package.zip"

        valid_asset_files = {a.file_path for a in result.assets if a.valid and a.file_path}

        checksums_for_output: dict[str, str] = {}

        with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for rel_path in sorted(valid_asset_files):
                abs_path = self._work_dir / rel_path
                if abs_path.exists():
                    content = abs_path.read_bytes()
                    zout.writestr(rel_path, content)
                    checksums_for_output[rel_path] = sha256_hex(content)

            valid_guids = {a.object_guid for a in result.assets if a.valid}
            orig_manifest_path = self._work_dir / "exportMetadata.v2.json"
            if orig_manifest_path.exists():
                with open(orig_manifest_path, encoding="utf-8") as fh:
                    orig = json.load(fh)
                orig["name"] = job_name
                orig["exportedObjects"] = [
                    o for o in orig.get("exportedObjects", [])
                    if o.get("objectGuid") in valid_guids
                ]
                manifest_bytes = json.dumps(orig, indent=2).encode("utf-8")
                zout.writestr("exportMetadata.v2.json", manifest_bytes)
                checksums_for_output["exportMetadata.v2.json"] = sha256_hex(manifest_bytes)

            csv_rows = [["objectPath", "objectName", "objectType", "id"]]
            for a in result.assets:
                if a.valid:
                    csv_rows.append([a.path, a.object_name, a.object_type, a.object_guid])
            csv_content = "\n".join(",".join(r) for r in csv_rows).encode("utf-8")
            csv_name = f"ContentsofExportPackage_{job_name}.csv"
            zout.writestr(csv_name, csv_content)
            # CSV is not included in IICS checksum file

            zout.writestr("exportPackage.chksum", build_checksum_file(checksums_for_output))

        ok, chk_errors = validate_zip_checksums(output_zip)
        if not ok:
            self.logger.warning("Post-pack checksum validation warnings: %s", chk_errors[:5])

        self.logger.info("Output zip created. path=%s size=%d bytes", output_zip, output_zip.stat().st_size)
        return output_zip

    # ── reports ──────────────────────────────────────────────────────────────

    def _write_reports(self, result: PackageValidationResult) -> None:
        self._write_asset_inventory(result)
        self._write_validation_report(result)
        self._write_checksum_report(result)

    def _write_asset_inventory(self, result: PackageValidationResult) -> None:
        path = self.output_dir / "asset_inventory.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["object_name", "object_type", "object_type_label",
                              "path", "object_guid", "file_path", "valid",
                              "checksum_ok", "issue_count"])
            for a in result.assets:
                writer.writerow([
                    a.object_name,
                    a.object_type,
                    self.ASSET_TYPE_LABELS.get(a.object_type, a.object_type),
                    a.path,
                    a.object_guid,
                    a.file_path,
                    a.valid,
                    a.checksum_ok,
                    len(a.issues),
                ])
        self.logger.info("Asset inventory written. path=%s", path)

    def _write_validation_report(self, result: PackageValidationResult) -> None:
        path = self.output_dir / "validation_report.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["object_name", "object_type", "path",
                              "valid", "checksum_ok", "issues"])
            for a in result.assets:
                writer.writerow([
                    a.object_name,
                    a.object_type,
                    a.path,
                    a.valid,
                    a.checksum_ok,
                    " | ".join(a.issues) if a.issues else "OK",
                ])
        self.logger.info("Validation report written. path=%s", path)

    def _write_checksum_report(self, result: PackageValidationResult) -> None:
        path = self.output_dir / "checksum_report.csv"
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["object_name", "object_type", "file_path", "checksum_ok"])
            for a in result.assets:
                writer.writerow([a.object_name, a.object_type, a.file_path, a.checksum_ok])
        self.logger.info("Checksum report written. path=%s", path)

    def _build_summary(self, result: PackageValidationResult, output_zip: Path) -> dict[str, Any]:
        return {
            "status": "success" if result.invalid_assets == 0 else "partial",
            "input_zip": str(self.input_zip),
            "output_zip": str(output_zip),
            "output_zip_size_bytes": output_zip.stat().st_size if output_zip.exists() else 0,
            "total_assets": result.total_assets,
            "valid_assets": result.valid_assets,
            "invalid_assets": result.invalid_assets,
            "missing_files": result.missing_files,
            "checksum_failures": result.checksum_failures,
            "asset_types": result.asset_types,
            "asset_type_labels": {
                k: self.ASSET_TYPE_LABELS.get(k, k)
                for k in result.asset_types
            },
            "reports": {
                "asset_inventory": str(self.output_dir / "asset_inventory.csv"),
                "validation_report": str(self.output_dir / "validation_report.csv"),
                "checksum_report": str(self.output_dir / "checksum_report.csv"),
                "summary": str(self.output_dir / "summary.json"),
            },
        }

    def _write_summary(self, summary: dict[str, Any]) -> None:
        path = self.output_dir / "summary.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2)
        self.logger.info("Summary written. path=%s", path)

    # ── utilities ────────────────────────────────────────────────────────────

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
