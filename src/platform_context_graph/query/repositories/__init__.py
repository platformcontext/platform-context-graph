"""Public repository query entrypoints."""

from __future__ import annotations

from typing import Any

from ...observability import trace_query
from .common import (
    canonical_repository_ref as _canonical_repository_ref,
    canonical_repository_identifier as _canonical_repository_id,
    get_db_manager,
    repository_metadata_from_row as _repository_metadata_from_row,
    repository_projection as _repository_projection,
    resolve_repository as _resolve_repository,
)
from .coverage_data import (
    get_repository_coverage_payload,
    list_repository_coverage_payload,
)
from .content_enrichment import enrich_repository_context
from .context_data import build_repository_context
from .listing import list_repositories_rows
from .stats_data import build_repository_stats
from ..story_documentation import (
    build_graph_context_evidence,
    collect_documentation_evidence,
)
from ..story import build_repository_story_response

__all__ = [
    "_canonical_repository_id",
    "list_repositories",
    "get_repository_context",
    "get_repository_story",
    "get_repository_stats",
    "get_repository_coverage",
    "list_repository_coverage",
]

_get_db_manager = get_db_manager


def list_repositories(database: Any) -> dict[str, Any]:
    """List repositories known to the graph using remote-first identity.

    Args:
        database: Query-layer database dependency.

    Returns:
        Repository listing response payload.
    """

    with trace_query("list_repositories"):
        return {"repositories": list_repositories_rows(database)}


def get_repository_context(database: Any, *, repo_id: str) -> dict[str, Any]:
    """Return repository context for a canonical repository identifier.

    Args:
        database: Query-layer database dependency.
        repo_id: Canonical repository identifier.

    Returns:
        Repository context payload or an error dictionary.
    """

    with trace_query("repository_context"):
        with get_db_manager(database).get_driver().session() as session:
            context = build_repository_context(session, repo_id)
        if "error" in context:
            return context
        return enrich_repository_context(database, context)


def get_repository_story(database: Any, *, repo_id: str) -> dict[str, Any]:
    """Return a structured story response for a repository."""

    with trace_query("repository_story"):
        context = get_repository_context(database, repo_id=repo_id)
        if "error" in context:
            return context
        repository = dict(context.get("repository") or {})
        repo_refs = [
            repository,
            *list(context.get("deploys_from") or []),
            *list(context.get("discovers_config_in") or []),
            *list(context.get("provisioned_by") or []),
        ]
        documentation_evidence = collect_documentation_evidence(
            database,
            repo_refs=repo_refs,
            subject_names=[str(repository.get("name") or repo_id)],
        )
        documentation_evidence["graph_context"] = build_graph_context_evidence(
            entrypoints=list(context.get("hostnames") or []),
            delivery_paths=list(context.get("delivery_paths") or []),
            deploys_from=list(context.get("deploys_from") or []),
            dependencies=[
                {"name": row.get("repository") or row.get("name")}
                for row in list(context.get("consumer_repositories") or [])
                if isinstance(row, dict)
            ],
            api_surface=dict(context.get("api_surface") or {}),
        )
        context["documentation_evidence"] = documentation_evidence
        return build_repository_story_response(context)


def get_repository_stats(
    database: Any, *, repo_id: str | None = None
) -> dict[str, Any]:
    """Return repository or graph-wide statistics.

    Args:
        database: Query-layer database dependency.
        repo_id: Optional repository identifier to scope the statistics.

    Returns:
        Statistics response payload.
    """

    with trace_query("repository_stats"):
        with get_db_manager(database).get_driver().session() as session:
            return build_repository_stats(session, repo_id)


def get_repository_coverage(
    database: Any, *, repo_id: str, run_id: str | None = None
) -> dict[str, Any]:
    """Return durable repository coverage for one canonical repository ID."""

    del database
    with trace_query("repository_coverage"):
        return get_repository_coverage_payload(repo_id=repo_id, run_id=run_id)


def list_repository_coverage(
    database: Any,
    *,
    run_id: str | None = None,
    only_incomplete: bool = False,
    statuses: list[str] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return durable repository coverage rows for one run or across runs."""

    del database
    with trace_query("repository_coverage_list"):
        return list_repository_coverage_payload(
            run_id=run_id,
            only_incomplete=only_incomplete,
            statuses=statuses,
            limit=limit,
        )
