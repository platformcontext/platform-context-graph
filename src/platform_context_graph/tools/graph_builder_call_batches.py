"""Batched CALLS relationship helpers shared by graph builder indexing."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

_CALL_RELATIONSHIP_BATCH_SIZE = 250
_LOW_SIGNAL_JS_FALLBACK_NAMES = frozenset(
    {
        "$",
        "apply",
        "appendChild",
        "attr",
        "call",
        "createElement",
        "css",
        "data",
        "each",
        "exec",
        "extend",
        "find",
        "get",
        "getElementsByTagName",
        "indexOf",
        "insertBefore",
        "join",
        "load",
        "match",
        "on",
        "pop",
        "push",
        "RegExp",
        "removeChild",
        "replace",
        "set",
        "split",
        "splice",
        "substr",
        "test",
    }
)
_KNOWN_PHP_BUILTINS = frozenset(
    {
        "array_merge",
        "count",
        "empty",
        "explode",
        "implode",
        "in_array",
        "is_array",
        "is_bool",
        "is_callable",
        "is_float",
        "is_int",
        "is_null",
        "is_numeric",
        "is_object",
        "is_string",
        "isset",
        "json_decode",
        "json_encode",
        "method_exists",
        "preg_match",
        "preg_replace",
        "sprintf",
        "str_replace",
        "strlen",
        "strpos",
        "strtolower",
        "strtoupper",
        "substr",
        "trim",
    }
)


def _call_resolution_scope() -> str:
    """Return the call resolution scope, reading the env var on each call."""
    return os.environ.get("PCG_CALL_RESOLUTION_SCOPE", "repo").lower()


def create_contextual_call_relationships_batched(
    session: Any,
    rows: list[dict[str, Any]],
) -> dict[str, float | int]:
    """Create contextual call relationships in batched UNWIND passes."""

    repo_scoped = (
        contextual_repo_scoped_batch_query()
        if _call_resolution_scope() == "repo"
        else None
    )
    return create_call_relationships_batched(
        session,
        rows,
        exact_queries=contextual_call_batch_queries(),
        repo_scoped_query=repo_scoped,
        fallback_query=contextual_call_fallback_batch_query(),
    )


def create_file_level_call_relationships_batched(
    session: Any,
    rows: list[dict[str, Any]],
) -> dict[str, float | int]:
    """Create file-level call relationships in batched UNWIND passes."""

    repo_scoped = (
        file_level_repo_scoped_batch_query()
        if _call_resolution_scope() == "repo"
        else None
    )
    return create_call_relationships_batched(
        session,
        rows,
        exact_queries=file_level_call_batch_queries(),
        repo_scoped_query=repo_scoped,
        fallback_query=file_level_call_fallback_batch_query(),
    )


def create_call_relationships_batched(
    session: Any,
    rows: list[dict[str, Any]],
    *,
    exact_queries: tuple[str, ...],
    repo_scoped_query: str | None = None,
    fallback_query: str,
) -> dict[str, float | int]:
    """Create call relationships via exact, repo-scoped, and fallback passes.

    Resolution order:
    1. Exact queries (name + path match).
    2. Repo-scoped query (name + path STARTS WITH repo_path) when provided.
    3. Global fallback (name-only) when ``PCG_FUNCTION_CALL_GLOBAL_FALLBACK``
       is enabled.
    """

    exact_started = time.monotonic()
    remaining_rows = rows
    for query in exact_queries:
        remaining_rows = run_call_batch_query(session, query, remaining_rows)
        if not remaining_rows:
            return call_resolution_metrics(
                rows=rows,
                fallback_rows=0,
                unresolved_rows=[],
                exact_duration=time.monotonic() - exact_started,
                repo_scoped_duration=0.0,
                fallback_duration=0.0,
            )

    exact_duration = time.monotonic() - exact_started

    repo_scoped_duration = 0.0
    if repo_scoped_query and remaining_rows:
        repo_scoped_started = time.monotonic()
        remaining_rows = run_call_batch_query(
            session, repo_scoped_query, remaining_rows
        )
        repo_scoped_duration = time.monotonic() - repo_scoped_started
        if not remaining_rows:
            return call_resolution_metrics(
                rows=rows,
                fallback_rows=0,
                unresolved_rows=[],
                exact_duration=exact_duration,
                repo_scoped_duration=repo_scoped_duration,
                fallback_duration=0.0,
            )

    _global_fallback_enabled = (
        os.environ.get("PCG_FUNCTION_CALL_GLOBAL_FALLBACK", "false").lower() == "true"
    )
    if not _global_fallback_enabled:
        return call_resolution_metrics(
            rows=rows,
            fallback_rows=0,
            unresolved_rows=remaining_rows,
            exact_duration=exact_duration,
            repo_scoped_duration=repo_scoped_duration,
            fallback_duration=0.0,
        )

    fallback_candidates = filter_fallback_candidate_rows(remaining_rows)
    fallback_rows = len(fallback_candidates)
    if not fallback_candidates:
        return call_resolution_metrics(
            rows=rows,
            fallback_rows=0,
            unresolved_rows=[],
            exact_duration=exact_duration,
            repo_scoped_duration=repo_scoped_duration,
            fallback_duration=0.0,
        )
    fallback_started = time.monotonic()
    unresolved_rows = run_call_batch_query(session, fallback_query, fallback_candidates)
    return call_resolution_metrics(
        rows=rows,
        fallback_rows=fallback_rows,
        unresolved_rows=unresolved_rows,
        exact_duration=exact_duration,
        repo_scoped_duration=repo_scoped_duration,
        fallback_duration=time.monotonic() - fallback_started,
    )


def filter_fallback_candidate_rows(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Drop low-signal fallback rows that are unlikely to resolve meaningfully."""

    return [row for row in rows if not should_skip_global_fallback(row)]


