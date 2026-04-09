"""PostgreSQL-backed store for shared projection intents."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any

from .models import SharedProjectionIntentRow
from .schema import SHARED_PROJECTION_INTENT_SCHEMA

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - exercised without optional dependency.
    psycopg = None
    dict_row = None
    Jsonb = None

_UPSERT_INTENT_SQL = """
INSERT INTO shared_projection_intents (
    intent_id,
    projection_domain,
    partition_key,
    repository_id,
    source_run_id,
    generation_id,
    payload,
    created_at
) VALUES (
    %(intent_id)s,
    %(projection_domain)s,
    %(partition_key)s,
    %(repository_id)s,
    %(source_run_id)s,
    %(generation_id)s,
    %(payload)s,
    %(created_at)s
)
ON CONFLICT (intent_id) DO UPDATE
SET projection_domain = EXCLUDED.projection_domain,
    partition_key = EXCLUDED.partition_key,
    repository_id = EXCLUDED.repository_id,
    source_run_id = EXCLUDED.source_run_id,
    generation_id = EXCLUDED.generation_id,
    payload = EXCLUDED.payload,
    created_at = EXCLUDED.created_at
"""


def _intent_params(entry: SharedProjectionIntentRow) -> dict[str, Any]:
    """Return SQL parameters for one shared projection intent row."""

    return {
        "intent_id": entry.intent_id,
        "projection_domain": entry.projection_domain,
        "partition_key": entry.partition_key,
        "repository_id": entry.repository_id,
        "source_run_id": entry.source_run_id,
        "generation_id": entry.generation_id,
        "payload": Jsonb(entry.payload),
        "created_at": entry.created_at,
    }


class PostgresSharedProjectionIntentStore:
    """Persist shared projection intents in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Bind the store to a PostgreSQL DSN."""

        self._dsn = dsn
        self._conn: Any | None = None
        self._conn_lock = threading.Lock()
        self._schema_lock = threading.Lock()
        self._initialized = False

    @property
    def enabled(self) -> bool:
        """Return whether the store is usable in the current process."""

        return psycopg is not None and bool(self._dsn)

    def close(self) -> None:
        """Close the shared PostgreSQL connection if it is open."""

        with self._conn_lock:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
            self._conn = None
            self._initialized = False

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor and bootstrap schema on first use."""

        if not self.enabled:
            raise RuntimeError(
                "shared projection intent store requires psycopg and a DSN"
            )
        with self._conn_lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            self._ensure_schema(self._conn)
            with self._conn.cursor() as cursor:
                yield cursor

    def _ensure_schema(self, conn: Any) -> None:
        """Run shared projection intent DDL once across the store lifetime."""

        if self._initialized:
            return
        with self._schema_lock:
            if self._initialized:
                return
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' "
                    "AND table_name = 'shared_projection_intents'"
                )
                if cursor.fetchone() is not None:
                    self._initialized = True
                    return
            with conn.cursor() as cursor:
                cursor.execute(SHARED_PROJECTION_INTENT_SCHEMA)
            self._initialized = True

    def upsert_intents(self, entries: list[SharedProjectionIntentRow]) -> None:
        """Insert or update shared projection intents."""

        if not entries:
            return
        with self._cursor() as cursor:
            cursor.executemany(
                _UPSERT_INTENT_SQL,
                [_intent_params(entry) for entry in entries],
            )

    def list_intents(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        projection_domain: str | None = None,
        limit: int = 100,
    ) -> list[SharedProjectionIntentRow]:
        """Return persisted intents for one repository/run pair."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT intent_id,
                       projection_domain,
                       partition_key,
                       repository_id,
                       source_run_id,
                       generation_id,
                       payload,
                       created_at
                FROM shared_projection_intents
                WHERE repository_id = %(repository_id)s
                  AND source_run_id = %(source_run_id)s
                  AND (
                      %(projection_domain)s IS NULL
                      OR projection_domain = %(projection_domain)s
                  )
                ORDER BY created_at ASC, intent_id ASC
                LIMIT %(limit)s
                """,
                {
                    "repository_id": repository_id,
                    "source_run_id": source_run_id,
                    "projection_domain": projection_domain,
                    "limit": max(limit, 1),
                },
            )
            rows = cursor.fetchall()
        return [SharedProjectionIntentRow(**row) for row in rows]


__all__ = ["PostgresSharedProjectionIntentStore"]
