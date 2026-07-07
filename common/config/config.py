"""
Support config for shared application infrastructure.
Provides configuration, logging, constants, and reusable helpers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseConfig:
    """Stores configuration values used by the application."""

    host: str
    port: int
    username: str
    password: str
    database: str
    driver: str


@dataclass(frozen=True)
class PathConfig:
    """Stores configuration values used by the application."""

    xml_folder: str
    output_folder: str
    log_folder: str


@dataclass(frozen=True)
class LoggingConfig:
    """Stores configuration values used by the application."""

    level: str
    file_name: str
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class AppConfig:
    """Stores configuration values used by the application."""

    database: DatabaseConfig
    paths: PathConfig
    logging: LoggingConfig


class ConfigLoader:
    """Encapsulates config loader behavior for migration workflows."""

    def __init__(self, config_path: Path) -> None:
        """Initialize migration data using the provided config_path."""

        self.config_path = config_path

    def load(self) -> AppConfig:
        """Load migration data for the migration workflow."""

        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        with self.config_path.open("r", encoding="utf-8") as config_file:
            raw = json.load(config_file)

        try:
            return AppConfig(
                database=DatabaseConfig(**raw["database"]),
                paths=PathConfig(**raw["paths"]),
                logging=LoggingConfig(**raw["logging"]),
            )
        except KeyError as exc:
            raise KeyError(f"Missing required config section or key: {exc}") from exc
