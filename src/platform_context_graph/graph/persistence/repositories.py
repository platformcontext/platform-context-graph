"""Shared persistence helpers for repository and file graph updates."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ...cli.config_manager import get_config_value
from ...content.ingest import repository_metadata_from_row
from ...core.records import record_to_dict
from ...utils.debug_log import emit_log_call
from .directories import (
    collect_directory_chain_rows as _collect_directory_chain_rows,
    flush_directory_chain_rows as _flush_directory_chain_rows,
    merge_directory_chain,
)


def _consume_write_result(result: Any) -> None:
    """Eagerly consume Neo4j write results to release transaction buffers."""

    consume = getattr(result, "consume", None)
    if callable(consume):
        consume()


def _run_write_query(tx_or_session: Any, query: str, /, **parameters: Any) -> None:
    """Execute one write query and eagerly consume its result when supported."""

    _consume_write_result(tx_or_session.run(query, parameters=parameters))


def _bounded_positive_int_config(name: str, default: int, *, maximum: int) -> int:
    """Return a bounded positive integer from config with a safe fallback."""

    raw_value = os.getenv(name)
    if raw_value is None:
        raw_value = get_config_value(name)
    if raw_value is None or not str(raw_value).strip():
        return default
    try:
        return max(1, min(int(raw_value), maximum))
    except ValueError:
        return default


def _relative_path_with_fallback(
    file_path_obj: Path,
    repo_path_obj: Path,
    *,
    warning_logger_fn: Any | None = None,
    operation: str,
) -> Path:
    """Return a repo-relative path or fall back to the basename with a warning."""

    try:
        return file_path_obj.relative_to(repo_path_obj)
    except ValueError as exc:
        fallback = Path(file_path_obj.name)
        emit_log_call(
            warning_logger_fn,
            (
                f"Relative path fallback during {operation}: "
                f"file {file_path_obj} is outside repository root {repo_path_obj}; "
                f"using basename {fallback}"
            ),
            event_name="graph.path.relative_path_fallback",
            extra_keys={
                "file_path": str(file_path_obj),
                "repo_path": str(repo_path_obj),
                "fallback_path": str(fallback),
                "operation": operation,
            },
            exc_info=exc,
        )
        return fallback


def _run_managed_write(session: Any, write_fn: Any) -> None:
    """Execute one write callback with the best available transaction primitive."""

    execute_write = getattr(session, "execute_write", None)
    if callable(execute_write):
        execute_write(write_fn)
        return

    write_transaction = getattr(session, "write_transaction", None)
    if callable(write_transaction):
        write_transaction(write_fn)
        return

    begin = getattr(session, "begin_transaction", None)
    if begin is not None:
        try:
            tx = begin()
            is_explicit = True
        except (AttributeError, NotImplementedError, RuntimeError, TypeError):
            tx = session
            is_explicit = False
    else:
        tx = session
        is_explicit = False
    try:
        write_fn(tx)
        if is_explicit:
            tx.commit()
    except Exception:
        if is_explicit:
            tx.rollback()
        raise


_REPOSITORY_OUTGOING_RECONCILE_TYPES = (
    "CONTAINS",
    "REPO_CONTAINS",
    "DEFINES",
    "DEPENDS_ON",
    "RUNS_ON",
    "PROVISIONS_PLATFORM",
    "DEPLOYS_FROM",
    "DISCOVERS_CONFIG_IN",
    "PROVISIONS_DEPENDENCY_FOR",
)

_REPOSITORY_INCOMING_RECONCILE_TYPES = (
    "CONTAINS",
    "SOURCES_FROM",
    "DEPLOYMENT_SOURCE",
    "DEPENDS_ON",
    "DEPLOYS_FROM",
    "DISCOVERS_CONFIG_IN",
    "PROVISIONS_DEPENDENCY_FOR",
)


def _reconcile_legacy_path_only_repository(
    tx: Any,
    *,
    repo_parameters: dict[str, Any],
) -> None:
    """Merge a legacy path-only repository node into the canonical repository node."""

    base_parameters = {
        "repo_id": repo_parameters["repo_id"],
        "repo_path": repo_parameters["repo_path"],
    }
    for relationship_type in _REPOSITORY_OUTGOING_RECONCILE_TYPES:
        _run_write_query(
            tx,
            f"""
            MATCH (loser:Repository {{path: $repo_path}})
            MATCH (winner:Repository {{id: $repo_id}})
            WHERE elementId(loser) <> elementId(winner)
            OPTIONAL MATCH (loser)-[rel:{relationship_type}]->(target)
            FOREACH (_ IN CASE WHEN rel IS NULL THEN [] ELSE [1] END |
                MERGE (winner)-[merged:{relationship_type}]->(target)
                SET merged += properties(rel)
            )
            """,
            **base_parameters,
        )

    for relationship_type in _REPOSITORY_INCOMING_RECONCILE_TYPES:
        _run_write_query(
            tx,
            f"""
            MATCH (loser:Repository {{path: $repo_path}})
            MATCH (winner:Repository {{id: $repo_id}})
            WHERE elementId(loser) <> elementId(winner)
            OPTIONAL MATCH (source)-[rel:{relationship_type}]->(loser)
            FOREACH (_ IN CASE WHEN rel IS NULL THEN [] ELSE [1] END |
                MERGE (source)-[merged:{relationship_type}]->(winner)
                SET merged += properties(rel)
            )
            """,
            **base_parameters,
        )

    _run_write_query(
        tx,
        """
        MATCH (loser:Repository {path: $repo_path})
        MATCH (winner:Repository {id: $repo_id})
        WHERE elementId(loser) <> elementId(winner)
        DETACH DELETE loser
        """,
        **base_parameters,
    )

    _run_write_query(
        tx,
        """
        MATCH (winner:Repository {id: $repo_id})
        SET winner.path = $repo_path,
            winner.name = $name,
            winner.local_path = $local_path,
            winner.remote_url = $remote_url,
            winner.repo_slug = $repo_slug,
            winner.has_remote = $has_remote,
            winner.is_dependency = $is_dependency
        """,
        **repo_parameters,
    )


def add_repository_to_graph(
    builder: Any,
    repo_path: Path,
    is_dependency: bool,
    *,
    git_remote_for_path_fn: Any,
    repository_metadata_fn: Any,
) -> None:
    """Merge a repository node using the canonical remote-first identity."""

    repo_path_str = str(repo_path.resolve())
    remote_url = git_remote_for_path_fn(repo_path)
    metadata = repository_metadata_fn(
        name=repo_path.name,
        local_path=repo_path_str,
        remote_url=remote_url,
    )
    repo_parameters = {
        "repo_id": metadata["id"],
        "repo_path": repo_path_str,
        "local_path": metadata["local_path"],
        "name": metadata["name"],
        "remote_url": metadata["remote_url"],
        "repo_slug": metadata["repo_slug"],
        "has_remote": metadata["has_remote"],
        "is_dependency": is_dependency,
    }

    with builder.driver.session() as session:

        def _write_repository(tx: Any) -> None:
            """Create, update, or reconcile the Repository node for this path."""

            by_path = record_to_dict(
                tx.run(
                    """
                    MATCH (r:Repository {path: $repo_path})
                    RETURN r.id as existing_id
                    LIMIT 1
                    """,
                    repo_path=repo_path_str,
                ).single()
            )
            by_id = record_to_dict(
                tx.run(
                    """
                    MATCH (r:Repository {id: $repo_id})
                    RETURN r.path as existing_path
                    LIMIT 1
                    """,
                    repo_id=metadata["id"],
                ).single()
            )

            if by_path and by_id and by_id.get("existing_path") != repo_path_str:
                if by_path.get("existing_id") in (None, ""):
                    _reconcile_legacy_path_only_repository(
                        tx,
                        repo_parameters=repo_parameters,
                    )
                    return
                raise RuntimeError(
                    (
                        "Repository identity conflict: "
                        f"path {repo_path_str} is already represented by a "
                        "different Repository node while canonical id "
                        f"{metadata['id']} points to {by_id.get('existing_path')}"
                    )
                )

            if by_path:
                _run_write_query(
                    tx,
                    """
                    MATCH (r:Repository {path: $repo_path})
                    SET r.id = $repo_id,
                        r.name = $name,
                        r.path = $repo_path,
                        r.local_path = $local_path,
                        r.remote_url = $remote_url,
                        r.repo_slug = $repo_slug,
                        r.has_remote = $has_remote,
                        r.is_dependency = $is_dependency
                    """,
                    **repo_parameters,
                )
                return

            _run_write_query(
                tx,
                """
                MERGE (r:Repository {id: $repo_id})
                ON CREATE SET r.path = $repo_path,
                              r.name = $name,
                              r.local_path = $local_path,
                              r.remote_url = $remote_url,
                              r.repo_slug = $repo_slug,
                              r.has_remote = $has_remote,
                              r.is_dependency = $is_dependency
                ON MATCH SET r.path = $repo_path,
                             r.name = $name,
                             r.local_path = $local_path,
                             r.remote_url = $remote_url,
                             r.repo_slug = $repo_slug,
                             r.has_remote = $has_remote,
                             r.is_dependency = $is_dependency
                """,
                **repo_parameters,
            )

        _run_managed_write(session, _write_repository)


def _merge_directory_chain(
    tx: Any,
    file_path_obj: Path,
    repo_path_obj: Path,
    file_path_str: str,
    *,
    warning_logger_fn: Any | None = None,
) -> None:
    """Write the directory chain and file-containment edge within a transaction."""
    merge_directory_chain(
        tx,
        file_path_obj,
        repo_path_obj,
        file_path_str,
        relative_path_with_fallback_fn=_relative_path_with_fallback,
        run_write_query_fn=_run_write_query,
        warning_logger_fn=warning_logger_fn,
    )


def read_repository_metadata(session: Any, repo_path_obj: Path) -> dict[str, Any]:
    """Load canonical repository metadata for a repository path from the graph."""

    try:
        repo_result = session.run(
            """
            MATCH (r:Repository {path: $repo_path})
            RETURN r.id as id,
                   r.name as name,
                   r.path as path,
                   coalesce(r[$local_path_key], r.path) as local_path,
                   r[$remote_url_key] as remote_url,
                   r[$repo_slug_key] as repo_slug,
                   coalesce(r[$has_remote_key], false) as has_remote
            """,
            repo_path=str(repo_path_obj),
            local_path_key="local_path",
            remote_url_key="remote_url",
            repo_slug_key="repo_slug",
            has_remote_key="has_remote",
        ).single()
    except ValueError:
        repo_result = None

    repo_row = record_to_dict(repo_result) if repo_result is not None else None
    return repository_metadata_from_row(row=repo_row, repo_path=repo_path_obj)


def collect_directory_chain_rows(
    file_path_obj: Path,
    repo_path_obj: Path,
    file_path_str: str,
    *,
    warning_logger_fn: Any | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Return directory rows and containment rows without executing queries.

    Returns:
        (dir_rows, containment_rows) where:
        - dir_rows: [{parent_path, parent_label, current_path, part}]
        - containment_rows: [{repo_path, file_path, parent_path, parent_label}]
    """

    return _collect_directory_chain_rows(
        file_path_obj,
        repo_path_obj,
        file_path_str,
        relative_path_with_fallback_fn=_relative_path_with_fallback,
        warning_logger_fn=warning_logger_fn,
    )


def flush_directory_chain_rows(
    tx: Any,
    dir_rows: list[dict[str, str]],
    containment_rows: list[dict[str, str]],
) -> None:
    """Write collected directory chains via UNWIND queries."""
    _flush_directory_chain_rows(
        tx,
        dir_rows,
        containment_rows,
        run_write_query_fn=_run_write_query,
    )


__all__ = [
    "_bounded_positive_int_config",
    "_merge_directory_chain",
    "collect_directory_chain_rows",
    "flush_directory_chain_rows",
    "_relative_path_with_fallback",
    "_run_managed_write",
    "_run_write_query",
    "add_repository_to_graph",
    "read_repository_metadata",
]
