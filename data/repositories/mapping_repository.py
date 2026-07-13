"""
Support mapping repository for migration data structures and persistence.
Defines models and repository access for metadata workflows.
"""

from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

from common.config.config import AppConfig


class MySqlMetadataRepository:
    """Handles persistence operations for migration metadata."""

    TABLES = [
        "connectors",
        "sql_overrides",
        "columns_metadata",
        "transformations",
        "mappings",
        "assets",
    ]

    def __init__(self, config: AppConfig, logger) -> None:
        """Initialize migration data using the provided config and logger."""

        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(config.paths.output_folder)
        self.canonical_tables_folder = self.output_folder / "canonical" / "tables"

    def persist(self) -> dict[str, int]:
        """Handle persist for the migration workflow."""

        self._ensure_database()
        engine = self._database_engine()

        assets = self._read_csv("canonical_assets.csv")
        mappings = self._read_csv("canonical_mappings.csv")
        transformations = self._read_csv("canonical_transformations.csv")
        columns = self._read_csv("canonical_columns.csv")
        sql_overrides = self._read_csv("canonical_sql_overrides.csv")
        connectors = self._read_csv("canonical_connectors.csv")

        with engine.begin() as connection:
            self._create_tables(connection)

            connection.execute(
                text(
                    """
                    INSERT INTO assets (
                        asset_id, asset_name, asset_type, platform, repository_name,
                        folder_name, source_file, parent_asset_id, complexity, migration_status
                    )
                    VALUES (
                        :asset_id, :asset_name, :asset_type, :platform, :repository_name,
                        :folder_name, :source_file, :parent_asset_id, :complexity, NULL
                    )
                    ON DUPLICATE KEY UPDATE
                        asset_name = VALUES(asset_name),
                        asset_type = VALUES(asset_type),
                        platform = VALUES(platform),
                        repository_name = VALUES(repository_name),
                        folder_name = VALUES(folder_name),
                        source_file = VALUES(source_file),
                        parent_asset_id = VALUES(parent_asset_id),
                        complexity = VALUES(complexity)
                    """
                ),
                assets,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO mappings (
                        mapping_id, mapping_name, repository_name, folder_name, source_file,
                        sources, targets, transformation_count, connector_count,
                        sql_override_count, complexity
                    )
                    VALUES (
                        :mapping_id, :mapping_name, :repository_name, :folder_name, :source_file,
                        :sources, :targets, :transformation_count, :connector_count,
                        :sql_override_count, :complexity
                    )
                    ON DUPLICATE KEY UPDATE
                        mapping_name = VALUES(mapping_name),
                        repository_name = VALUES(repository_name),
                        folder_name = VALUES(folder_name),
                        source_file = VALUES(source_file),
                        sources = VALUES(sources),
                        targets = VALUES(targets),
                        transformation_count = VALUES(transformation_count),
                        connector_count = VALUES(connector_count),
                        sql_override_count = VALUES(sql_override_count),
                        complexity = VALUES(complexity)
                    """
                ),
                [self._mapping_row(row) for row in mappings],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO transformations (
                        transformation_id, mapping_id, mapping_name, transformation_name,
                        transformation_type, reusable_flag, attribute_count, port_count
                    )
                    VALUES (
                        :transformation_id, :mapping_id, :mapping_name, :transformation_name,
                        :transformation_type, :reusable_flag, :attribute_count, :port_count
                    )
                    ON DUPLICATE KEY UPDATE
                        mapping_id = VALUES(mapping_id),
                        mapping_name = VALUES(mapping_name),
                        transformation_name = VALUES(transformation_name),
                        transformation_type = VALUES(transformation_type),
                        reusable_flag = VALUES(reusable_flag),
                        attribute_count = VALUES(attribute_count),
                        port_count = VALUES(port_count)
                    """
                ),
                [self._transformation_row(row) for row in transformations],
            )
            connection.execute(
                text(
                    """
                    INSERT INTO columns_metadata (
                        column_id, asset_id, table_name, table_type, column_name, datatype,
                        precision_val, scale_val, repository_name, folder_name, source_file
                    )
                    VALUES (
                        :column_id, :asset_id, :table_name, :table_type, :column_name, :datatype,
                        :precision, :scale, :repository_name, :folder_name, :source_file
                    )
                    ON DUPLICATE KEY UPDATE
                        asset_id = VALUES(asset_id),
                        table_name = VALUES(table_name),
                        table_type = VALUES(table_type),
                        column_name = VALUES(column_name),
                        datatype = VALUES(datatype),
                        precision_val = VALUES(precision_val),
                        scale_val = VALUES(scale_val),
                        repository_name = VALUES(repository_name),
                        folder_name = VALUES(folder_name),
                        source_file = VALUES(source_file)
                    """
                ),
                columns,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO sql_overrides (
                        sql_override_id, mapping_id, mapping_name, context_type, context_name,
                        sql_query, review_status
                    )
                    VALUES (
                        :sql_override_id, :mapping_id, :mapping_name, :context_type,
                        :context_name, :sql_query, 'NOT_REVIEWED'
                    )
                    ON DUPLICATE KEY UPDATE
                        mapping_id = VALUES(mapping_id),
                        mapping_name = VALUES(mapping_name),
                        context_type = VALUES(context_type),
                        context_name = VALUES(context_name),
                        sql_query = VALUES(sql_query)
                    """
                ),
                sql_overrides,
            )
            connection.execute(
                text(
                    """
                    INSERT INTO connectors (
                        connector_id, mapping_id, mapping_name, from_instance, from_field,
                        to_instance, to_field, from_instance_type, to_instance_type
                    )
                    VALUES (
                        :connector_id, :mapping_id, :mapping_name, :from_instance, :from_field,
                        :to_instance, :to_field, :from_instance_type, :to_instance_type
                    )
                    ON DUPLICATE KEY UPDATE
                        mapping_id = VALUES(mapping_id),
                        mapping_name = VALUES(mapping_name),
                        from_instance = VALUES(from_instance),
                        from_field = VALUES(from_field),
                        to_instance = VALUES(to_instance),
                        to_field = VALUES(to_field),
                        from_instance_type = VALUES(from_instance_type),
                        to_instance_type = VALUES(to_instance_type)
                    """
                ),
                connectors,
            )

        summary = {
            "assets": len(assets),
            "mappings": len(mappings),
            "transformations": len(transformations),
            "columns_metadata": len(columns),
            "sql_overrides": len(sql_overrides),
            "connectors": len(connectors),
        }
        self.logger.info("Central metadata repository loaded. %s", summary)
        return summary

    def persist_complexity_report(self, report_path: str | Path | None = None) -> int:
        """Refresh the MySQL complexity classification report table."""

        self._ensure_database()
        path = Path(report_path) if report_path else self.output_folder / "complexity_classification_report.csv"
        if not path.exists():
            raise FileNotFoundError(f"Complexity classification report not found: {path}")

        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            rows = list(csv.DictReader(csv_file))

        engine = self._database_engine()
        with engine.begin() as connection:
            self._create_complexity_report_table(connection)
            connection.execute(text("DELETE FROM complexity_classification_report"))
            if rows:
                connection.execute(
                    text(
                        """
                        INSERT INTO complexity_classification_report (
                            `XML`, `Workflow`, `Session`, `Mapping`,
                            `Transformation Count`, `Complexity`, `Score`, `Reason`
                        )
                        VALUES (
                            :xml, :workflow, :session, :mapping,
                            :transformation_count, :complexity, :score, :reason
                        )
                        """
                    ),
                    [self._complexity_report_row(row) for row in rows],
                )

        return len(rows)

    def _drop_existing_tables(self, connection) -> None:
        """Handle drop existing tables using the provided connection."""

        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in self.TABLES:
            connection.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    def _create_tables(self, connection) -> None:
        """Create tables using the provided connection."""

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id VARCHAR(64) PRIMARY KEY,
                    asset_name VARCHAR(255) NOT NULL,
                    asset_type VARCHAR(50) NOT NULL,
                    platform VARCHAR(50) DEFAULT 'POWERCENTER',
                    repository_name VARCHAR(255),
                    folder_name VARCHAR(255),
                    source_file VARCHAR(255),
                    parent_asset_id VARCHAR(64),
                    complexity VARCHAR(10),
                    migration_status TINYINT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_asset_type (asset_type),
                    INDEX idx_complexity (complexity),
                    INDEX idx_migration_status (migration_status)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mappings (
                    mapping_id VARCHAR(64) PRIMARY KEY,
                    mapping_name VARCHAR(255) NOT NULL,
                    repository_name VARCHAR(255),
                    folder_name VARCHAR(255),
                    source_file VARCHAR(255),
                    sources TEXT,
                    targets TEXT,
                    transformation_count INT DEFAULT 0,
                    connector_count INT DEFAULT 0,
                    sql_override_count INT DEFAULT 0,
                    complexity VARCHAR(10),
                    FOREIGN KEY (mapping_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
                    INDEX idx_mapping_complexity (complexity)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS transformations (
                    transformation_id VARCHAR(64) PRIMARY KEY,
                    mapping_id VARCHAR(64) NOT NULL,
                    mapping_name VARCHAR(255),
                    transformation_name VARCHAR(255),
                    transformation_type VARCHAR(100),
                    reusable_flag VARCHAR(10),
                    attribute_count INT DEFAULT 0,
                    port_count INT DEFAULT 0,
                    FOREIGN KEY (mapping_id) REFERENCES mappings(mapping_id) ON DELETE CASCADE,
                    INDEX idx_trans_type (transformation_type)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS columns_metadata (
                    column_id VARCHAR(64) PRIMARY KEY,
                    asset_id VARCHAR(64) NOT NULL,
                    table_name VARCHAR(255),
                    table_type VARCHAR(20),
                    column_name VARCHAR(255),
                    datatype VARCHAR(50),
                    precision_val VARCHAR(20),
                    scale_val VARCHAR(20),
                    repository_name VARCHAR(255),
                    folder_name VARCHAR(255),
                    source_file VARCHAR(255),
                    FOREIGN KEY (asset_id) REFERENCES assets(asset_id) ON DELETE CASCADE,
                    INDEX idx_datatype (datatype),
                    INDEX idx_column_name (column_name)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS sql_overrides (
                    sql_override_id VARCHAR(64) PRIMARY KEY,
                    mapping_id VARCHAR(64) NOT NULL,
                    mapping_name VARCHAR(255),
                    context_type VARCHAR(20),
                    context_name VARCHAR(255),
                    sql_query TEXT,
                    review_status VARCHAR(30) DEFAULT 'NOT_REVIEWED',
                    FOREIGN KEY (mapping_id) REFERENCES mappings(mapping_id) ON DELETE CASCADE
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS connectors (
                    connector_id VARCHAR(64) PRIMARY KEY,
                    mapping_id VARCHAR(64) NOT NULL,
                    mapping_name VARCHAR(255),
                    from_instance VARCHAR(255),
                    from_field VARCHAR(255),
                    to_instance VARCHAR(255),
                    to_field VARCHAR(255),
                    from_instance_type VARCHAR(50),
                    to_instance_type VARCHAR(50),
                    FOREIGN KEY (mapping_id) REFERENCES mappings(mapping_id) ON DELETE CASCADE
                )
                """
            )
        )

    def _create_complexity_report_table(self, connection) -> None:
        """Create the complexity report table when it is missing."""

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS complexity_classification_report (
                    `XML` VARCHAR(255),
                    `Workflow` VARCHAR(255),
                    `Session` VARCHAR(255),
                    `Mapping` VARCHAR(255),
                    `Transformation Count` INT DEFAULT 0,
                    `Complexity` VARCHAR(20),
                    `Score` INT DEFAULT 0,
                    `Reason` TEXT,
                    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_complexity_report_mapping (`Mapping`),
                    INDEX idx_complexity_report_complexity (`Complexity`)
                )
                """
            )
        )

    def _ensure_database(self) -> None:
        """Handle ensure database for the migration workflow."""

        self._validate_identifier(self.config.database.database)
        engine = self._server_engine()
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{self.config.database.database}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )

    def _server_engine(self):
        """Handle server engine for the migration workflow."""

        db = self.config.database
        url = f"{db.driver}://{quote_plus(db.username)}:{quote_plus(db.password)}@{db.host}:{db.port}"
        return create_engine(url, future=True, connect_args={"connection_timeout": 5})

    def _database_engine(self):
        """Handle database engine for the migration workflow."""

        db = self.config.database
        url = (
            f"{db.driver}://{quote_plus(db.username)}:{quote_plus(db.password)}"
            f"@{db.host}:{db.port}/{db.database}"
        )
        return create_engine(url, future=True, connect_args={"connection_timeout": 5})

    def _read_csv(self, file_name: str) -> list[dict[str, str]]:
        """Handle read csv using the provided file_name."""

        path = self.canonical_tables_folder / file_name
        if not path.exists():
            raise FileNotFoundError(f"Required canonical table not found: {path}")
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    @staticmethod
    def _mapping_row(row: dict[str, str]) -> dict[str, object]:
        """Handle mapping row using the provided row."""

        return {
            **row,
            "transformation_count": MySqlMetadataRepository._to_int(row.get("transformation_count", "")),
            "connector_count": MySqlMetadataRepository._to_int(row.get("connector_count", "")),
            "sql_override_count": MySqlMetadataRepository._to_int(row.get("sql_override_count", "")),
        }

    @staticmethod
    def _transformation_row(row: dict[str, str]) -> dict[str, object]:
        """Handle transformation row using the provided row."""

        return {
            **row,
            "attribute_count": MySqlMetadataRepository._to_int(row.get("attribute_count", "")),
            "port_count": MySqlMetadataRepository._to_int(row.get("port_count", "")),
        }

    @staticmethod
    def _complexity_report_row(row: dict[str, str]) -> dict[str, object]:
        """Convert complexity report CSV values for MySQL insertion."""

        return {
            "xml": row.get("XML", ""),
            "workflow": row.get("Workflow", ""),
            "session": row.get("Session", ""),
            "mapping": row.get("Mapping", ""),
            "transformation_count": MySqlMetadataRepository._to_int(row.get("Transformation Count", "")),
            "complexity": row.get("Complexity", ""),
            "score": MySqlMetadataRepository._to_int(row.get("Score", "")),
            "reason": row.get("Reason", ""),
        }

    @staticmethod
    def _to_int(value: str) -> int:
        """Handle to int using the provided value."""

        try:
            return int(value or 0)
        except ValueError:
            return 0

    @staticmethod
    def _validate_identifier(value: str) -> None:
        """Validate identifier using the provided value."""

        if not value.replace("_", "").isalnum():
            raise ValueError(f"Unsafe database identifier: {value}")

    def _resolve_path(self, path: str | Path) -> Path:
        """Handle resolve path using the provided path."""

        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate
