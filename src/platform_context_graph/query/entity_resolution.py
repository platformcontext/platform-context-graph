"""Entity-resolution queries for canonical PCG entity identifiers."""

from __future__ import annotations

from typing import Any, Sequence

from ..domain import (
    EntityType,
    WorkloadKind,
    normalize_entity_type,
    normalize_workload_kind,
)
from ..observability import trace_query
from ..repository_identity import repository_metadata
from .entity_resolution_database import db_content_entities, db_workload_entities
from .entity_resolution_support import (
    build_match,
    entity_matches_filters,
    fixture_matches,
    load_fixture_graph,
    score_match,
)
from .repositories import _repository_projection

__all__ = ["resolve_entity"]


def _normalize_types(values: Sequence[EntityType | str] | None) -> set[EntityType]:
    """Normalize requested entity types into enum values."""

    return {normalize_entity_type(value) for value in values or []}


def _normalize_kinds(values: Sequence[WorkloadKind | str] | None) -> set[WorkloadKind]:
    """Normalize requested workload kinds into enum values."""

    return {normalize_workload_kind(value) for value in values or []}


def _db_repository_matches(
    database: Any,
    *,
    query: str,
    allowed_types: set[EntityType],
    exact: bool,
    repo_id: str | None,
    limit: int,
) -> dict[str, Any]:
    """Resolve repository entities against the live database backend."""
    if allowed_types and EntityType.repository not in allowed_types:
        return {"matches": []}

    driver = database.get_driver()
    with driver.session() as session:
        repos = session.run(
            f"""
            MATCH (r:Repository)
            RETURN {_repository_projection()}
            ORDER BY r.name
        """,
            local_path_key="local_path",
            remote_url_key="remote_url",
            repo_slug_key="repo_slug",
            has_remote_key="has_remote",
        ).data()

    matches: list[dict[str, Any]] = []
    for repo in repos:
        metadata = repository_metadata(
            name=repo["name"],
            local_path=repo.get("local_path") or repo.get("path"),
            remote_url=repo.get("remote_url"),
            repo_slug=repo.get("repo_slug"),
            has_remote=repo.get("has_remote"),
        )
        entity = {
            "id": repo.get("id") or metadata["id"],
            "type": "repository",
            "name": metadata["name"],
            "local_path": metadata["local_path"],
            "repo_slug": metadata["repo_slug"],
            "remote_url": metadata["remote_url"],
            "has_remote": metadata["has_remote"],
            "aliases": [
                value
                for value in (
                    metadata["name"],
                    metadata["repo_slug"],
                    metadata["remote_url"],
                    metadata["local_path"],
                )
                if value
            ],
        }
        if repo_id and entity["id"] != repo_id:
            continue
        score, source, matched_value = score_match(entity, query=query, exact=exact)
        if score <= 0:
            continue
        matches.append(
            build_match(
                entity,
                score=score,
                source=source,
                matched_value=matched_value,
                graph=None,
                query=query,
            )
        )
    matches.sort(key=lambda item: (-item["score"], item["ref"]["id"]))
    return {"matches": matches[:limit]}


def _db_workload_matches(
    database: Any,
    *,
    query: str,
    allowed_types: set[EntityType],
    allowed_kinds: set[WorkloadKind],
    environment: str | None,
    repo_id: str | None,
    exact: bool,
    limit: int,
) -> dict[str, Any]:
    """Resolve workload-shaped entities against the live database backend."""
    if allowed_types and not allowed_types.intersection(
        {EntityType.workload, EntityType.workload_instance}
    ):
        return {"matches": []}

    matches: list[dict[str, Any]] = []
    for entity in db_workload_entities(database, query=query, repo_id=repo_id):
        if not entity_matches_filters(
            entity,
            allowed_types=allowed_types,
            allowed_kinds=allowed_kinds,
            environment=environment,
            repo_id=repo_id,
        ):
            continue
        score, source, matched_value = score_match(entity, query=query, exact=exact)
        if score <= 0:
            continue
        matches.append(
            build_match(
                entity,
                score=score,
                source=source,
                matched_value=matched_value,
                graph=None,
                query=query,
            )
        )
    matches.sort(key=lambda item: (-item["score"], item["ref"]["id"]))
    return {"matches": matches[:limit]}


def _db_content_entity_matches(
    database: Any,
    *,
    query: str,
    allowed_types: set[EntityType],
    repo_id: str | None,
    exact: bool,
    limit: int,
) -> dict[str, Any]:
    """Resolve SQL-backed content entities against the live database backend."""

    if allowed_types and EntityType.content_entity not in allowed_types:
        return {"matches": []}

    matches: list[dict[str, Any]] = []
    for entity in db_content_entities(database, query=query, repo_id=repo_id):
        if not entity_matches_filters(
            entity,
            allowed_types=allowed_types,
            allowed_kinds=set(),
            environment=None,
            repo_id=repo_id,
        ):
            continue
        score, source, matched_value = score_match(entity, query=query, exact=exact)
        if score <= 0:
            continue
        matches.append(
            build_match(
                entity,
                score=score,
                source=source,
                matched_value=matched_value,
                graph=None,
                query=query,
            )
        )
    matches.sort(key=lambda item: (-item["score"], item["ref"]["id"]))
    return {"matches": matches[:limit]}


def resolve_entity(
    database: Any,
    *,
    query: str,
    types: Sequence[EntityType | str] | None = None,
    kinds: Sequence[WorkloadKind | str] | None = None,
    environment: str | None = None,
    repo_id: str | None = None,
    exact: bool = False,
    limit: int = 10,
) -> dict[str, Any]:
    """Resolve a user query to canonical entities.

    Args:
        database: Live database manager or fixture graph input.
        query: User-supplied query text.
        types: Optional entity-type filter.
        kinds: Optional workload-kind filter.
        environment: Optional environment filter.
        repo_id: Optional canonical repository identifier used to scope results.
        exact: Whether to require exact term matches.
        limit: Maximum number of matches to return.

    Returns:
        Ranked entity-resolution matches.
    """
    with trace_query("resolve_entity"):
        allowed_types = _normalize_types(types)
        allowed_kinds = _normalize_kinds(kinds)
        fixture_graph = load_fixture_graph(database)
        if fixture_graph is not None:
            return fixture_matches(
                fixture_graph,
                query=query,
                allowed_types=allowed_types,
                allowed_kinds=allowed_kinds,
                environment=environment,
                repo_id=repo_id,
                exact=exact,
                limit=limit,
            )
        if callable(getattr(database, "get_driver", None)):
            repo_matches = _db_repository_matches(
                database,
                query=query,
                allowed_types=allowed_types,
                exact=exact,
                repo_id=repo_id,
                limit=limit,
            )
            workload_matches = _db_workload_matches(
                database,
                query=query,
                allowed_types=allowed_types,
                allowed_kinds=allowed_kinds,
                environment=environment,
                repo_id=repo_id,
                exact=exact,
                limit=limit,
            )
            content_entity_matches = _db_content_entity_matches(
                database,
                query=query,
                allowed_types=allowed_types,
                repo_id=repo_id,
                exact=exact,
                limit=limit,
            )
            matches = (
                repo_matches["matches"]
                + workload_matches["matches"]
                + content_entity_matches["matches"]
            )
            matches.sort(key=lambda item: (-item["score"], item["ref"]["id"]))
            return {"matches": matches[:limit]}
        return {"matches": []}