def should_skip_global_fallback(row: dict[str, Any]) -> bool:
    """Return whether a global name-only lookup should be skipped for one call."""

    called_name = str(row.get("called_name") or "").strip()
    if not called_name:
        return True
    normalized_name = called_name.lower()
    language = str(row.get("lang") or "").strip().lower()
    if language == "javascript":
        if len(called_name) <= 2:
            return True
        return called_name in _LOW_SIGNAL_JS_FALLBACK_NAMES
    if language == "php":
        return normalized_name in _KNOWN_PHP_BUILTINS
    return False


def call_resolution_metrics(
    *,
    rows: list[dict[str, Any]],
    fallback_rows: int,
    unresolved_rows: list[dict[str, Any]],
    exact_duration: float,
    repo_scoped_duration: float = 0.0,
    fallback_duration: float = 0.0,
) -> dict[str, float | int]:
    """Return a normalized metric payload for one batched call-resolution pass."""

    return {
        "rows": len(rows),
        "fallback_rows": fallback_rows,
        "unmatched_rows": len(unresolved_rows),
        "exact_duration_seconds": exact_duration,
        "repo_scoped_duration_seconds": repo_scoped_duration,
        "fallback_duration_seconds": fallback_duration,
    }


def combine_call_relationship_metrics(
    contextual_metrics: dict[str, float | int],
    file_level_metrics: dict[str, float | int],
) -> dict[str, float | int]:
    """Combine contextual and file-level timing metrics under stable keys."""

    metrics = {
        **{f"contextual_{key}": value for key, value in contextual_metrics.items()},
        **{f"file_level_{key}": value for key, value in file_level_metrics.items()},
    }
    metrics["exact_duration_seconds"] = (
        metrics["contextual_exact_duration_seconds"]
        + metrics["file_level_exact_duration_seconds"]
    )
    metrics["repo_scoped_duration_seconds"] = (
        metrics["contextual_repo_scoped_duration_seconds"]
        + metrics["file_level_repo_scoped_duration_seconds"]
    )
    metrics["fallback_duration_seconds"] = (
        metrics["contextual_fallback_duration_seconds"]
        + metrics["file_level_fallback_duration_seconds"]
    )
    metrics["total_duration_seconds"] = (
        metrics["exact_duration_seconds"]
        + metrics["repo_scoped_duration_seconds"]
        + metrics["fallback_duration_seconds"]
    )
    return metrics


def run_call_batch_query(
    session: Any,
    query: str,
    rows: list[dict[str, Any]],
    *,
    batch_size: int | None = None,
) -> list[dict[str, Any]]:
    """Run one batched call-link query and return the unresolved rows."""

    if not rows:
        return []
    unresolved_rows: list[dict[str, Any]] = []
    effective_batch_size = max(
        1,
        batch_size if batch_size is not None else _CALL_RELATIONSHIP_BATCH_SIZE,
    )
    for start in range(0, len(rows), effective_batch_size):
        chunk = rows[start : start + effective_batch_size]
        try:
            result = session.run(query, {"rows": chunk})
            row = result.single()
        except Exception:
            logger.warning(
                "Neo4j query failed during call resolution",
                exc_info=True,
                extra={"batch_size": len(chunk)},
            )
            unresolved_rows.extend(chunk)
            continue
        matched_row_ids = set()
        if row is not None:
            matched_row_ids.update(row.get("matched_row_ids") or [])
        if not matched_row_ids:
            unresolved_rows.extend(chunk)
            continue
        unresolved_rows.extend(
            item for item in chunk if item.get("row_id") not in matched_row_ids
        )
    return unresolved_rows


