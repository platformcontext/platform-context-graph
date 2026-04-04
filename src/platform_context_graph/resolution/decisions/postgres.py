"""PostgreSQL-backed store for projection decisions and evidence."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Any

from .models import ProjectionDecisionEvidenceRow
from .models import ProjectionDecisionRow
from .schema import PROJECTION_DECISION_SCHEMA

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:  # pragma: no cover - exercised without optional dependency.
    psycopg = None
    dict_row = None
    Jsonb = None

_UPSERT_DECISION_SQL = """
INSERT INTO projection_decisions (
    decision_id,
    decision_type,
    repository_id,
    source_run_id,
    work_item_id,
    subject,
    confidence_score,
    confidence_reason,
    provenance_summary,
    created_at
) VALUES (
    %(decision_id)s,
    %(decision_type)s,
    %(repository_id)s,
    %(source_run_id)s,
    %(work_item_id)s,
    %(subject)s,
    %(confidence_score)s,
    %(confidence_reason)s,
    %(provenance_summary)s,
    %(created_at)s
)
ON CONFLICT (decision_id) DO UPDATE
SET decision_type = EXCLUDED.decision_type,
    repository_id = EXCLUDED.repository_id,
    source_run_id = EXCLUDED.source_run_id,
    work_item_id = EXCLUDED.work_item_id,
    subject = EXCLUDED.subject,
    confidence_score = EXCLUDED.confidence_score,
    confidence_reason = EXCLUDED.confidence_reason,
    provenance_summary = EXCLUDED.provenance_summary,
    created_at = EXCLUDED.created_at
"""

_INSERT_EVIDENCE_SQL = """
INSERT INTO projection_decision_evidence (
    evidence_id,
    decision_id,
    fact_id,
    evidence_kind,
    detail,
    created_at
) VALUES (
    %(evidence_id)s,
    %(decision_id)s,
    %(fact_id)s,
    %(evidence_kind)s,
    %(detail)s,
    %(created_at)s
)
ON CONFLICT (evidence_id) DO UPDATE
SET decision_id = EXCLUDED.decision_id,
    fact_id = EXCLUDED.fact_id,
    evidence_kind = EXCLUDED.evidence_kind,
    detail = EXCLUDED.detail,
    created_at = EXCLUDED.created_at
"""


def _decision_params(entry: ProjectionDecisionRow) -> dict[str, Any]:
    """Return SQL parameters for one projection decision row."""

    return {
        "decision_id": entry.decision_id,
        "decision_type": entry.decision_type,
        "repository_id": entry.repository_id,
        "source_run_id": entry.source_run_id,
        "work_item_id": entry.work_item_id,
        "subject": entry.subject,
        "confidence_score": entry.confidence_score,
        "confidence_reason": entry.confidence_reason,
        "provenance_summary": Jsonb(entry.provenance_summary),
        "created_at": entry.created_at,
    }


def _evidence_params(entry: ProjectionDecisionEvidenceRow) -> dict[str, Any]:
    """Return SQL parameters for one decision evidence row."""

    return {
        "evidence_id": entry.evidence_id,
        "decision_id": entry.decision_id,
        "fact_id": entry.fact_id,
        "evidence_kind": entry.evidence_kind,
        "detail": Jsonb(entry.detail),
        "created_at": entry.created_at,
    }


class PostgresProjectionDecisionStore:
    """Persist projection decisions and evidence in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Bind the decision store to a PostgreSQL DSN."""

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

    def _ensure_schema(self, conn: Any) -> None:
        """Run decision-store DDL once across the lifetime of the store.

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
                        "AND table_name = 'projection_decisions'"
                    )
                    if cursor.fetchone() is not None:
                        self._initialized = True
                        return
                with conn.cursor() as cursor:
                    cursor.execute(PROJECTION_DECISION_SCHEMA)
                self._initialized = True

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor and bootstrap schema on first use."""

        if not self.enabled:
            raise RuntimeError("projection decision store requires psycopg and a DSN")
        with self._conn_lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            self._ensure_schema(self._conn)
            with self._conn.cursor() as cursor:
                yield cursor

    def upsert_decision(self, entry: ProjectionDecisionRow) -> None:
        """Insert or update one projection decision."""

        self._execute(_UPSERT_DECISION_SQL, _decision_params(entry))

    def insert_evidence(self, entries: list[ProjectionDecisionEvidenceRow]) -> None:
        """Insert or update evidence rows for projection decisions."""

        if not entries:
            return
        self._executemany(
            _INSERT_EVIDENCE_SQL, [_evidence_params(row) for row in entries]
        )

    def list_decisions(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        decision_type: str | None = None,
        limit: int = 100,
    ) -> list[ProjectionDecisionRow]:
        """Return persisted decisions for one repository/run pair."""

        rows = self._fetchall(
            """
            SELECT decision_id,
                   decision_type,
                   repository_id,
                   source_run_id,
                   work_item_id,
                   subject,
                   confidence_score,
                   confidence_reason,
                   provenance_summary,
                   created_at
            FROM projection_decisions
            WHERE repository_id = %(repository_id)s
              AND source_run_id = %(source_run_id)s
              AND (%(decision_type)s IS NULL OR decision_type = %(decision_type)s)
            ORDER BY created_at ASC, decision_id ASC
            LIMIT %(limit)s
            """,
            {
                "repository_id": repository_id,
                "source_run_id": source_run_id,
                "decision_type": decision_type,
                "limit": max(limit, 1),
            },
        )
        return [ProjectionDecisionRow(**row) for row in rows]

    def list_evidence(
        self,
        *,
        decision_id: str,
    ) -> list[ProjectionDecisionEvidenceRow]:
        """Return persisted evidence for one decision."""

        rows = self._fetchall(
            """
            SELECT evidence_id,
                   decision_id,
                   fact_id,
                   evidence_kind,
                   detail,
                   created_at
            FROM projection_decision_evidence
            WHERE decision_id = %(decision_id)s
            ORDER BY created_at ASC, evidence_id ASC
            """,
            {"decision_id": decision_id},
        )
        return [ProjectionDecisionEvidenceRow(**row) for row in rows]

    def _execute(self, query: str, params: dict[str, Any]) -> None:
        """Execute one SQL statement through the managed cursor."""

        with self._cursor() as cursor:
            cursor.execute(query, params)

    def _executemany(self, query: str, rows: list[dict[str, Any]]) -> None:
        """Execute one batched SQL statement through the managed cursor."""

        with self._cursor() as cursor:
            cursor.executemany(query, rows)

    def _fetchall(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Execute one SQL read and return all fetched rows."""

        with self._cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return list(rows)
