from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from automation.evaluation_matrix import ReportRepository
from common.config.config import ConfigLoader
from common.logger.logger import LoggerFactory


@lru_cache(maxsize=1)
def get_logger():
    config = ConfigLoader(Path("common/config/config.json")).load()
    return LoggerFactory.create_logger(config.logging, config.paths.log_folder)


def get_repository() -> ReportRepository:
    return ReportRepository()
