"""FastAPI dependency providers for the HTTP query surface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import Depends

from platform_context_graph.core import get_database_manager
from platform_context_graph.query import (
    code as code_queries,
    compare as compare_queries,
    content as content_queries,
    context as context_queries,
    entity_resolution as entity_resolution_queries,
    investigation as investigation_queries,
    impact as impact_queries,
    infra as infra_queries,
    repositories as repository_queries,
    status as status_queries,
)

__all__ = [
    "QueryServices",
    "get_database",
    "get_query_services",
]


@dataclass(frozen=True, slots=True)
class QueryServices:
    """Bundle the query modules exposed to HTTP routers.

    Attributes:
        database: Database manager instance resolved for the current request.
        code: Code-query module.
        compare: Environment comparison query module.
        content: Content retrieval and search query module.
        context: Entity and workload context query module.
        entity_resolution: Entity resolution query module.
        investigation: Investigation query module.
        impact: Trace and blast-radius query module.
        infra: Infrastructure query module.
        repositories: Repository query module.
        status: Runtime ingester status query module.
    """

    database: Any
    code: Any = code_queries
    compare: Any = compare_queries
    content: Any = content_queries
    context: Any = context_queries
    entity_resolution: Any = entity_resolution_queries
    investigation: Any = investigation_queries
    impact: Any = impact_queries
    infra: Any = infra_queries
    repositories: Any = repository_queries
    status: Any = status_queries


def get_database() -> Any:
    """Resolve the shared database manager dependency."""
    return get_database_manager()


def get_query_services(database: Any = Depends(get_database)) -> QueryServices:
    """Construct the query-service bundle for a request.

    Args:
        database: Database manager resolved by FastAPI dependency injection.

    Returns:
        Query service bundle used by the API routers.
    """
    return QueryServices(database=database)
