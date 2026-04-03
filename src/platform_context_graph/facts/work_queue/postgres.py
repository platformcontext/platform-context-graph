"""PostgreSQL-backed implementation of the fact work queue."""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
from datetime import timedelta
import time
from typing import Any

from platform_context_graph.observability import current_component
from platform_context_graph.observability import get_observability

from .models import FactWorkItemRow
from .models import FactWorkQueueSnapshotRow
from .replay import replay_failed_work_items
from .schema import FACT_WORK_QUEUE_SCHEMA
from .support import utc_now
from .support import work_item_params

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool as _ConnectionPool
except ImportError:  # pragma: no cover - exercised without optional dependency.
    psycopg = None
    dict_row = None
    _ConnectionPool = None

_logger = logging.getLogger(__name__)
class PostgresFactWorkQueue:
    """Persist and lease fact work items in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Bind the queue to a PostgreSQL DSN."""

        self._dsn = dsn
        self._schema_lock = threading.Lock()
        self._lock = threading.Lock()
        self._pool: Any | None = None
        self._conn: Any | None = None
        self._conn_lock: threading.Lock | None = None
        self._initialized = False
        if psycopg is not None and _ConnectionPool is not None and dsn:
            try:
                pool_max = max(4, int(os.getenv("PCG_FACT_QUEUE_POOL_MAX_SIZE", "4")))
                self._pool = _ConnectionPool(
                    dsn,
                    min_size=1,
                    max_size=pool_max,
                    max_waiting=max(pool_max * 4, 8),
                    kwargs={"autocommit": True, "row_factory": dict_row},
                )
            except Exception:
                _logger.warning(
                    "Fact work queue pool initialization failed; falling back to one connection",
                    exc_info=True,
                )
                self._pool = None
                self._conn_lock = threading.Lock()
        else:
            self._conn_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """Return whether the queue is usable in the current process."""

        return psycopg is not None and bool(self._dsn)

    def _ensure_schema(self, conn: Any) -> None:
        """Run queue DDL once across the lifetime of the queue."""

        if self._initialized:
            return
        with self._schema_lock:
            if not self._initialized:
                with conn.cursor() as cursor:
                    cursor.execute(FACT_WORK_QUEUE_SCHEMA)
                self._initialized = True

    def _refresh_pool_metrics(self, *, component: str) -> None:
        """Refresh connection-pool gauges when the queue uses pooling."""

        if self._pool is None:
            return
        stats = self._pool.get_stats()
        get_observability().set_fact_postgres_pool_stats(
            component=component,
            pool_name="fact_queue",
            size=int(stats.get("pool_size", 0)),
            available=int(stats.get("pool_available", 0)),
            waiting=int(stats.get("requests_waiting", 0)),
        )
    def refresh_pool_metrics(self, *, component: str) -> None:
        """Refresh queue pool metrics for independent samplers."""

        self._refresh_pool_metrics(component=component)

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor and bootstrap schema on first use."""

        if not self.enabled:
            raise RuntimeError("fact work queue requires psycopg and a DSN")

        if self._pool is not None:
            observability = get_observability()
            component = self._component()
            acquire_started = time.perf_counter()
            try:
                connection_context = self._pool.connection()
                conn = connection_context.__enter__()
            except Exception:
                observability.record_fact_postgres_pool_acquire(
                    component=component,
                    pool_name="fact_queue",
                    outcome="error",
                    duration_seconds=max(time.perf_counter() - acquire_started, 0.0),
                )
                self._refresh_pool_metrics(component=component)
                raise
            observability.record_fact_postgres_pool_acquire(
                component=component,
                pool_name="fact_queue",
                outcome="success",
                duration_seconds=max(time.perf_counter() - acquire_started, 0.0),
            )
            self._refresh_pool_metrics(component=component)
            exc_info: tuple[Any, Any, Any] = (None, None, None)
            try:
                self._ensure_schema(conn)
                with conn.cursor() as cursor:
                    yield cursor
            except BaseException as exc:  # pragma: no cover - exercised via callers.
                exc_info = (type(exc), exc, exc.__traceback__)
                raise
            finally:
                connection_context.__exit__(*exc_info)
                self._refresh_pool_metrics(component=component)
            return

        assert self._conn_lock is not None
        with self._conn_lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            self._ensure_schema(self._conn)
            with self._conn.cursor() as cursor:
                yield cursor

    def enqueue_work_item(self, entry: FactWorkItemRow) -> None:
        """Insert or update a pending work item."""

        self._record_operation(
            operation="enqueue_work_item",
            row_count=1,
            callback=lambda: self._execute(
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
                work_item_params(entry),
            ),
        )

    def claim_work_item(
        self,
        *,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        """Claim one pending work item and return the leased row."""

        now = utc_now()
        lease_expires_at = now + timedelta(seconds=lease_ttl_seconds)
        row = self._record_operation(
            operation="claim_work_item",
            callback=lambda: self._fetchone(
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
            ),
        )
        return FactWorkItemRow(**row) if row else None

    def lease_work_item(
        self,
        *,
        work_item_id: str,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        """Lease one specific work item when it is still claimable."""

        now = utc_now()
        lease_expires_at = now + timedelta(seconds=lease_ttl_seconds)
        row = self._record_operation(
            operation="lease_work_item",
            callback=lambda: self._fetchone(
                """
                UPDATE fact_work_items
                SET lease_owner = %(lease_owner)s,
                    lease_expires_at = %(lease_expires_at)s,
                    status = 'leased',
                    attempt_count = fact_work_items.attempt_count + 1,
                    updated_at = %(now)s
                WHERE work_item_id = %(work_item_id)s
                  AND status = 'pending'
                  AND (
                    lease_expires_at IS NULL
                    OR lease_expires_at <= %(now)s
                  )
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
                    "work_item_id": work_item_id,
                    "lease_owner": lease_owner,
                    "lease_expires_at": lease_expires_at,
                    "now": now,
                },
            ),
        )
        return FactWorkItemRow(**row) if row else None

    def fail_work_item(
        self,
        *,
        work_item_id: str,
        error_message: str,
        terminal: bool,
    ) -> None:
        """Mark one work item as retryable or terminally failed."""

        self._record_operation(
            operation="fail_work_item",
            row_count=1,
            callback=lambda: self._execute(
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
                    "updated_at": utc_now(),
                },
            ),
        )

    def complete_work_item(self, *, work_item_id: str) -> None:
        """Mark one work item completed and clear its lease."""

        self._record_operation(
            operation="complete_work_item",
            row_count=1,
            callback=lambda: self._execute(
                """
                UPDATE fact_work_items
                SET status = 'completed',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error = NULL,
                    updated_at = %(updated_at)s
                WHERE work_item_id = %(work_item_id)s
                """,
                {
                    "work_item_id": work_item_id,
                    "updated_at": utc_now(),
                },
            ),
        )

    def replay_failed_work_items(self, **kwargs: Any) -> list[FactWorkItemRow]:
        """Replay terminally failed work items by returning them to pending."""

        return replay_failed_work_items(self, **kwargs)

    def list_queue_snapshot(self) -> list[FactWorkQueueSnapshotRow]:
        """Return aggregated queue depth and oldest age by work type and status."""

        now = utc_now()
        rows = self._record_operation(
            operation="list_queue_snapshot",
            callback=lambda: self._fetchall(
                """
                SELECT work_type,
                       status,
                       COUNT(*) AS depth,
                       COALESCE(
                         EXTRACT(EPOCH FROM (%(now)s - MIN(created_at))),
                         0
                       ) AS oldest_age_seconds
                FROM fact_work_items
                GROUP BY work_type, status
                """,
                {"now": now},
            ),
            row_count=None,
        )
        return [
            FactWorkQueueSnapshotRow(
                work_type=row["work_type"],
                status=row["status"],
                depth=int(row["depth"]),
                oldest_age_seconds=float(row["oldest_age_seconds"] or 0.0),
            )
            for row in rows
        ]

    def _component(self) -> str:
        """Return the logical component for emitted telemetry."""

        runtime = get_observability()
        return current_component() or runtime.component

    def _execute(self, query: str, params: dict[str, Any]) -> None:
        """Execute one SQL statement through the managed cursor."""

        with self._cursor() as cursor:
            cursor.execute(query, params)

    def _fetchone(self, query: str, params: dict[str, Any]) -> dict[str, Any] | None:
        """Execute one SQL read and return one row when present."""

        with self._cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        return dict(row) if row is not None else None

    def _fetchall(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute one SQL read and return all fetched rows."""

        with self._cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return list(rows)

    def _record_operation(
        self,
        *,
        operation: str,
        callback: Any,
        row_count: int | None = None,
    ) -> Any:
        """Wrap one queue operation with OTEL spans and metrics."""

        observability = get_observability()
        component = self._component()
        started = time.perf_counter()
        with observability.start_span(
            f"pcg.fact_queue.{operation}",
            component=component,
            attributes={
                "pcg.backend": "postgres",
                "pcg.operation": operation,
            },
        ) as span:
            try:
                result = callback()
            except Exception as exc:
                if span is not None:
                    span.record_exception(exc)
                observability.record_fact_queue_operation(
                    component=component,
                    operation=operation,
                    outcome="error",
                    duration_seconds=max(time.perf_counter() - started, 0.0),
                    row_count=row_count,
                )
                raise
        result_row_count = row_count
        if isinstance(result, list):
            result_row_count = len(result)
        elif isinstance(result, dict):
            result_row_count = 1
        observability.record_fact_queue_operation(
            component=component,
            operation=operation,
            outcome="success",
            duration_seconds=max(time.perf_counter() - started, 0.0),
            row_count=result_row_count,
        )
        return result

    def close(self) -> None:
        """Close the shared PostgreSQL connection if it is open."""

        if self._pool is not None:
            self._pool.close()
            self._pool = None
        with self._lock:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
            self._conn = None
            self._initialized = False
