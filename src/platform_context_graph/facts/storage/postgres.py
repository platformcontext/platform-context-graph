"""PostgreSQL-backed fact store implementation."""

from __future__ import annotations

import logging
import os
import threading
from contextlib import contextmanager
import time
from collections.abc import Iterator
from typing import Any

from platform_context_graph.observability import current_component
from platform_context_graph.observability import get_observability

from .models import FactRecordRow
from .models import FactRunRow
from .schema import FACT_STORE_SCHEMA
from .sql import FACT_RECORD_UPSERT_SQL
from .sql import FACT_RUN_UPSERT_SQL
from .sql import fact_record_params
from .sql import fact_run_params

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool as _ConnectionPool
except ImportError:  # pragma: no cover - exercised without optional dependency.
    psycopg = None
    dict_row = None
    _ConnectionPool = None

_logger = logging.getLogger(__name__)

_FACT_UPSERT_BATCH_SIZE = int(os.getenv("PCG_FACT_UPSERT_BATCH_SIZE", "2000"))


class PostgresFactStore:
    """Persist fact runs and fact records in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Bind the fact store to a PostgreSQL DSN."""

        self._dsn = dsn
        self._schema_lock = threading.Lock()
        self._lock = threading.Lock()
        self._pool: Any | None = None
        self._conn: Any | None = None
        self._conn_lock: threading.Lock | None = None
        self._initialized = False
        if psycopg is not None and _ConnectionPool is not None and dsn:
            try:
                pool_max = max(4, int(os.getenv("PCG_FACT_STORE_POOL_MAX_SIZE", "4")))
                self._pool = _ConnectionPool(
                    dsn,
                    min_size=1,
                    max_size=pool_max,
                    max_waiting=max(pool_max * 4, 8),
                    kwargs={"autocommit": True, "row_factory": dict_row},
                )
            except Exception:
                _logger.warning(
                    "Fact store pool initialization failed; falling back to one connection",
                    exc_info=True,
                )
                self._pool = None
                self._conn_lock = threading.Lock()
        else:
            self._conn_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """Return whether the fact store is usable in the current process."""

        return psycopg is not None and bool(self._dsn)

    def _ensure_schema(self, conn: Any) -> None:
        """Run fact-store DDL once across the lifetime of the store.

        Uses a lightweight existence check before attempting DDL so that
        concurrent writers are never blocked by ``CREATE INDEX IF NOT EXISTS``
        acquiring a ``ShareLock`` on the table.
        """

        if self._initialized:
            return
        with self._schema_lock:
            if not self._initialized:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'fact_records'"
                    )
                    if cursor.fetchone() is not None:
                        self._initialized = True
                        return
                with conn.cursor() as cursor:
                    cursor.execute(FACT_STORE_SCHEMA)
                self._initialized = True

    def _refresh_pool_metrics(self, *, component: str) -> None:
        """Refresh connection-pool gauges when the fact store uses pooling."""

        if self._pool is None:
            return
        stats = self._pool.get_stats()
        get_observability().set_fact_postgres_pool_stats(
            component=component,
            pool_name="fact_store",
            size=int(stats.get("pool_size", 0)),
            available=int(stats.get("pool_available", 0)),
            waiting=int(stats.get("requests_waiting", 0)),
        )

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor and bootstrap schema on first use."""

        if not self.enabled:
            raise RuntimeError("fact store requires psycopg and a DSN")

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
                    pool_name="fact_store",
                    outcome="error",
                    duration_seconds=max(time.perf_counter() - acquire_started, 0.0),
                )
                self._refresh_pool_metrics(component=component)
                raise
            observability.record_fact_postgres_pool_acquire(
                component=component,
                pool_name="fact_store",
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

    def upsert_fact_run(self, entry: FactRunRow) -> None:
        """Insert or update one fact run row."""

        self._record_operation(
            operation="upsert_fact_run",
            row_count=1,
            callback=lambda: self._execute(
                FACT_RUN_UPSERT_SQL,
                fact_run_params(entry),
            ),
        )

    def upsert_facts(self, entries: list[FactRecordRow]) -> None:
        """Insert or update fact records in one batch."""

        if not entries:
            return
        rows = [fact_record_params(entry) for entry in entries]
        self._record_operation(
            operation="upsert_facts",
            row_count=len(rows),
            callback=lambda: self._executemany(FACT_RECORD_UPSERT_SQL, rows),
        )

    def list_facts(
        self,
        *,
        repository_id: str,
        source_run_id: str,
    ) -> list[FactRecordRow]:
        """Return fact records for one repository/run pair."""

        rows = self._record_operation(
            operation="list_facts",
            callback=lambda: self._fetchall(
                """
                SELECT fact_id,
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
                FROM fact_records
                WHERE repository_id = %(repository_id)s
                  AND source_run_id = %(source_run_id)s
                ORDER BY relative_path NULLS FIRST, fact_id
                """,
                {
                    "repository_id": repository_id,
                    "source_run_id": source_run_id,
                },
            ),
        )
        return [FactRecordRow(**row) for row in rows]

    def list_facts_by_type(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        fact_type: str,
    ) -> list[FactRecordRow]:
        """Return fact records filtered by type for one repository/run pair.

        Filters at the SQL level using the composite index
        ``fact_records_repo_run_type_idx(repository_id, source_run_id, fact_type)``
        so Postgres never reads rows outside the requested type.

        Args:
            repository_id: Canonical repository identifier
                (e.g. ``"repository:my-app"``).
            source_run_id: The fact run that produced these records.
            fact_type: One of ``"RepositoryObserved"``, ``"FileObserved"``,
                or ``"ParsedEntityObserved"``.

        Returns:
            All matching fact records ordered by
            ``(relative_path NULLS FIRST, fact_id)``.
        """
        from .queries import list_facts_by_type as _list_facts_by_type

        return _list_facts_by_type(
            cursor_factory=self._cursor,
            record_operation=self._record_operation,
            repository_id=repository_id,
            source_run_id=source_run_id,
            fact_type=fact_type,
        )

    def iter_fact_batches(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        fact_type: str,
        batch_size: int = 2000,
    ) -> Iterator[list[FactRecordRow]]:
        """Load fact records in batches using keyset pagination.

        Yields one batch at a time rather than holding the full result
        set in Python. Each batch is bounded by ``batch_size`` rows,
        keeping peak memory proportional to one batch (~1 MB).

        Uses ``(relative_path, fact_id)`` as the seek cursor, which is
        O(log n) per page via the composite index — unlike LIMIT/OFFSET
        which is O(n) for deep pages.

        Args:
            repository_id: Canonical repository identifier.
            source_run_id: The fact run that produced these records.
            fact_type: Fact type to paginate (typically
                ``"ParsedEntityObserved"``).
            batch_size: Maximum rows per batch.  Defaults to 2 000,
                which at ~450 bytes/row keeps each batch under ~1 MB.

        Returns:
            Iterator of batches, each containing up to ``batch_size`` records.
        """
        from .queries import iter_fact_batches as _iter_fact_batches

        return _iter_fact_batches(
            cursor_factory=self._cursor,
            record_operation=self._record_operation,
            repository_id=repository_id,
            source_run_id=source_run_id,
            fact_type=fact_type,
            batch_size=batch_size,
        )

    def count_facts(
        self,
        *,
        repository_id: str,
        source_run_id: str,
    ) -> int:
        """Return the total fact count for one repository/run pair.

        Uses a simple ``COUNT(*)`` which Postgres resolves via an
        index-only scan on ``fact_records_repository_run_idx``.

        Args:
            repository_id: Canonical repository identifier.
            source_run_id: The fact run that produced these records.

        Returns:
            Total number of fact records for the repository/run pair.
        """
        from .queries import count_facts as _count_facts

        return _count_facts(
            cursor_factory=self._cursor,
            record_operation=self._record_operation,
            repository_id=repository_id,
            source_run_id=source_run_id,
        )

    def _component(self) -> str:
        """Return the logical component for telemetry emitted by this store."""

        runtime = get_observability()
        return current_component() or runtime.component

    def _execute(self, query: str, params: dict[str, Any]) -> None:
        """Execute one SQL statement through the managed cursor."""

        with self._cursor() as cursor:
            cursor.execute(query, params)

    def _executemany(self, query: str, rows: list[dict[str, Any]]) -> None:
        """Execute one SQL batch through the managed cursor in chunks.

        Large batches are split into chunks of ``_FACT_UPSERT_BATCH_SIZE``
        rows (default 2000, configurable via ``PCG_FACT_UPSERT_BATCH_SIZE``).
        Each chunk commits independently under autocommit mode, preventing a
        single massive repo from creating a multi-hour transaction that stalls
        the entire pipeline.
        """

        batch_size = _FACT_UPSERT_BATCH_SIZE
        if len(rows) <= batch_size:
            with self._cursor() as cursor:
                cursor.executemany(query, rows)
            return

        total = len(rows)
        for offset in range(0, total, batch_size):
            chunk = rows[offset : offset + batch_size]
            with self._cursor() as cursor:
                cursor.executemany(query, chunk)
            if offset + batch_size < total:
                _logger.debug(
                    "Fact upsert chunk committed: %d/%d rows",
                    min(offset + batch_size, total),
                    total,
                )

    def _fetchall(
        self,
        query: str,
        params: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Execute one SQL read and return all fetched rows."""

        with self._cursor() as cursor:
            cursor.execute(query, params)
            fetched_rows = cursor.fetchall()
        return list(fetched_rows)

    def _record_operation(
        self,
        *,
        operation: str,
        callback: Any,
        row_count: int | None = None,
    ) -> Any:
        """Wrap one fact-store operation with OTEL spans and metrics."""

        observability = get_observability()
        component = self._component()
        started = time.perf_counter()
        with observability.start_span(
            f"pcg.fact_store.{operation}",
            component=component,
            attributes={
                "pcg.backend": "postgres",
                "pcg.operation": operation,
                **({"pcg.rows": row_count} if row_count is not None else {}),
            },
        ) as span:
            try:
                result = callback()
            except Exception as exc:
                if span is not None:
                    span.record_exception(exc)
                observability.record_fact_store_operation(
                    component=component,
                    operation=operation,
                    outcome="error",
                    duration_seconds=max(time.perf_counter() - started, 0.0),
                    row_count=row_count,
                )
                raise
        result_row_count = len(result) if isinstance(result, list) else row_count
        observability.record_fact_store_operation(
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
