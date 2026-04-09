"""Helpers for low-contention PostgreSQL schema readiness checks."""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Mapping
from typing import Any


def _row_value(row: Any, key: str) -> str:
    """Return one named value from a DB row or tuple-like object."""

    if isinstance(row, Mapping):
        return str(row[key])
    return str(row[0])


def _fetch_named_values(
    conn: Any,
    *,
    query: str,
    params: dict[str, Any],
    key: str,
) -> set[str]:
    """Return one string column from a metadata query as a set."""

    with conn.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
    return {_row_value(row, key) for row in rows}


def schema_is_ready(
    conn: Any,
    *,
    required_tables: Iterable[str],
    required_columns_by_table: Mapping[str, Iterable[str]] | None = None,
    required_indexes: Iterable[str] = (),
) -> bool:
    """Return whether the visible schema already satisfies the runtime contract."""

    table_names = tuple(required_tables)
    existing_tables = _fetch_named_values(
        conn,
        query=(
            "SELECT table_name "
            "FROM information_schema.tables "
            "WHERE table_schema = 'public' "
            "AND table_name = ANY(%(table_names)s)"
        ),
        params={"table_names": list(table_names)},
        key="table_name",
    )
    if not set(table_names).issubset(existing_tables):
        return False

    column_requirements = required_columns_by_table or {}
    for table_name, required_columns in column_requirements.items():
        existing_columns = _fetch_named_values(
            conn,
            query=(
                "SELECT column_name "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = %(table_name)s"
            ),
            params={"table_name": table_name},
            key="column_name",
        )
        if not set(required_columns).issubset(existing_columns):
            return False

    index_names = tuple(required_indexes)
    if not index_names:
        return True
    existing_indexes = _fetch_named_values(
        conn,
        query=(
            "SELECT indexname "
            "FROM pg_indexes "
            "WHERE schemaname = 'public' "
            "AND indexname = ANY(%(index_names)s)"
        ),
        params={"index_names": list(index_names)},
        key="indexname",
    )
    return set(index_names).issubset(existing_indexes)
