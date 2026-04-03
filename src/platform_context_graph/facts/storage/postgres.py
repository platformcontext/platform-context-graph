"""PostgreSQL-backed fact store implementation."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any

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

        with self._cursor() as cursor:
            cursor.execute(_FACT_RUN_UPSERT_SQL, _fact_run_params(entry))

    def upsert_facts(self, entries: list[FactRecordRow]) -> None:
        """Insert or update fact records in one batch."""

        if not entries:
            return
        with self._cursor() as cursor:
            cursor.executemany(
                _FACT_RECORD_UPSERT_SQL,
                [_fact_record_params(entry) for entry in entries],
            )

    def list_facts(
        self,
        *,
        repository_id: str,
        source_run_id: str,
    ) -> list[FactRecordRow]:
        """Return fact records for one repository/run pair."""

        with self._cursor() as cursor:
            cursor.execute(
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
            )
            rows = cursor.fetchall()
        return [FactRecordRow(**row) for row in rows]

    def close(self) -> None:
        """Close the underlying PostgreSQL connection when it exists."""

        with self._lock:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
            self._conn = None
            self._initialized = False

    def close(self) -> None:
        """Close the shared PostgreSQL connection if it is open."""

        with self._lock:
            if self._conn is not None and not self._conn.closed:
                self._conn.close()
            self._conn = None
            self._initialized = False
