"""PostgreSQL-backed fact store implementation."""

from __future__ import annotations

import threading
from contextlib import contextmanager
import time
from typing import Any

from platform_context_graph.observability import current_component
from platform_context_graph.observability import get_observability

from .models import FactRecordRow
from .models import FactRunRow
from .schema import FACT_STORE_SCHEMA

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised without optional dependency.
    psycopg = None
    dict_row = None

_FACT_RUN_UPSERT_SQL = """
INSERT INTO fact_runs (
    source_run_id,
    source_system,
    source_snapshot_id,
    repository_id,
    status,
    started_at,
    completed_at
) VALUES (
    %(source_run_id)s,
    %(source_system)s,
    %(source_snapshot_id)s,
    %(repository_id)s,
    %(status)s,
    %(started_at)s,
    %(completed_at)s
)
ON CONFLICT (source_run_id) DO UPDATE
SET source_system = EXCLUDED.source_system,
    source_snapshot_id = EXCLUDED.source_snapshot_id,
    repository_id = EXCLUDED.repository_id,
    status = EXCLUDED.status,
    started_at = EXCLUDED.started_at,
    completed_at = EXCLUDED.completed_at
"""

_FACT_RECORD_UPSERT_SQL = """
INSERT INTO fact_records (
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
) VALUES (
    %(fact_id)s,
    %(fact_type)s,
    %(repository_id)s,
    %(checkout_path)s,
    %(relative_path)s,
    %(source_system)s,
    %(source_run_id)s,
    %(source_snapshot_id)s,
    %(payload)s,
    %(observed_at)s,
    %(ingested_at)s,
    %(provenance)s
)
ON CONFLICT (fact_id) DO UPDATE
SET fact_type = EXCLUDED.fact_type,
    repository_id = EXCLUDED.repository_id,
    checkout_path = EXCLUDED.checkout_path,
    relative_path = EXCLUDED.relative_path,
    source_system = EXCLUDED.source_system,
    source_run_id = EXCLUDED.source_run_id,
    source_snapshot_id = EXCLUDED.source_snapshot_id,
    payload = EXCLUDED.payload,
    observed_at = EXCLUDED.observed_at,
    ingested_at = EXCLUDED.ingested_at,
    provenance = EXCLUDED.provenance
"""


def _fact_run_params(entry: FactRunRow) -> dict[str, Any]:
    """Return SQL parameters for one fact run row."""

    return {
        "source_run_id": entry.source_run_id,
        "source_system": entry.source_system,
        "source_snapshot_id": entry.source_snapshot_id,
        "repository_id": entry.repository_id,
        "status": entry.status,
        "started_at": entry.started_at,
        "completed_at": entry.completed_at,
    }


def _fact_record_params(entry: FactRecordRow) -> dict[str, Any]:
    """Return SQL parameters for one fact record row."""

    return {
        "fact_id": entry.fact_id,
        "fact_type": entry.fact_type,
        "repository_id": entry.repository_id,
        "checkout_path": entry.checkout_path,
        "relative_path": entry.relative_path,
        "source_system": entry.source_system,
        "source_run_id": entry.source_run_id,
        "source_snapshot_id": entry.source_snapshot_id,
        "payload": entry.payload,
        "observed_at": entry.observed_at,
        "ingested_at": entry.ingested_at,
        "provenance": entry.provenance,
    }


class PostgresFactStore:
    """Persist fact runs and fact records in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Bind the fact store to a PostgreSQL DSN."""

        self._dsn = dsn
        self._lock = threading.Lock()
        self._conn: Any | None = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        """Return whether the fact store is usable in the current process."""

        return psycopg is not None and bool(self._dsn)

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor and bootstrap schema on first use."""

        if not self.enabled:
            raise RuntimeError("fact store requires psycopg and a DSN")

        with self._lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            if not self._initialized:
                with self._conn.cursor() as cursor:
                    cursor.execute(FACT_STORE_SCHEMA)
                self._initialized = True
            with self._conn.cursor() as cursor:
                yield cursor

    def upsert_fact_run(self, entry: FactRunRow) -> None:
        """Insert or update one fact run row."""

        self._record_operation(
            operation="upsert_fact_run",
            row_count=1,
            callback=lambda: self._execute(
                _FACT_RUN_UPSERT_SQL,
                _fact_run_params(entry),
            ),
        )

    def upsert_facts(self, entries: list[FactRecordRow]) -> None:
        """Insert or update fact records in one batch."""

        if not entries:
            return
        rows = [_fact_record_params(entry) for entry in entries]
        self._record_operation(
            operation="upsert_facts",
            row_count=len(rows),
            callback=lambda: self._executemany(_FACT_RECORD_UPSERT_SQL, rows),
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

    def _component(self) -> str:
        """Return the logical component for telemetry emitted by this store."""

        runtime = get_observability()
        return current_component() or runtime.component

    def _execute(self, query: str, params: dict[str, Any]) -> None:
        """Execute one SQL statement through the managed cursor."""

        with self._cursor() as cursor:
            cursor.execute(query, params)

    def _executemany(self, query: str, rows: list[dict[str, Any]]) -> None:
        """Execute one SQL batch through the managed cursor."""

        with self._cursor() as cursor:
            cursor.executemany(query, rows)

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

        with self._lock:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
            self._conn = None
            self._initialized = False
