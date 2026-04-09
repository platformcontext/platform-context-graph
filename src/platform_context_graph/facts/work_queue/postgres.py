"""PostgreSQL-backed implementation of the fact work queue."""

from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any

from platform_context_graph.observability import current_component
from platform_context_graph.observability import get_observability
from platform_context_graph.postgres_schema import schema_is_ready

from .claims import claim_work_item
from .claims import complete_work_item
from .claims import enqueue_work_item
from .claims import fail_work_item
from .claims import lease_work_item
from .inspection import count_shared_projection_pending
from .inspection import list_shared_projection_acceptances
from .inspection import list_queue_snapshot
from .inspection import list_work_items
from .models import FactBackfillRequestRow
from .models import FactReplayEventRow
from .models import FactWorkItemRow
from .models import FactWorkQueueSnapshotRow
from .replay import replay_failed_work_items
from .recovery import dead_letter_work_items
from .recovery import list_replay_events
from .recovery import request_backfill
from .schema import FACT_WORK_QUEUE_SCHEMA
from .shared_completion import complete_shared_projection_domain
from .shared_completion import complete_shared_projection_domain_by_generation
from .shared_completion import mark_shared_projection_pending

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool as _ConnectionPool
except ImportError:  # pragma: no cover - exercised without optional dependency.
    psycopg = None
    dict_row = None
    _ConnectionPool = None

_logger = logging.getLogger(__name__)

