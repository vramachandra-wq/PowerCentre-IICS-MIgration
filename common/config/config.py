"""
Module: common/config/config.py

Purpose:
    This module supports configuration loading for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the configuration loading area and turns project configuration files into typed application settings. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatabaseConfig:
    """
    Represents the DatabaseConfig component in the configuration loading area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that turns project configuration files into typed application settings. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    host: str
    port: int
    username: str
    password: str
    database: str
    driver: str


@dataclass(frozen=True)
class PathConfig:
    """
    Represents the PathConfig component in the configuration loading area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that turns project configuration files into typed application settings. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    xml_folder: str
    output_folder: str
    log_folder: str


@dataclass(frozen=True)
class LoggingConfig:
    """
    Represents the LoggingConfig component in the configuration loading area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that turns project configuration files into typed application settings. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    level: str
    file_name: str
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class AppConfig:
    """
    Represents the AppConfig component in the configuration loading area.
    
    Purpose:
        Provide a named object that groups related state and behavior for this module.
    
    Responsibilities:
        - Encapsulate the data or operations required by the surrounding workflow.
        - Collaborate with parser, validation, automation, API, or report components where this class is used.
        - Keep behavior predictable so migration assessment outputs remain traceable and easy to review.
    
    Architecture Notes:
        This class is part of the project layer that turns project configuration files into typed application settings. Instances or class methods are used by higher-level orchestration code, services, tests, or report builders without changing business rules.
    """

    database: DatabaseConfig
    paths: PathConfig
    logging: LoggingConfig


class ConfigLoader:
    """Loads strongly typed application configuration from JSON."""

    def __init__(self, config_path: Path) -> None:
        """
        Executes the __init__ workflow for configuration loading.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
                config_path (object): Value supplied by the caller and used by the workflow.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that turns project configuration files into typed application settings. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

        self.config_path = config_path

    def load(self) -> AppConfig:
        """
        Executes the load workflow for configuration loading.
        
        Purpose:
            Support the module responsibility by performing one focused step in the migration assessment process.
        
        Workflow:
            1. Receive inputs from the caller or surrounding service layer.
            2. Apply the existing project logic without changing business rules.
            3. Return data in the format expected by downstream parser, validation, API, reporting, or test code.
        
        Parameters:
        None.
        
        Returns:
            object:
                The function returns the value required by existing callers. The concrete type is defined by the function annotation or by the established project contract.
        
        Raises:
            Exception:
                This function does not add custom exception handling beyond the existing implementation; exceptions propagate according to the current workflow.
        
        Implementation Notes:
            This function belongs to the layer that turns project configuration files into typed application settings. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
        """

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
