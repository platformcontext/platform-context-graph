"""PostgreSQL-backed implementation of the fact work queue."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import FactWorkItemRow
from .schema import FACT_WORK_QUEUE_SCHEMA

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised without optional dependency.
    psycopg = None
    dict_row = None


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


def _work_item_params(entry: FactWorkItemRow) -> dict[str, Any]:
    """Return SQL parameters for one fact work item row."""

    return {
        "work_item_id": entry.work_item_id,
        "work_type": entry.work_type,
        "repository_id": entry.repository_id,
        "source_run_id": entry.source_run_id,
        "lease_owner": entry.lease_owner,
        "lease_expires_at": entry.lease_expires_at,
        "status": entry.status,
        "attempt_count": entry.attempt_count,
        "last_error": entry.last_error,
        "created_at": entry.created_at or _utc_now(),
        "updated_at": entry.updated_at or _utc_now(),
    }


class PostgresFactWorkQueue:
    """Persist and lease fact work items in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Bind the queue to a PostgreSQL DSN."""

        self._dsn = dsn
        self._lock = threading.Lock()
        self._conn: Any | None = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        """Return whether the queue is usable in the current process."""

        return psycopg is not None and bool(self._dsn)

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor and bootstrap schema on first use."""

        if not self.enabled:
            raise RuntimeError("fact work queue requires psycopg and a DSN")

        with self._lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            if not self._initialized:
                with self._conn.cursor() as cursor:
                    cursor.execute(FACT_WORK_QUEUE_SCHEMA)
                self._initialized = True
            with self._conn.cursor() as cursor:
                yield cursor

    def enqueue_work_item(self, entry: FactWorkItemRow) -> None:
        """Insert or update a pending work item."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO fact_work_items (
                    work_item_id,
                    work_type,
                    repository_id,
                    source_run_id,
                    lease_owner,
                    lease_expires_at,
                    status,
                    attempt_count,
                    last_error,
                    created_at,
                    updated_at
                ) VALUES (
                    %(work_item_id)s,
                    %(work_type)s,
                    %(repository_id)s,
                    %(source_run_id)s,
                    %(lease_owner)s,
                    %(lease_expires_at)s,
                    %(status)s,
                    %(attempt_count)s,
                    %(last_error)s,
                    %(created_at)s,
                    %(updated_at)s
                )
                ON CONFLICT (work_item_id) DO UPDATE
                SET work_type = EXCLUDED.work_type,
                    repository_id = EXCLUDED.repository_id,
                    source_run_id = EXCLUDED.source_run_id,
                    lease_owner = EXCLUDED.lease_owner,
                    lease_expires_at = EXCLUDED.lease_expires_at,
                    status = EXCLUDED.status,
                    attempt_count = EXCLUDED.attempt_count,
                    last_error = EXCLUDED.last_error,
                    updated_at = EXCLUDED.updated_at
                """,
                _work_item_params(entry),
            )

    def claim_work_item(
        self,
        *,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        """Claim one pending work item and return the leased row."""

        now = _utc_now()
        lease_expires_at = now + timedelta(seconds=lease_ttl_seconds)
        with self._cursor() as cursor:
            cursor.execute(
                """
                WITH claimable AS (
                    SELECT work_item_id
                    FROM fact_work_items
                    WHERE status = 'pending'
                      AND (
                        lease_expires_at IS NULL
                        OR lease_expires_at <= %(now)s
                      )
                    ORDER BY updated_at ASC
                    LIMIT 1
                )
                UPDATE fact_work_items
                SET lease_owner = %(lease_owner)s,
                    lease_expires_at = %(lease_expires_at)s,
                    status = 'leased',
                    attempt_count = fact_work_items.attempt_count + 1,
                    updated_at = %(now)s
                WHERE work_item_id IN (SELECT work_item_id FROM claimable)
                RETURNING work_item_id,
                          work_type,
                          repository_id,
                          source_run_id,
                          lease_owner,
                          lease_expires_at,
                          status,
                          attempt_count,
                          last_error,
                          created_at,
                          updated_at
                """,
                {
                    "lease_owner": lease_owner,
                    "lease_expires_at": lease_expires_at,
                    "now": now,
                },
            )
            row = cursor.fetchone()
        return FactWorkItemRow(**row) if row else None

    def fail_work_item(
        self,
        *,
        work_item_id: str,
        error_message: str,
        terminal: bool,
    ) -> None:
        """Mark one work item as retryable or terminally failed."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE fact_work_items
                SET status = %(status)s,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    attempt_count = fact_work_items.attempt_count + 1,
                    last_error = %(last_error)s,
                    updated_at = %(updated_at)s
                WHERE work_item_id = %(work_item_id)s
                """,
                {
                    "work_item_id": work_item_id,
                    "status": "failed" if terminal else "pending",
                    "last_error": error_message,
                    "updated_at": _utc_now(),
                },
            )
