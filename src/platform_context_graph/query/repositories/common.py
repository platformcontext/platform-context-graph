"""Shared helpers for repository query modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...repository_identity import canonical_repository_id, repository_metadata


def get_db_manager(database: Any) -> Any:
    """Normalize the database dependency to a driver-capable manager.

    Args:
        database: Query-layer database dependency or wrapper object.

    Returns:
        An object that exposes ``get_driver()``.
    """

    if callable(getattr(database, "get_driver", None)):
        return database

    db_manager = getattr(database, "db_manager", None)
    if callable(getattr(db_manager, "get_driver", None)):
        return db_manager

    return database


def canonical_repository_identifier(
    repo_path: str | None = None,
    *,
    remote_url: str | None = None,
    local_path: str | None = None,
) -> str:
    """Build the canonical repository identifier used by the query layer.

    Args:
        repo_path: Legacy repository path fallback.
        remote_url: Normalized or raw remote URL.
        local_path: Server-local checkout path.

    Returns:
        Canonical repository identifier.
    """

    return canonical_repository_id(
        remote_url=remote_url,
        local_path=local_path or repo_path,
    )


def repository_metadata_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Project repository metadata from a query result row.

    Args:
        row: Row returned by a repository query.

    Returns:
        Repository metadata in the remote-first public shape.
    """

    local_path = row.get("local_path") or row.get("path")
    return repository_metadata(
        name=row.get("name") or (Path(local_path).name if local_path else "repository"),
        local_path=local_path,
        remote_url=row.get("remote_url"),
        repo_slug=row.get("repo_slug"),
        has_remote=row.get("has_remote"),
    )


def repository_projection(
    alias: str = "r",
    *,
    local_path_param: str = "local_path_key",
    remote_url_param: str = "remote_url_key",
    repo_slug_param: str = "repo_slug_key",
    has_remote_param: str = "has_remote_key",
) -> str:
    """Return the standard Cypher projection for repository metadata.

    Args:
        alias: Cypher variable name for the repository node.

    Returns:
        Projection clause fragment reused by repository queries.
    """

    return (
        f"{alias}.id as id, "
        f"{alias}.name as name, "
        f"{alias}.path as path, "
        f"coalesce({alias}[${local_path_param}], {alias}.path) as local_path, "
        f"{alias}[${remote_url_param}] as remote_url, "
        f"{alias}[${repo_slug_param}] as repo_slug, "
        f"coalesce({alias}[${has_remote_param}], false) as has_remote"
    )


def canonical_repository_ref(row: dict[str, Any]) -> dict[str, Any]:
    """Build the public repository reference shape for responses.

    Args:
        row: Repository query result row.

    Returns:
        Canonical repository reference dictionary.
    """

    metadata = repository_metadata_from_row(row)
    return {
        "id": metadata["id"],
        "type": "repository",
        "name": metadata["name"],
        "repo_slug": metadata["repo_slug"],
        "remote_url": metadata["remote_url"],
        "local_path": metadata["local_path"],
        "has_remote": metadata["has_remote"],
    }


def graph_relationship_types(session: Any) -> set[str]:
    """Return the available graph relationship types for the current session."""

    rows = session.run("CALL db.relationshipTypes()").data()
    relationship_types: set[str] = set()
    for row in rows:
        for value in row.values():
            if isinstance(value, str) and value:
                relationship_types.add(value)
    return relationship_types


def resolve_repository(session: Any, repo_id: str) -> dict[str, Any] | None:
    """Resolve one canonical repository identifier against the indexed graph.

    Args:
        session: Database session used for lookup.
        repo_id: Canonical repository identifier.

    Returns:
        Repository row enriched with canonical metadata, or ``None`` when no
        repository matches.
    """

    repos = session.run(
        f"""
            MATCH (r:Repository)
            RETURN {repository_projection()}
            ORDER BY r.name
            """,
        local_path_key="local_path",
        remote_url_key="remote_url",
        repo_slug_key="repo_slug",
        has_remote_key="has_remote",
    ).data()

    for repo in repos:
        metadata = repository_metadata_from_row(repo)
        stored_id = repo.get("id") or metadata["id"]
        if stored_id == repo_id:
            return {**repo, **metadata, "id": repo.get("id") or metadata["id"]}

    if not repo_id.startswith("repository:"):
        path_candidate = Path(repo_id).expanduser()
        if path_candidate.is_absolute():
            resolved_path = str(path_candidate.resolve())
            for repo in repos:
                metadata = repository_metadata_from_row(repo)
                if (
                    metadata.get("local_path") == resolved_path
                    or repo.get("path") == resolved_path
                ):
                    return {**repo, **metadata, "id": repo.get("id") or metadata["id"]}

        lowered_identifier = repo_id.lower()
        for repo in repos:
            metadata = repository_metadata_from_row(repo)
            candidates = [
                repo.get("name"),
                metadata.get("repo_slug"),
                metadata.get("remote_url"),
                repo.get("path"),
                metadata.get("local_path"),
            ]
            if any(
                isinstance(candidate, str) and candidate.lower() == lowered_identifier
                for candidate in candidates
            ):
                return {**repo, **metadata, "id": repo.get("id") or metadata["id"]}
    return None
