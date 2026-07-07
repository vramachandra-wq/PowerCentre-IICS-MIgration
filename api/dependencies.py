"""
Module: api/dependencies.py

Purpose:
    This module supports FastAPI service layer for the PowerCenter to IDMC migration assessment platform.

Responsibilities:
    - Provide the code and data structures needed by this part of the application.
    - Integrate with the surrounding parsing, validation, automation, API, or reporting workflow as appropriate.
    - Keep inputs and outputs consistent with the project reporting pipeline so downstream modules can consume them reliably.

Architecture Context:
    The file belongs to the FastAPI service layer area and exposes validation, recommendation, and evaluation results to UI and integration clients. It participates in the overall input -> processing -> output lifecycle where PowerCenter XML metadata and generated reports are transformed into migration readiness, validation, and AI recommendation insights.

Inputs and Outputs:
    Inputs generally include configuration values, XML-derived metadata, CSV/JSON report rows, API payloads, or test fixtures. Outputs are returned Python objects, API responses, generated report records, or assertions that protect expected behavior.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from automation.evaluation_matrix import ReportRepository
from common.config.config import ConfigLoader
from common.logger.logger import LoggerFactory


@lru_cache(maxsize=1)
def get_logger():
    """
    Executes the get_logger workflow for FastAPI service layer.
    
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
        This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    config = ConfigLoader(Path("common/config/config.json")).load()
    return LoggerFactory.create_logger(config.logging, config.paths.log_folder)


def get_repository() -> ReportRepository:
    """
    Executes the get_repository workflow for FastAPI service layer.
    
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
        This function belongs to the layer that exposes validation, recommendation, and evaluation results to UI and integration clients. The documentation is intentionally business-readable so both technical reviewers and delivery stakeholders can follow the intent.
    """

    return ReportRepository()
