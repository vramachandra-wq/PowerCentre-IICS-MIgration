"""
Persist generated automation reports into MySQL.
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


CSV_REPORTS = [
    ("complexity_classification_report.csv", "complexity_classification_report"),
    ("remediation_report.csv", "remediation_report"),
    ("automation/evaluation_matrix.csv", "evaluation_matrix"),
    ("automation/ai_evaluation_dataset.csv", "ai_evaluation_dataset"),
    ("automation/ai_evaluation_matrix.csv", "ai_evaluation_matrix"),
    ("automation/ai_recommendation_report.csv", "ai_recommendation_report"),
]

LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+"
    r"(?P<level>[A-Z]+)\s+"
    r"(?P<module>[\w.]+)\s+-\s+"
    r"(?P<message>.*)$"
)


@dataclass(frozen=True)
class MySQLPersistenceConfig:
    """Stores MySQL persistence settings."""

    enabled: bool
    host: str
    port: int
    username: str
    password: str
    database: str
    batch_size: int = 1000


class MySQLReportPersistence:
    """Persists generated report files into MySQL tables."""

    METADATA_COLUMNS = {"id", "row_hash", "timestamp"}

    def __init__(
        self,
        config: MySQLPersistenceConfig,
        output_folder: str | Path,
        reports_folder: str | Path,
        logs_folder: str | Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.output_folder = Path(output_folder)
        self.reports_folder = Path(reports_folder)
        self.logs_folder = Path(logs_folder)
        self.logger = logger or logging.getLogger(__name__)

    @classmethod
    def from_project_config(
        cls,
        project_root: str | Path,
        output_folder: str | Path,
        reports_folder: str | Path,
        logs_folder: str | Path,
        payload: dict[str, Any],
        logger: logging.Logger | None = None,
    ) -> "MySQLReportPersistence":
        """Create persistence service from automation and shared database config."""

        project_root = Path(project_root)
        mysql_payload = payload.get("mysql_persistence", {})
        shared_config_path = project_root / str(mysql_payload.get("config_path", "common/config/config.json"))
        database_payload: dict[str, Any] = {}
        if shared_config_path.exists():
            with shared_config_path.open("r", encoding="utf-8-sig") as config_file:
                database_payload = json.load(config_file).get("database", {})

        config = MySQLPersistenceConfig(
            enabled=bool(mysql_payload.get("enabled", True)),
            host=str(mysql_payload.get("host", database_payload.get("host", "localhost"))),
            port=int(mysql_payload.get("port", database_payload.get("port", 3306))),
            username=str(mysql_payload.get("username", database_payload.get("username", ""))),
            password=str(mysql_payload.get("password", database_payload.get("password", ""))),
            database=str(mysql_payload.get("database", database_payload.get("database", ""))),
            batch_size=int(mysql_payload.get("batch_size", 1000)),
        )
        return cls(config, output_folder, reports_folder, logs_folder, logger=logger)

    def persist_all(self, runtime_timestamp: datetime) -> dict[str, int]:
        """Persist configured reports and return row counts by table."""

        if not self.config.enabled:
            self.logger.info("MySQL report persistence is disabled.")
            return {}

        timestamp = runtime_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        counts: dict[str, int] = {}
        connection = self._connect()
        try:
            self._ensure_database(connection)
            connection.database = self.config.database

            for relative_path, table_name in CSV_REPORTS:
                path = self._existing_report_path(relative_path)
                rows = self._read_csv(path, include_report_row_number=table_name == "remediation_report")
                counts[table_name] = self._persist_rows(
                    connection,
                    table_name,
                    rows,
                    timestamp,
                    source_name=str(path),
                    refresh_table=True,
                )

            validation_path = self._existing_report_path("automation/validation_summary.json")
            rows = self._read_json(validation_path)
            counts["validation_summary"] = self._persist_rows(
                connection,
                "validation_summary",
                rows,
                timestamp,
                source_name=str(validation_path),
                refresh_table=True,
            )

            parsed_json_folder = self.output_folder / "parsed_json"
            if parsed_json_folder.exists():
                for json_path in sorted(parsed_json_folder.glob("*.json")):
                    table_name = self._safe_identifier(json_path.stem)
                    rows = self._read_json(json_path)
                    counts[table_name] = self._persist_rows(
                        connection,
                        table_name,
                        rows,
                        timestamp,
                        source_name=str(json_path),
                        refresh_table=True,
                    )
            else:
                self.logger.warning("Parsed JSON folder not found: %s", parsed_json_folder)

            log_rows = self._read_automation_log()
            counts["automation_log"] = self._persist_rows(
                connection,
                "automation_log",
                log_rows,
                timestamp,
                source_name="automation.log",
                append_only=True,
            )
            connection.commit()
            self.logger.info("MySQL report persistence completed. table_counts=%s", counts)
            return counts
        except Exception:
            try:
                connection.rollback()
            except Exception:
                self.logger.exception("Unable to roll back MySQL report persistence transaction.")
            self.logger.exception("MySQL report persistence failed.")
            raise
        finally:
            connection.close()

    def _connect(self):
        """Create a MySQL connection."""

        try:
            import mysql.connector
            from mysql.connector import Error
        except ImportError as exc:
            raise RuntimeError("mysql-connector-python is required for MySQL report persistence.") from exc

        try:
            return mysql.connector.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.username,
                password=self.config.password,
                autocommit=False,
            )
        except Error as exc:
            raise ConnectionError(f"Unable to connect to MySQL at {self.config.host}:{self.config.port}") from exc

    def _ensure_database(self, connection) -> None:
        if not self.config.database:
            raise ValueError("MySQL database name is required for report persistence.")
        cursor = connection.cursor()
        try:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{self._safe_identifier(self.config.database)}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        finally:
            cursor.close()

    def _persist_rows(
        self,
        connection,
        table_name: str,
        rows: list[dict[str, Any]],
        timestamp: str,
        source_name: str,
        refresh_table: bool = False,
        append_only: bool = False,
    ) -> int:
        table_name = self._safe_identifier(table_name)
        if refresh_table:
            self._drop_table(connection, table_name)
        if not rows:
            self.logger.warning("No rows available for MySQL table %s from %s", table_name, source_name)
            self._ensure_table(connection, table_name, ["source_file"])
            return 0

        normalized_rows = [self._normalize_row(row, source_name) for row in rows]
        columns = sorted({column for row in normalized_rows for column in row.keys()})
        self._ensure_table(connection, table_name, columns)
        self._ensure_columns(connection, table_name, columns)
        if append_only:
            affected = self._insert_ignore_rows(connection, table_name, columns, normalized_rows, timestamp)
        else:
            affected = self._upsert_rows(connection, table_name, columns, normalized_rows, timestamp)
        self.logger.info("Persisted %s row(s) into MySQL table %s.", len(normalized_rows), table_name)
        return affected

    def _drop_table(self, connection, table_name: str) -> None:
        """Drop a generated latest-state report table before recreating it."""

        table_name = self._safe_identifier(table_name)
        cursor = connection.cursor()
        try:
            cursor.execute("SHOW TABLES LIKE %s", (table_name,))
            if cursor.fetchone() is None:
                return
            cursor.execute(f"DROP TABLE `{table_name}`")
            self.logger.info("Dropped MySQL report table before refresh: %s", table_name)
        except Exception:
            self.logger.exception("Unable to drop MySQL table before refresh: %s", table_name)
            raise
        finally:
            cursor.close()

    def _ensure_table(self, connection, table_name: str, columns: Iterable[str]) -> None:
        cursor = connection.cursor()
        column_sql = ", ".join(f"`{self._safe_identifier(column)}` LONGTEXT NULL" for column in columns)
        if column_sql:
            column_sql = ", " + column_sql
        try:
            unique_key = self._safe_identifier(f"uq_{table_name}_row_hash")
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{table_name}` (
                    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
                    `row_hash` CHAR(64) NOT NULL,
                    `timestamp` DATETIME NOT NULL
                    {column_sql},
                    UNIQUE KEY `{unique_key}` (`row_hash`)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                """
            )
        finally:
            cursor.close()

    def _ensure_columns(self, connection, table_name: str, columns: Iterable[str]) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
            existing_raw = {str(row[0]) for row in cursor.fetchall()}
            existing_safe = {
                self._safe_identifier(column)
                for column in existing_raw
                if column.lower() == self._safe_identifier(column).lower()
            }
            if "row_hash" not in existing_safe:
                cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `row_hash` CHAR(64) NULL")
                existing_safe.add("row_hash")
            if "timestamp" not in existing_safe:
                cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `timestamp` DATETIME NULL")
                existing_safe.add("timestamp")
            for column in columns:
                safe_column = self._safe_identifier(column)
                if safe_column not in existing_safe and safe_column not in self.METADATA_COLUMNS:
                    cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{safe_column}` LONGTEXT NULL")
                    existing_safe.add(safe_column)
            self._ensure_unique_row_hash_index(cursor, table_name)
        finally:
            cursor.close()

    def _ensure_unique_row_hash_index(self, cursor, table_name: str) -> None:
        unique_key = self._safe_identifier(f"uq_{table_name}_row_hash")
        cursor.execute(f"SHOW INDEX FROM `{table_name}`")
        existing_indexes = {self._safe_identifier(str(row[2])) for row in cursor.fetchall()}
        if unique_key not in existing_indexes:
            cursor.execute(f"ALTER TABLE `{table_name}` ADD UNIQUE KEY `{unique_key}` (`row_hash`)")

    def _upsert_rows(
        self,
        connection,
        table_name: str,
        columns: list[str],
        rows: list[dict[str, Any]],
        timestamp: str,
    ) -> int:
        if not rows:
            return 0
        cursor = connection.cursor()
        safe_columns = [self._safe_identifier(column) for column in columns]
        insert_columns = ["row_hash", "timestamp", *safe_columns]
        placeholders = ", ".join(["%s"] * len(insert_columns))
        update_columns = ["`timestamp` = VALUES(`timestamp`)", *[
            f"`{column}` = VALUES(`{column}`)" for column in safe_columns
        ]]
        sql = (
            f"INSERT INTO `{table_name}` ({', '.join(f'`{column}`' for column in insert_columns)}) "
            f"VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {', '.join(update_columns)}"
        )
        values = [
            (
                self._row_hash(row),
                timestamp,
                *[self._stringify(row.get(column, "")) for column in columns],
            )
            for row in rows
        ]
        try:
            batch_size = max(self.config.batch_size, 1)
            for start in range(0, len(values), batch_size):
                cursor.executemany(sql, values[start : start + batch_size])
            return len(values)
        finally:
            cursor.close()

    def _insert_ignore_rows(
        self,
        connection,
        table_name: str,
        columns: list[str],
        rows: list[dict[str, Any]],
        timestamp: str,
    ) -> int:
        if not rows:
            return 0
        cursor = connection.cursor()
        safe_columns = [self._safe_identifier(column) for column in columns]
        insert_columns = ["row_hash", "timestamp", *safe_columns]
        placeholders = ", ".join(["%s"] * len(insert_columns))
        sql = (
            f"INSERT IGNORE INTO `{table_name}` ({', '.join(f'`{column}`' for column in insert_columns)}) "
            f"VALUES ({placeholders})"
        )
        values = [
            (
                self._row_hash(row),
                timestamp,
                *[self._stringify(row.get(column, "")) for column in columns],
            )
            for row in rows
        ]
        inserted = 0
        try:
            batch_size = max(self.config.batch_size, 1)
            for start in range(0, len(values), batch_size):
                cursor.executemany(sql, values[start : start + batch_size])
                inserted += max(cursor.rowcount, 0)
            return inserted
        finally:
            cursor.close()

    def _read_csv(self, path: Path, include_report_row_number: bool = False) -> list[dict[str, Any]]:
        if not path.exists():
            self.logger.warning("CSV report not found for MySQL persistence: %s", path)
            return []
        try:
            with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
                reader = csv.DictReader(csv_file)
                if not reader.fieldnames:
                    self.logger.warning("CSV report has no header: %s", path)
                    return []
                rows = [dict(row) for row in reader]
                if include_report_row_number:
                    return [
                        {"report_row_number": index, **row}
                        for index, row in enumerate(rows, start=1)
                    ]
                return rows
        except csv.Error as exc:
            self.logger.exception("Unable to parse CSV report: %s", path)
            raise ValueError(f"Unable to parse CSV report: {path}") from exc

    def _read_json(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            self.logger.warning("JSON report not found for MySQL persistence: %s", path)
            return []
        try:
            with path.open("r", encoding="utf-8") as json_file:
                payload = json.load(json_file)
        except json.JSONDecodeError as exc:
            self.logger.exception("Invalid JSON report: %s", path)
            raise ValueError(f"Invalid JSON report: {path}") from exc
        return self._flatten_json(payload)

    def _read_automation_log(self) -> list[dict[str, Any]]:
        candidates = [
            self.logs_folder / "automation.log",
            self.output_folder / "logs" / "automation.log",
        ]
        path = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
        if not path.exists():
            self.logger.warning("Automation log not found for MySQL persistence: %s", path)
            return []

        rows: list[dict[str, Any]] = []
        current: dict[str, Any] | None = None
        with path.open("r", encoding="utf-8", errors="replace") as log_file:
            for line_number, line in enumerate(log_file, start=1):
                line = line.rstrip("\n")
                match = LOG_PATTERN.match(line)
                if match:
                    current = {
                        "log_timestamp": match.group("timestamp"),
                        "log_level": match.group("level"),
                        "module": match.group("module"),
                        "message": match.group("message"),
                        "line_number": line_number,
                    }
                    rows.append(current)
                elif current:
                    current["message"] = f"{current['message']}\n{line}"
                elif line:
                    rows.append(
                        {
                            "log_timestamp": "",
                            "log_level": "",
                            "module": "",
                            "message": line,
                            "line_number": line_number,
                        }
                    )
        return rows

    def _existing_report_path(self, relative_path: str) -> Path:
        candidates = [
            self.output_folder / relative_path,
            self.reports_folder / Path(relative_path).name,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def _flatten_json(self, payload: Any) -> list[dict[str, Any]]:
        if payload in ({}, [], None):
            return []
        if isinstance(payload, list):
            rows: list[dict[str, Any]] = []
            for index, item in enumerate(payload):
                rows.extend(self._flatten_json_node(item, {"array_index": index}))
            return rows
        return self._flatten_json_node(payload, {})

    def _flatten_json_node(self, node: Any, parent: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
        if isinstance(node, dict):
            scalar_fields: dict[str, Any] = {}
            child_rows: list[list[dict[str, Any]]] = []
            for key, value in node.items():
                field_name = self._field_name(prefix, key)
                if isinstance(value, dict):
                    nested_rows = self._flatten_json_node(value, {}, field_name)
                    if len(nested_rows) == 1:
                        scalar_fields.update(nested_rows[0])
                    else:
                        child_rows.append(nested_rows)
                elif isinstance(value, list):
                    if not value:
                        scalar_fields[field_name] = ""
                    else:
                        expanded: list[dict[str, Any]] = []
                        for index, item in enumerate(value):
                            item_parent = {f"{field_name}_index": index}
                            expanded.extend(self._flatten_json_node(item, item_parent, field_name))
                        child_rows.append(expanded)
                else:
                    scalar_fields[field_name] = value
            base = {**parent, **scalar_fields}
            if not child_rows:
                return [base]
            rows: list[dict[str, Any]] = []
            for group in child_rows:
                for child in group:
                    rows.append({**base, **child})
            return rows
        if isinstance(node, list):
            rows = []
            for index, item in enumerate(node):
                rows.extend(self._flatten_json_node(item, {**parent, "array_index": index}, prefix))
            return rows
        field = prefix or "value"
        return [{**parent, field: node}]

    @staticmethod
    def _field_name(prefix: str, key: str) -> str:
        return f"{prefix}_{key}" if prefix else str(key)

    def _normalize_row(self, row: dict[str, Any], source_name: str) -> dict[str, Any]:
        normalized: dict[str, Any] = {"source_file": source_name}
        for key, value in row.items():
            column = self._safe_identifier(str(key))
            if column in self.METADATA_COLUMNS:
                column = f"data_{column}"
            normalized[column] = value
        return normalized

    @staticmethod
    def _row_hash(row: dict[str, Any]) -> str:
        identity_fields = {
            "source_file",
            "xml",
            "xml_name",
            "workflow",
            "session",
            "mapping",
            "mapping_name",
            "rule_name",
            "issue",
            "asset",
            "line_number",
            "report_row_number",
            "array_index",
            "name",
            "id",
        }
        identity = {
            key: value
            for key, value in row.items()
            if key in identity_fields or key.endswith("_id") or key.endswith("_index")
        }
        if not identity or set(identity) == {"source_file"}:
            identity = row
        payload = json.dumps(identity, sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _stringify(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True, ensure_ascii=False)
        return str(value)

    @staticmethod
    def _safe_identifier(value: str) -> str:
        identifier = re.sub(r"[^0-9a-zA-Z_]+", "_", value.strip())
        identifier = re.sub(r"_+", "_", identifier).strip("_").lower()
        if not identifier:
            identifier = "value"
        if identifier[0].isdigit():
            identifier = f"t_{identifier}"
        return identifier[:64]
