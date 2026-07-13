"""Build an IDMC-style review package from existing migration outputs."""

from __future__ import annotations

import logging
import os
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path

from export.checksum_generator import ChecksumGenerator
from export.mapping_package_generator import MappingPackageGenerator
from export.metadata_generator import MetadataGenerator
from export.package_builder import GeneratedAsset, ReviewSession, ReviewWorkflow, group_by, read_csv, safe_name
from export.taskflow_generator import TaskflowGenerator
from export.zip_generator import ZipGenerator


class IDMCReviewPackageGenerator:
    """Generate a client review ZIP using already-produced migration metadata."""

    ZIP_NAME = "Migration_Review_Package.zip"

    def __init__(self, output_folder: str | Path = "output", logger: logging.Logger | None = None) -> None:
        self.output_folder = Path(output_folder)
        self.package_folder = self.output_folder / "idmc_review_package"
        self.package_root = self.package_folder / "package"
        self.zip_path = self.package_folder / self.ZIP_NAME
        self.metadata_folder = self.output_folder / "metadata_tables"
        self.logger = logger or logging.getLogger(__name__)

    def build(self) -> dict[str, object]:
        """Build the review package and return a compact summary."""

        self.logger.info("Generating IDMC Review Package...")
        self._prepare_package_root()
        tables = self._load_tables()
        workflows = self._build_workflows(tables["workflows"], tables["sessions"])
        assets: list[GeneratedAsset] = []

        explore_dir = self.package_root / "Explore"
        sys_dir = self.package_root / "SYS"
        assets.extend(self._generate_metadata_files(explore_dir, sys_dir, workflows, tables))
        assets.extend(self._generate_workflow_assets(explore_dir, workflows, tables))
        assets.extend(self._copy_remediated_xml(explore_dir))
        assets.extend(self._copy_existing_metadata_outputs(explore_dir))

        metadata_generator = MetadataGenerator()
        assets.append(metadata_generator.write_export_metadata(self.package_root, assets))
        assets.append(metadata_generator.write_contents_csv(self.package_root, assets))

        self.logger.info("Generating checksum metadata...")
        checksum_path = ChecksumGenerator().write(self.package_root)
        assets.append(GeneratedAsset("", "", "", "Checksum", checksum_path.relative_to(self.package_root).as_posix()))

        self.logger.info("Generating ZIP...")
        try:
            zip_path = ZipGenerator().write(self.package_root, self.zip_path)
        except PermissionError as exc:
            if not self.zip_path.exists():
                raise
            self.logger.warning("Could not replace existing review package ZIP; keeping current ZIP. %s", exc)
            zip_path = self.zip_path
        self._cleanup_staging()
        self.logger.info("Package Generation Completed. output=%s assets=%s", zip_path, len(assets))
        return {
            "zip_path": str(zip_path),
            "package_root": str(self.package_root),
            "workflow_count": len(workflows),
            "asset_count": len(assets),
        }

    def _prepare_package_root(self) -> None:
        self.package_folder.mkdir(parents=True, exist_ok=True)
        for stale in sorted(self.package_folder.glob("package_*")):
            if stale.is_dir():
                try:
                    self._remove_tree(stale)
                except PermissionError as exc:
                    self.logger.warning("Could not remove stale review package staging folder: %s. %s", stale, exc)
        if self.package_root.exists():
            try:
                self._remove_tree(self.package_root)
            except PermissionError as exc:
                self.logger.warning("Could not remove previous review package staging folder; using a fresh staging folder. %s", exc)
                suffix = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
                self.package_root = self.package_folder / f"package_{suffix}"
        self.package_root.mkdir(parents=True, exist_ok=True)

    def _cleanup_staging(self) -> None:
        try:
            self._remove_tree(self.package_root)
        except PermissionError as exc:
            self.logger.warning("Could not remove review package staging folder after ZIP generation. %s", exc)

    @staticmethod
    def _remove_tree(path: Path) -> None:
        def reset_permissions(function, target, exc_info) -> None:
            os.chmod(target, stat.S_IWRITE)
            function(target)

        shutil.rmtree(path, onexc=reset_permissions)

    def _load_tables(self) -> dict[str, list[dict[str, str]]]:
        names = [
            "workflows",
            "sessions",
            "mappings",
            "transformations",
            "ports",
            "instances",
            "connectors",
            "sources",
            "targets",
            "folders",
            "repositories",
        ]
        tables: dict[str, list[dict[str, str]]] = {}
        for name in names:
            path = self.metadata_folder / f"{name}.csv"
            rows = read_csv(path)
            if not rows:
                self.logger.warning("IDMC review package metadata missing or empty: %s", path)
            tables[name] = rows
        return tables

    def _build_workflows(
        self,
        workflow_rows: list[dict[str, str]],
        session_rows: list[dict[str, str]],
    ) -> list[ReviewWorkflow]:
        sessions_by_file = group_by(session_rows, "file_name")
        workflows: list[ReviewWorkflow] = []
        for workflow_row in workflow_rows:
            file_name = workflow_row.get("file_name", "")
            sessions = [
                ReviewSession(
                    session_name=row.get("session_name", ""),
                    mapping_name=row.get("mapping_name", ""),
                    folder_name=row.get("folder_name", workflow_row.get("folder_name", "")),
                    repository_name=row.get("repository_name", workflow_row.get("repository_name", "")),
                    file_name=row.get("file_name", file_name),
                )
                for row in sessions_by_file.get(file_name, [])
            ]
            if not sessions:
                self.logger.warning("No sessions found for workflow=%s file=%s", workflow_row.get("workflow_name", ""), file_name)
            workflows.append(
                ReviewWorkflow(
                    workflow_name=workflow_row.get("workflow_name", Path(file_name).stem),
                    folder_name=workflow_row.get("folder_name", ""),
                    repository_name=workflow_row.get("repository_name", ""),
                    file_name=file_name,
                    server_name=workflow_row.get("server_name", ""),
                    sessions=sessions,
                )
            )
        return workflows

    def _generate_metadata_files(
        self,
        explore_dir: Path,
        sys_dir: Path,
        workflows: list[ReviewWorkflow],
        tables: dict[str, list[dict[str, str]]],
    ) -> list[GeneratedAsset]:
        self.logger.info("Generating Metadata...")
        generator = MetadataGenerator()
        assets = [
            generator.write_project_metadata(explore_dir, tables["repositories"], workflows),
            generator.write_folder_metadata(explore_dir, tables["folders"]),
        ]
        assets.extend(generator.write_sys_metadata(sys_dir, workflows, tables["sources"], tables["targets"]))
        return assets

    def _generate_workflow_assets(
        self,
        explore_dir: Path,
        workflows: list[ReviewWorkflow],
        tables: dict[str, list[dict[str, str]]],
    ) -> list[GeneratedAsset]:
        taskflow_generator = TaskflowGenerator()
        mapping_generator = MappingPackageGenerator(
            mappings={row.get("mapping_name", ""): row for row in tables["mappings"] if row.get("mapping_name")},
            transformations=group_by(tables["transformations"], "mapping_name"),
            ports=group_by(tables["ports"], "mapping_name"),
            instances=group_by(tables["instances"], "mapping_name"),
            connectors=group_by(tables["connectors"], "mapping_name"),
            sources_by_file=group_by(tables["sources"], "file_name"),
            targets_by_file=group_by(tables["targets"], "file_name"),
        )
        assets: list[GeneratedAsset] = []
        for workflow in workflows:
            self.logger.info("Generating Workflow Package... workflow=%s", workflow.workflow_name)
            assets.append(taskflow_generator.generate(workflow, explore_dir / "Taskflows"))
            for session in workflow.sessions:
                if not session.mapping_name:
                    self.logger.warning("Session has no mapping. workflow=%s session=%s", workflow.workflow_name, session.session_name)
                    continue
                self.logger.info(
                    "Generating Mapping Package... workflow=%s session=%s mapping=%s",
                    workflow.workflow_name,
                    session.session_name,
                    session.mapping_name,
                )
                assets.append(mapping_generator.generate(workflow, session, explore_dir / "MappingPackages"))
        return assets

    def _copy_remediated_xml(self, explore_dir: Path) -> list[GeneratedAsset]:
        source_dir = self.output_folder / "remediated_xml"
        destination_dir = explore_dir / "RemediatedXML"
        assets: list[GeneratedAsset] = []
        if not source_dir.exists():
            self.logger.warning("Remediated XML folder missing: %s", source_dir)
            return assets
        destination_dir.mkdir(parents=True, exist_ok=True)
        for source in sorted(source_dir.glob("*.xml")):
            target = destination_dir / safe_name(source.name, source.name)
            shutil.copy2(source, target)
            assets.append(GeneratedAsset("", "", "", "Remediated XML", target.relative_to(self.package_root).as_posix()))
        return assets

    def _copy_existing_metadata_outputs(self, explore_dir: Path) -> list[GeneratedAsset]:
        assets: list[GeneratedAsset] = []
        copy_specs = [
            (self.output_folder / "metadata_tables", explore_dir / "Metadata" / "metadata_tables", ("*.csv",)),
            (self.output_folder / "canonical", explore_dir / "Metadata" / "canonical", ("*.json", "*.csv")),
            (self.output_folder / "parsed_json", explore_dir / "Metadata" / "parsed_json", ("*.json",)),
            (self.output_folder / "reports", explore_dir / "Reports", ("*.csv", "*.json", "*.md")),
            (self.output_folder / "automation", explore_dir / "Reports" / "automation", ("*.csv", "*.json")),
        ]
        root_patterns = ("*.csv", "*.json", "*.md")
        for path in self._iter_matching_files(self.output_folder, root_patterns):
            if self.package_folder in path.parents:
                continue
            target = explore_dir / "Reports" / "root" / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            assets.append(GeneratedAsset("", "", "", "Migration Report", target.relative_to(self.package_root).as_posix()))
        for source_dir, target_dir, patterns in copy_specs:
            if not source_dir.exists():
                self.logger.warning("Optional review package input folder missing: %s", source_dir)
                continue
            for path in self._iter_matching_files(source_dir, patterns):
                target = target_dir / path.relative_to(source_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                assets.append(GeneratedAsset("", "", "", "Migration Metadata", target.relative_to(self.package_root).as_posix()))
        return assets

    @staticmethod
    def _iter_matching_files(source_dir: Path, patterns: tuple[str, ...]) -> list[Path]:
        files: list[Path] = []
        for pattern in patterns:
            files.extend(path for path in source_dir.rglob(pattern) if path.is_file())
        return sorted(set(files))


def build_idmc_review_package(output_folder: str | Path = "output", logger: logging.Logger | None = None) -> dict[str, object]:
    """Build the IDMC review package using existing migration output artifacts."""

    return IDMCReviewPackageGenerator(output_folder=output_folder, logger=logger).build()
