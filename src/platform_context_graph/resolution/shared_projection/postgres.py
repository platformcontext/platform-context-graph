"""PostgreSQL-backed store for shared projection intents."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Any

from platform_context_graph.postgres_schema import schema_is_ready

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
    created_at,
    completed_at
) VALUES (
    %(intent_id)s,
    %(projection_domain)s,
    %(partition_key)s,
    %(repository_id)s,
    %(source_run_id)s,
    %(generation_id)s,
    %(payload)s,
    %(created_at)s,
    %(completed_at)s
)
ON CONFLICT (intent_id) DO UPDATE
SET projection_domain = EXCLUDED.projection_domain,
    partition_key = EXCLUDED.partition_key,
    repository_id = EXCLUDED.repository_id,
    source_run_id = EXCLUDED.source_run_id,
    generation_id = EXCLUDED.generation_id,
    payload = EXCLUDED.payload,
    created_at = EXCLUDED.created_at,
    completed_at = NULL
"""

_REQUIRED_SHARED_PROJECTION_TABLES = (
    "shared_projection_intents",
    "shared_projection_partition_leases",
)
_REQUIRED_SHARED_PROJECTION_COLUMNS = {
    "shared_projection_intents": ("completed_at",),
}
_REQUIRED_SHARED_PROJECTION_INDEXES = (
    "shared_projection_intents_repo_run_idx",
    "shared_projection_intents_pending_idx",
)


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
        "completed_at": entry.completed_at,
    }


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


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
            if not schema_is_ready(
                conn,
                required_tables=_REQUIRED_SHARED_PROJECTION_TABLES,
                required_columns_by_table=_REQUIRED_SHARED_PROJECTION_COLUMNS,
                required_indexes=_REQUIRED_SHARED_PROJECTION_INDEXES,
            ):
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
                       created_at,
                       completed_at
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

    def list_pending_domain_intents(
        self, *, projection_domain: str, limit: int = 100
    ) -> list[SharedProjectionIntentRow]:
        """Return uncompleted intents for one projection domain."""

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
                       created_at,
                       completed_at
                FROM shared_projection_intents
                WHERE projection_domain = %(projection_domain)s
                  AND completed_at IS NULL
                ORDER BY created_at ASC, intent_id ASC
                LIMIT %(limit)s
                """,
                {
                    "projection_domain": projection_domain,
                    "limit": max(limit, 1),
                },
            )
            rows = cursor.fetchall()
        return [SharedProjectionIntentRow(**row) for row in rows]

    def mark_intents_completed(self, *, intent_ids: list[str]) -> None:
        """Mark one or more shared projection intents completed."""

        if not intent_ids:
            return
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE shared_projection_intents
                SET completed_at = %(completed_at)s
                WHERE intent_id = ANY(%(intent_ids)s)
                """,
                {
                    "completed_at": _utc_now(),
                    "intent_ids": intent_ids,
                },
            )

    def count_pending_repository_generation_intents(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        generation_id: str,
        projection_domain: str,
    ) -> int:
        """Return pending intents for one repository generation and domain."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS pending_count
                FROM shared_projection_intents
                WHERE repository_id = %(repository_id)s
                  AND source_run_id = %(source_run_id)s
                  AND generation_id = %(generation_id)s
                  AND projection_domain = %(projection_domain)s
                  AND completed_at IS NULL
                """,
                {
                    "repository_id": repository_id,
                    "source_run_id": source_run_id,
                    "generation_id": generation_id,
                    "projection_domain": projection_domain,
                },
            )
            row = cursor.fetchone()
        if row is None:
            return 0
        return int(row.get("pending_count") or 0)

    def claim_partition_lease(
        self,
        *,
        projection_domain: str,
        partition_id: int,
        partition_count: int,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> bool:
        """Attempt to acquire a durable lease for one shared partition."""

        now = _utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO shared_projection_partition_leases (
                    projection_domain,
                    partition_id,
                    partition_count,
                    lease_owner,
                    lease_expires_at,
                    updated_at
                ) VALUES (
                    %(projection_domain)s,
                    %(partition_id)s,
                    %(partition_count)s,
                    %(lease_owner)s,
                    %(lease_expires_at)s,
                    %(updated_at)s
                )
                ON CONFLICT (projection_domain, partition_id, partition_count) DO UPDATE
                SET lease_owner = EXCLUDED.lease_owner,
                    lease_expires_at = EXCLUDED.lease_expires_at,
                    updated_at = EXCLUDED.updated_at
                WHERE shared_projection_partition_leases.lease_expires_at IS NULL
                   OR shared_projection_partition_leases.lease_expires_at <= %(updated_at)s
                   OR shared_projection_partition_leases.lease_owner = %(lease_owner)s
                RETURNING projection_domain
                """,
                {
                    "projection_domain": projection_domain,
                    "partition_id": partition_id,
                    "partition_count": partition_count,
                    "lease_owner": lease_owner,
                    "lease_expires_at": now + timedelta(seconds=lease_ttl_seconds),
                    "updated_at": now,
                },
            )
            return cursor.fetchone() is not None

    def release_partition_lease(
        self,
        *,
        projection_domain: str,
        partition_id: int,
        partition_count: int,
        lease_owner: str,
    ) -> None:
        """Release one durable shared partition lease."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE shared_projection_partition_leases
                SET lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = %(updated_at)s
                WHERE projection_domain = %(projection_domain)s
                  AND partition_id = %(partition_id)s
                  AND partition_count = %(partition_count)s
                  AND lease_owner = %(lease_owner)s
                """,
                {
                    "projection_domain": projection_domain,
                    "partition_id": partition_id,
                    "partition_count": partition_count,
                    "lease_owner": lease_owner,
                    "updated_at": _utc_now(),
                },
            )


__all__ = ["PostgresSharedProjectionIntentStore"]
