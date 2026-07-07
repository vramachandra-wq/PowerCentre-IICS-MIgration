"""
Support logger for shared application infrastructure.
Provides configuration, logging, constants, and reusable helpers.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from common.config.config import LoggingConfig


class LoggerFactory:
    """Encapsulates logger factory behavior for migration workflows."""

    LOGGER_NAME = "pc_iics_migration"

    @classmethod
    def create_logger(cls, config: LoggingConfig, log_folder: str | Path = "logs") -> logging.Logger:
        """Create logger using the provided config and log_folder."""

        logger = logging.getLogger(cls.LOGGER_NAME)
        logger.setLevel(cls._level(config.level))
        logger.propagate = False

        # Retry-safe logging: repeated CLI runs in the same interpreter should not duplicate handlers.
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

        resolved_log_folder = Path(log_folder)
        if not resolved_log_folder.is_absolute():
            resolved_log_folder = Path.cwd() / resolved_log_folder
        resolved_log_folder.mkdir(parents=True, exist_ok=True)
        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(module)s.%(funcName)s:%(lineno)d | %(message)s"
        )

        file_handler = RotatingFileHandler(
            resolved_log_folder / config.file_name,
            maxBytes=config.max_bytes,
            backupCount=config.backup_count,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(cls._level(config.level))

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(cls._level(config.level))

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        return logger

    @staticmethod
    def _level(level_name: str) -> int:
        """Handle level using the provided level_name."""

        return getattr(logging, level_name.upper(), logging.INFO)