def contextual_call_batch_queries() -> tuple[str, ...]:
    """Return ordered batched query attempts for contextual call resolution."""

    return (
        """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller_function:Function {name: row.caller_name, path: row.caller_file_path})
        OPTIONAL MATCH (caller_class:Class {name: row.caller_name, path: row.caller_file_path})
        WITH row, COALESCE(caller_function, caller_class) AS caller
        OPTIONAL MATCH (called_function:Function {name: row.called_name, path: row.called_file_path})
        OPTIONAL MATCH (called_class:Class {name: row.called_name, path: row.called_file_path})
        OPTIONAL MATCH (called_class)-[:CONTAINS]->(init:Function)
        WITH row, caller, called_function, called_class,
             CASE WHEN init.name IN ["__init__", "constructor"] THEN init END AS init
        WITH row, caller, COALESCE(called_function, init, called_class) AS final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(final_target)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
        """,
    )


def contextual_call_fallback_batch_query() -> str:
    """Return the batched fallback query for contextual call resolution."""

    return """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller_function:Function {name: row.caller_name, path: row.caller_file_path})
        OPTIONAL MATCH (caller_class:Class {name: row.caller_name, path: row.caller_file_path})
        WITH row, COALESCE(caller_function, caller_class) AS caller
        OPTIONAL MATCH (called:Function {name: row.called_name})
          WHERE called.lang IS NULL OR called.lang IN row.compatible_langs
        WITH row, caller, called
        WHERE caller IS NOT NULL AND called IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(called)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
    """


def contextual_repo_scoped_batch_query() -> str:
    """Return the repo-scoped query for contextual call resolution.

    Matches called functions by name within the same repository (path prefix)
    rather than requiring an exact file-path match. Sits between the exact
    queries and the global fallback in the resolution chain.
    """

    return """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller_function:Function {name: row.caller_name, path: row.caller_file_path})
        OPTIONAL MATCH (caller_class:Class {name: row.caller_name, path: row.caller_file_path})
        WITH row, COALESCE(caller_function, caller_class) AS caller
        OPTIONAL MATCH (called_function:Function {name: row.called_name})
          WHERE called_function.path STARTS WITH row.repo_path
            AND (called_function.lang IS NULL OR called_function.lang IN row.compatible_langs)
        OPTIONAL MATCH (called_class:Class {name: row.called_name})
          WHERE called_class.path STARTS WITH row.repo_path
            AND (called_class.lang IS NULL OR called_class.lang IN row.compatible_langs)
        OPTIONAL MATCH (called_class)-[:CONTAINS]->(init:Function)
        WITH row, caller, called_function, called_class,
             CASE WHEN init.name IN ["__init__", "constructor"] THEN init END AS init
        WITH row, caller, COALESCE(called_function, init, called_class) AS final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(final_target)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
    """


def file_level_call_batch_queries() -> tuple[str, ...]:
    """Return ordered batched query attempts for file-level call resolution."""

    return (
        """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller:File {path: row.caller_file_path})
        OPTIONAL MATCH (called_function:Function {name: row.called_name, path: row.called_file_path})
        OPTIONAL MATCH (called_class:Class {name: row.called_name, path: row.called_file_path})
        OPTIONAL MATCH (called_class)-[:CONTAINS]->(init:Function)
        WITH row, caller, called_function, called_class,
             CASE WHEN init.name IN ["__init__", "constructor"] THEN init END AS init
        WITH row, caller, COALESCE(called_function, init, called_class) AS final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(final_target)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
        """,
    )


def file_level_call_fallback_batch_query() -> str:
    """Return the batched fallback query for file-level call resolution."""

    return """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller:File {path: row.caller_file_path})
        OPTIONAL MATCH (called:Function {name: row.called_name})
          WHERE called.lang IS NULL OR called.lang IN row.compatible_langs
        WITH row, caller, called
        WHERE caller IS NOT NULL AND called IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(called)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
    """


def file_level_repo_scoped_batch_query() -> str:
    """Return the repo-scoped query for file-level call resolution.

    Matches called functions by name within the same repository (path prefix)
    rather than requiring an exact file-path match. Sits between the exact
    queries and the global fallback in the resolution chain.
    """

    return """
        UNWIND $rows AS row
        OPTIONAL MATCH (caller:File {path: row.caller_file_path})
        OPTIONAL MATCH (called_function:Function {name: row.called_name})
          WHERE called_function.path STARTS WITH row.repo_path
            AND (called_function.lang IS NULL OR called_function.lang IN row.compatible_langs)
        OPTIONAL MATCH (called_class:Class {name: row.called_name})
          WHERE called_class.path STARTS WITH row.repo_path
            AND (called_class.lang IS NULL OR called_class.lang IN row.compatible_langs)
        OPTIONAL MATCH (called_class)-[:CONTAINS]->(init:Function)
        WITH row, caller, called_function, called_class,
             CASE WHEN init.name IN ["__init__", "constructor"] THEN init END AS init
        WITH row, caller, COALESCE(called_function, init, called_class) AS final_target
        WHERE caller IS NOT NULL AND final_target IS NOT NULL
        MERGE (caller)-[:CALLS {line_number: row.line_number, args: row.args, full_call_name: row.full_call_name}]->(final_target)
        RETURN collect(DISTINCT row.row_id) AS matched_row_ids
    """
