"""Shared query functions for content retrieval and search."""

from __future__ import annotations

from typing import Any

from ..content.state import get_content_service
from ..observability import trace_query

__all__ = [
    "get_entity_content",
    "get_file_content",
    "get_file_lines",
    "search_entity_content",
    "search_file_content",
]


def get_file_content(database: Any, *, repo_id: str, relative_path: str) -> dict[str, Any]:
    """Return file content for one repo-relative path.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.
        relative_path: Repo-relative file path.

    Returns:
        Content response mapping.
    """

    with trace_query("content_file"):
        return get_content_service(database).get_file_content(
            repo_id=repo_id,
            relative_path=relative_path,
        )


def get_file_lines(
    database: Any,
    *,
    repo_id: str,
    relative_path: str,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    """Return one line range for a repo-relative file.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.
        relative_path: Repo-relative file path.
        start_line: First line to include.
        end_line: Last line to include.

    Returns:
        Line-range response mapping.
    """

    with trace_query("content_file_lines"):
        return get_content_service(database).get_file_lines(
            repo_id=repo_id,
            relative_path=relative_path,
            start_line=start_line,
            end_line=end_line,
        )


def get_entity_content(database: Any, *, entity_id: str) -> dict[str, Any]:
    """Return source for one content-bearing entity.

    Args:
        database: Query-layer database dependency.
        entity_id: Canonical content entity identifier.

    Returns:
        Entity-content response mapping.
    """

    with trace_query("content_entity"):
        return get_content_service(database).get_entity_content(entity_id=entity_id)


def search_file_content(
    database: Any,
    *,
    pattern: str,
    repo_ids: list[str] | None = None,
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """Search file content through the content store.

    Args:
        database: Query-layer database dependency.
        pattern: Search pattern.
        repo_ids: Optional repository filters.
        languages: Optional language filters.

    Returns:
        Search response mapping.
    """

    with trace_query("content_file_search"):
        return get_content_service(database).search_file_content(
            pattern=pattern,
            repo_ids=repo_ids,
            languages=languages,
        )


def search_entity_content(
    database: Any,
    *,
    pattern: str,
    entity_types: list[str] | None = None,
    repo_ids: list[str] | None = None,
    languages: list[str] | None = None,
) -> dict[str, Any]:
    """Search entity content through the content store.

    Args:
        database: Query-layer database dependency.
        pattern: Search pattern.
        entity_types: Optional entity-type filters.
        repo_ids: Optional repository filters.
        languages: Optional language filters.

    Returns:
        Search response mapping.
    """

    with trace_query("content_entity_search"):
        return get_content_service(database).search_entity_content(
            pattern=pattern,
            entity_types=entity_types,
            repo_ids=repo_ids,
            languages=languages,
        )