_REQUIRED_FACT_WORK_QUEUE_TABLES = (
    "fact_work_items",
    "fact_replay_events",
    "fact_backfill_requests",
)
_REQUIRED_FACT_WORK_QUEUE_COLUMNS = {
    "fact_work_items": (
        "parent_work_item_id",
        "projection_domain",
        "accepted_generation_id",
        "authoritative_shared_domains",
        "completed_shared_domains",
        "shared_projection_pending",
    ),
}
_REQUIRED_FACT_WORK_QUEUE_INDEXES = (
    "fact_work_items_status_idx",
    "fact_work_items_shared_projection_idx",
    "fact_replay_events_work_item_idx",
    "fact_backfill_requests_repo_idx",
)


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
        """Run queue DDL once across the lifetime of the queue.

        Uses a lightweight existence check before attempting DDL so that
        concurrent writers are never blocked by ``CREATE INDEX IF NOT EXISTS``
        acquiring a ``ShareLock`` on the table.
        """

        if self._initialized:
            return
        with self._schema_lock:
            if not self._initialized:
                if not schema_is_ready(
                    conn,
                    required_tables=_REQUIRED_FACT_WORK_QUEUE_TABLES,
                    required_columns_by_table=_REQUIRED_FACT_WORK_QUEUE_COLUMNS,
                    required_indexes=_REQUIRED_FACT_WORK_QUEUE_INDEXES,
                ):
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

        enqueue_work_item(self, entry)

    def claim_work_item(
        self,
        *,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        """Claim one pending work item and return the leased row."""

        return claim_work_item(
            self,
            lease_owner=lease_owner,
            lease_ttl_seconds=lease_ttl_seconds,
        )

    def lease_work_item(
        self,
        *,
        work_item_id: str,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        """Lease one specific work item when it is still claimable."""

        return lease_work_item(
            self,
            work_item_id=work_item_id,
            lease_owner=lease_owner,
            lease_ttl_seconds=lease_ttl_seconds,
        )

    def fail_work_item(
        self,
        *,
        work_item_id: str,
        error_message: str,
        terminal: bool,
        failure_stage: str | None = None,
        error_class: str | None = None,
        failure_class: str | None = None,
        failure_code: str | None = None,
        retry_disposition: str | None = None,
        next_retry_at: Any | None = None,
        operator_note: str | None = None,
    ) -> None:
        """Mark one work item as retryable or terminally failed."""

        fail_work_item(
            self,
            work_item_id=work_item_id,
            error_message=error_message,
            terminal=terminal,
            failure_stage=failure_stage,
            error_class=error_class,
            failure_class=failure_class,
            failure_code=failure_code,
            retry_disposition=retry_disposition,
            next_retry_at=next_retry_at,
            operator_note=operator_note,
        )

    def complete_work_item(self, *, work_item_id: str) -> None:
        """Mark one work item completed and clear its lease."""

        complete_work_item(self, work_item_id=work_item_id)

    def mark_shared_projection_pending(
        self,
        *,
        work_item_id: str,
        accepted_generation_id: str,
        authoritative_shared_domains: list[str] | tuple[str, ...],
    ) -> FactWorkItemRow | None:
        """Fence one parent work item on authoritative shared follow-up."""

        return mark_shared_projection_pending(
            self,
            work_item_id=work_item_id,
            accepted_generation_id=accepted_generation_id,
            authoritative_shared_domains=authoritative_shared_domains,
        )

    def complete_shared_projection_domain(
        self,
        *,
        work_item_id: str,
        projection_domain: str,
        accepted_generation_id: str,
    ) -> FactWorkItemRow | None:
        """Mark one authoritative shared domain complete for a parent work item."""

        return complete_shared_projection_domain(
            self,
            work_item_id=work_item_id,
            projection_domain=projection_domain,
            accepted_generation_id=accepted_generation_id,
        )

    def complete_shared_projection_domain_by_generation(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        accepted_generation_id: str,
        projection_domain: str,
    ) -> FactWorkItemRow | None:
        """Complete one shared domain for the latest accepted repo generation."""

        return complete_shared_projection_domain_by_generation(
            self,
            repository_id=repository_id,
            source_run_id=source_run_id,
            accepted_generation_id=accepted_generation_id,
            projection_domain=projection_domain,
        )

    def replay_failed_work_items(self, **kwargs: Any) -> list[FactWorkItemRow]:
        """Replay terminally failed work items by returning them to pending."""

        return replay_failed_work_items(self, **kwargs)

    def dead_letter_work_items(self, **kwargs: Any) -> list[FactWorkItemRow]:
        """Move selected work items into durable dead-letter state."""

        return dead_letter_work_items(self, **kwargs)

    def request_backfill(self, **kwargs: Any) -> FactBackfillRequestRow:
        """Persist one durable operator backfill request."""

        return request_backfill(self, **kwargs)

    def list_replay_events(self, **kwargs: Any) -> list[FactReplayEventRow]:
        """List durable replay audit rows."""

        return list_replay_events(self, **kwargs)

    def list_work_items(
        self,
        *,
        statuses: list[str] | None = None,
        repository_id: str | None = None,
        source_run_id: str | None = None,
        work_type: str | None = None,
        failure_class: str | None = None,
        limit: int = 100,
    ) -> list[FactWorkItemRow]:
        """Return work items filtered by status and failure selectors."""

        return list_work_items(
            self,
            statuses=statuses,
            repository_id=repository_id,
            source_run_id=source_run_id,
            work_type=work_type,
            failure_class=failure_class,
            limit=limit,
        )

    def count_shared_projection_pending(
        self, *, source_run_id: str | None = None
    ) -> int:
        """Return the number of work items awaiting authoritative shared writes."""

        return count_shared_projection_pending(self, source_run_id=source_run_id)

    def list_shared_projection_acceptances(
        self,
        *,
        projection_domain: str,
        repository_ids: list[str] | None = None,
    ) -> dict[tuple[str, str], str]:
        """Return accepted generations for one shared projection domain."""

        return list_shared_projection_acceptances(
            self,
            projection_domain=projection_domain,
            repository_ids=repository_ids,
        )

    def list_queue_snapshot(self) -> list[FactWorkQueueSnapshotRow]:
        """Return aggregated queue depth and oldest age by work type and status."""

        return list_queue_snapshot(self)

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

    def _executemany(self, query: str, rows: list[dict[str, Any]]) -> None:
        """Execute one batched SQL write through the managed cursor."""

        with self._cursor() as cursor:
            cursor.executemany(query, rows)

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
