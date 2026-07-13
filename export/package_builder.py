"""Shared helpers for IDMC review package generation."""

from __future__ import annotations

import csv
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


def safe_name(value: str, fallback: str = "asset", max_length: int = 120) -> str:
    """Return a filesystem-safe review package asset name."""

    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("._")
    cleaned = cleaned or fallback
    if max_length and len(cleaned) > max_length:
        digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:8]
        cleaned = f"{cleaned[: max_length - 9].rstrip('._-')}_{digest}"
    return cleaned


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV file if it exists, otherwise return an empty row list."""

    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        return list(csv.DictReader(csv_file))


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str]) -> None:
    """Write CSV rows, creating parent folders as needed."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def group_by(rows: Iterable[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    """Group CSV rows by a non-empty key."""

    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        value = row.get(key, "")
        if value:
            grouped[value].append(row)
    return grouped


@dataclass(frozen=True)
class ReviewSession:
    """Session to mapping relationship extracted from existing metadata."""

    session_name: str
    mapping_name: str
    folder_name: str
    repository_name: str
    file_name: str


@dataclass(frozen=True)
class ReviewWorkflow:
    """Workflow with all session to mapping relationships preserved."""

    workflow_name: str
    folder_name: str
    repository_name: str
    file_name: str
    server_name: str = ""
    sessions: list[ReviewSession] = field(default_factory=list)


@dataclass(frozen=True)
class GeneratedAsset:
    """Generated review package asset metadata."""

    workflow: str
    session: str
    mapping: str
    asset_type: str
    file_name: str
