"""Shared types for graph-builder indexing helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RepositoryParseSnapshot:
    """In-memory parsed representation for one repository."""

    repo_path: str
    file_count: int
    imports_map: dict[str, list[str]]
    file_data: list[dict[str, Any]]
