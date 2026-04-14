"""FastAPI dependency providers for the HTTP query surface.

The query layer has migrated to the Go API. This module provides stub
dependencies that return HTTP 503 for all query endpoints.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException

from platform_context_graph.core import get_database_manager

__all__ = [
    "QueryServices",
    "get_database",
    "get_query_services",
]


class _MigratedQueryModule:
    """Stub query module that raises HTTP 503 for all attribute access."""

    def __getattr__(self, name: str) -> Any:
        """Raise HTTP 503 when any query function is called."""
        raise HTTPException(
            status_code=503,
            detail="Query layer has migrated to Go API. Use the Go query endpoints.",
        )


@dataclass(frozen=True, slots=True)
class QueryServices:
    """Bundle the query modules exposed to HTTP routers.

    All query modules now raise HTTP 503 as the query layer has migrated to Go.

    Attributes:
        database: Database manager instance resolved for the current request.
        code: Migrated to Go API.
        compare: Migrated to Go API.
        content: Migrated to Go API.
        context: Migrated to Go API.
        entity_resolution: Migrated to Go API.
        investigation: Migrated to Go API.
        impact: Migrated to Go API.
        infra: Migrated to Go API.
        repositories: Migrated to Go API.
        status: Migrated to Go API.
    """

    database: Any
    code: Any = None
    compare: Any = None
    content: Any = None
    context: Any = None
    entity_resolution: Any = None
    investigation: Any = None
    impact: Any = None
    infra: Any = None
    repositories: Any = None
    status: Any = None

    def __post_init__(self) -> None:
        """Initialize stub query modules after dataclass initialization."""
        stub = _MigratedQueryModule()
        object.__setattr__(self, "code", stub)
        object.__setattr__(self, "compare", stub)
        object.__setattr__(self, "content", stub)
        object.__setattr__(self, "context", stub)
        object.__setattr__(self, "entity_resolution", stub)
        object.__setattr__(self, "investigation", stub)
        object.__setattr__(self, "impact", stub)
        object.__setattr__(self, "infra", stub)
        object.__setattr__(self, "repositories", stub)
        object.__setattr__(self, "status", stub)


def get_database() -> Any:
    """Resolve the shared database manager dependency."""
    return get_database_manager()


def get_query_services(database: Any = Depends(get_database)) -> QueryServices:
    """Construct the query-service bundle for a request.

    Args:
        database: Database manager resolved by FastAPI dependency injection.

    Returns:
        Query service bundle with stub modules that raise HTTP 503.
    """
    return QueryServices(database=database)
