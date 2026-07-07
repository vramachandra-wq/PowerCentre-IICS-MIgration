"""
Module: common/logger/logger.py

Purpose:
    This module supports project package support for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the project package support area and organizes imports and shared package behavior for the migration assessment application. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from common.config.config import LoggingConfig


class LoggerFactory:
    """Creates an idempotent console and file logger for repeatable executions."""

    LOGGER_NAME = "pc_iics_migration"

    @classmethod
    def create_logger(cls, config: LoggingConfig, log_folder: str | Path = "logs") -> logging.Logger:
        """
        Executes the create_logger workflow for project package support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                config (object): Value supplied by the caller and used by the workflow.
                log_folder (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that organizes imports and shared package behavior for the migration assessment application. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
        """
        Executes the _level workflow for project package support.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                level_name (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that organizes imports and shared package behavior for the migration assessment application. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        return getattr(logging, level_name.upper(), logging.INFO)
