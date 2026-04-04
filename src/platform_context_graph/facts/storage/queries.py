"""Partitioned and paginated fact query helpers.

Provides streaming read methods for the PostgreSQL fact store that load
facts by type and in batches.  These methods keep peak Python memory
proportional to one batch (~2 000 rows) rather than the full result set,
preventing OOM on repositories with hundreds of thousands of facts.

Typical usage::

    from platform_context_graph.facts.storage.queries import (
        list_facts_by_type,
        iter_fact_batches,
        count_facts,
    )

    file_facts = list_facts_by_type(
        cursor_factory=store._cursor,
        record_operation=store._record_operation,
        repository_id="repo:my-app",
        source_run_id="run-42",
        fact_type="FileObserved",
    )

    for batch in iter_fact_batches(...):
        process(batch)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Generator

from .models import FactRecordRow

# ---------------------------------------------------------------------------
# SQL fragments shared across query helpers
# ---------------------------------------------------------------------------

_FACT_COLUMNS = """
    fact_id,
    fact_type,
    repository_id,
    checkout_path,
    relative_path,
    source_system,
    source_run_id,
    source_snapshot_id,
    payload,
    observed_at,
    ingested_at,
    provenance
"""


def _rows_to_records(rows: list[dict[str, Any]]) -> list[FactRecordRow]:
    """Convert raw dict rows into frozen ``FactRecordRow`` dataclasses.

    Args:
        rows: List of column-keyed dictionaries returned by ``cursor.fetchall()``.

    Returns:
        Corresponding list of ``FactRecordRow`` instances.
    """
    return [FactRecordRow(**row) for row in rows]


# ---------------------------------------------------------------------------
# Public query helpers
# ---------------------------------------------------------------------------


def list_facts_by_type(
    *,
    cursor_factory: Callable[..., Any],
    record_operation: Callable[..., Any],
    repository_id: str,
    source_run_id: str,
    fact_type: str,
) -> list[FactRecordRow]:
    """Return fact records for one repository/run/type triple.

    Filters at the SQL level using the composite index
    ``fact_records_repo_run_type_idx(repository_id, source_run_id, fact_type)``
    so Postgres never reads rows outside the requested type.

    Args:
        cursor_factory: Context manager that yields a ``psycopg`` dict-row cursor.
        record_operation: Wrapper that adds OTEL spans and metrics around the query.
        repository_id: Canonical repository identifier (e.g. ``"repository:my-app"``).
        source_run_id: The fact run that produced these records.
        fact_type: One of ``"RepositoryObserved"``, ``"FileObserved"``,
            or ``"ParsedEntityObserved"``.

    Returns:
        All matching fact records ordered by ``(relative_path NULLS FIRST, fact_id)``.
    """
    rows = record_operation(
        operation="list_facts_by_type",
        callback=lambda: _fetchall(
            cursor_factory,
            f"""
            SELECT {_FACT_COLUMNS}
            FROM fact_records
            WHERE repository_id = %(repository_id)s
              AND source_run_id = %(source_run_id)s
              AND fact_type = %(fact_type)s
            ORDER BY relative_path NULLS FIRST, fact_id
            """,
            {
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "fact_type": fact_type,
            },
        ),
    )
    return _rows_to_records(rows)


def iter_fact_batches(
    *,
    cursor_factory: Callable[..., Any],
    record_operation: Callable[..., Any],
    repository_id: str,
    source_run_id: str,
    fact_type: str,
    batch_size: int = 2000,
) -> list[list[FactRecordRow]]:
    """Load fact records in batches using keyset pagination.

    Returns a list of batches (each a ``list[FactRecordRow]``) rather than
    holding a database cursor open across the full projection pipeline.
    Each batch is bounded by ``batch_size`` rows, keeping peak Python memory
    proportional to one batch rather than the entire result set.

    Keyset pagination uses ``(relative_path, fact_id)`` as the seek cursor,
    which is O(log n) per page via the composite index — unlike LIMIT/OFFSET
    which is O(n) for deep pages.

    Args:
        cursor_factory: Context manager that yields a ``psycopg`` dict-row cursor.
        record_operation: Wrapper that adds OTEL spans and metrics around the query.
        repository_id: Canonical repository identifier.
        source_run_id: The fact run that produced these records.
        fact_type: Fact type to paginate (typically ``"ParsedEntityObserved"``).
        batch_size: Maximum rows per batch.  Defaults to 2 000, which at
            ~450 bytes/row keeps each batch under ~1 MB of Python heap.

    Returns:
        List of batches, each containing up to ``batch_size`` fact records.
        Empty list if no matching records exist.
    """
    batches: list[list[FactRecordRow]] = []
    last_path: str | None = None
    last_id: str | None = None

    while True:
        if last_path is None and last_id is None:
            rows = record_operation(
                operation="iter_fact_batches",
                callback=lambda: _fetchall(
                    cursor_factory,
                    f"""
                    SELECT {_FACT_COLUMNS}
                    FROM fact_records
                    WHERE repository_id = %(repository_id)s
                      AND source_run_id = %(source_run_id)s
                      AND fact_type = %(fact_type)s
                    ORDER BY relative_path NULLS FIRST, fact_id
                    LIMIT %(batch_size)s
                    """,
                    {
                        "repository_id": repository_id,
                        "source_run_id": source_run_id,
                        "fact_type": fact_type,
                        "batch_size": batch_size,
                    },
                ),
            )
        else:
            # Keyset pagination: skip past already-seen rows.
            # Handle NULL relative_path (sorts first) separately.
            _lp = last_path
            _li = last_id
            rows = record_operation(
                operation="iter_fact_batches",
                callback=lambda: _fetchall(
                    cursor_factory,
                    f"""
                    SELECT {_FACT_COLUMNS}
                    FROM fact_records
                    WHERE repository_id = %(repository_id)s
                      AND source_run_id = %(source_run_id)s
                      AND fact_type = %(fact_type)s
                      AND (
                          (relative_path IS NOT NULL AND (relative_path, fact_id) > (%(last_path)s, %(last_id)s))
                          OR (relative_path IS NULL AND %(last_path)s IS NULL AND fact_id > %(last_id)s)
                          OR (relative_path IS NOT NULL AND %(last_path)s IS NULL)
                      )
                    ORDER BY relative_path NULLS FIRST, fact_id
                    LIMIT %(batch_size)s
                    """,
                    {
                        "repository_id": repository_id,
                        "source_run_id": source_run_id,
                        "fact_type": fact_type,
                        "last_path": _lp,
                        "last_id": _li,
                        "batch_size": batch_size,
                    },
                ),
            )

        if not rows:
            break

        batch = _rows_to_records(rows)
        batches.append(batch)
        last_row = batch[-1]
        last_path = last_row.relative_path
        last_id = last_row.fact_id

        if len(rows) < batch_size:
            break

    return batches


def count_facts(
    *,
    cursor_factory: Callable[..., Any],
    record_operation: Callable[..., Any],
    repository_id: str,
    source_run_id: str,
) -> int:
    """Return the total fact count for one repository/run pair.

    Uses a simple ``COUNT(*)`` which Postgres resolves via an index-only
    scan on ``fact_records_repository_run_idx``.

    Args:
        cursor_factory: Context manager that yields a ``psycopg`` dict-row cursor.
        record_operation: Wrapper that adds OTEL spans and metrics around the query.
        repository_id: Canonical repository identifier.
        source_run_id: The fact run that produced these records.

    Returns:
        Total number of fact records for the repository/run pair.
    """
    rows = record_operation(
        operation="count_facts",
        callback=lambda: _fetchall(
            cursor_factory,
            """
            SELECT COUNT(*) AS cnt
            FROM fact_records
            WHERE repository_id = %(repository_id)s
              AND source_run_id = %(source_run_id)s
            """,
            {
                "repository_id": repository_id,
                "source_run_id": source_run_id,
            },
        ),
    )
    return int(rows[0]["cnt"]) if rows else 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetchall(
    cursor_factory: Callable[..., Any],
    query: str,
    params: dict[str, Any],
) -> list[dict[str, Any]]:
    """Execute a read query and return all rows as dicts.

    Args:
        cursor_factory: Context manager yielding a ``psycopg`` dict-row cursor.
        query: SQL query string with ``%(name)s`` placeholders.
        params: Parameter dict for the query.

    Returns:
        List of column-keyed dictionaries.
    """
    with cursor_factory() as cursor:
        cursor.execute(query, params)
        return list(cursor.fetchall())
