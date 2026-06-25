from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text

from common.config.config import AppConfig


class MySqlMetadataRepository:
    """Persists canonical PowerCenter metadata into the central MySQL repository."""

    TABLES = [
        "connectors",
        "sql_overrides",
        "columns_metadata",
        "transformations",
        "mappings",
        "assets",
    ]

    def __init__(self, config: AppConfig, logger) -> None:
        self.config = config
        self.logger = logger
        self.project_root = Path.cwd()
        self.output_folder = self._resolve_path(config.paths.output_folder)
        self.canonical_tables_folder = self.output_folder / "canonical" / "tables"

    def persist(self) -> dict[str, int]:
        self._ensure_database()
        engine = self._database_engine()

        assets = self._read_csv("canonical_assets.csv")
        mappings = self._read_csv("canonical_mappings.csv")
        transformations = self._read_csv("canonical_transformations.csv")
        columns = self._read_csv("canonical_columns.csv")
        sql_overrides = self._read_csv("canonical_sql_overrides.csv")
        connectors = self._read_csv("canonical_connectors.csv")

        with engine.begin() as connection:
            self._drop_existing_tables(connection)
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

    def _drop_existing_tables(self, connection) -> None:
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in self.TABLES:
            connection.execute(text(f"DROP TABLE IF EXISTS `{table}`"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    def _create_tables(self, connection) -> None:
        connection.execute(
            text(
                """
                CREATE TABLE assets (
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
                CREATE TABLE mappings (
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
                CREATE TABLE transformations (
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
                CREATE TABLE columns_metadata (
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
                CREATE TABLE sql_overrides (
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
                CREATE TABLE connectors (
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

    def _ensure_database(self) -> None:
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
        db = self.config.database
        url = f"{db.driver}://{quote_plus(db.username)}:{quote_plus(db.password)}@{db.host}:{db.port}"
        return create_engine(url, future=True)

    def _database_engine(self):
        db = self.config.database
        url = (
            f"{db.driver}://{quote_plus(db.username)}:{quote_plus(db.password)}"
            f"@{db.host}:{db.port}/{db.database}"
        )
        return create_engine(url, future=True)

    def _read_csv(self, file_name: str) -> list[dict[str, str]]:
        path = self.canonical_tables_folder / file_name
        if not path.exists():
            raise FileNotFoundError(f"Required canonical table not found: {path}")
        with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
            return list(csv.DictReader(csv_file))

    @staticmethod
    def _mapping_row(row: dict[str, str]) -> dict[str, object]:
        return {
            **row,
            "transformation_count": MySqlMetadataRepository._to_int(row.get("transformation_count", "")),
            "connector_count": MySqlMetadataRepository._to_int(row.get("connector_count", "")),
            "sql_override_count": MySqlMetadataRepository._to_int(row.get("sql_override_count", "")),
        }

    @staticmethod
    def _transformation_row(row: dict[str, str]) -> dict[str, object]:
        return {
            **row,
            "attribute_count": MySqlMetadataRepository._to_int(row.get("attribute_count", "")),
            "port_count": MySqlMetadataRepository._to_int(row.get("port_count", "")),
        }

    @staticmethod
    def _to_int(value: str) -> int:
        try:
            return int(value or 0)
        except ValueError:
            return 0

    @staticmethod
    def _validate_identifier(value: str) -> None:
        if not value.replace("_", "").isalnum():
            raise ValueError(f"Unsafe database identifier: {value}")

    def _resolve_path(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return self.project_root / candidate
