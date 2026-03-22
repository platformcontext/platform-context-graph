"""PostgreSQL-backed runtime worker status persistence."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised when optional dependency missing.
    psycopg = None
    dict_row = None

__all__ = [
    "get_runtime_status_store",
    "reset_runtime_status_store_for_tests",
    "update_runtime_status",
]

_STATUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_worker_status (
    component TEXT PRIMARY KEY,
    source_mode TEXT,
    status TEXT NOT NULL,
    active_run_id TEXT,
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,
    last_error_kind TEXT,
    last_error_message TEXT,
    repository_count INTEGER NOT NULL DEFAULT 0,
    pending_repositories INTEGER NOT NULL DEFAULT 0,
    completed_repositories INTEGER NOT NULL DEFAULT 0,
    failed_repositories INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL
);
"""

_STORE_LOCK = threading.Lock()
_STORE: PostgresRuntimeStatusStore | None = None


def _content_store_enabled() -> bool:
    """Return whether PostgreSQL-backed runtime status should be attempted."""

    raw = os.getenv("PCG_CONTENT_STORE_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _dsn() -> str | None:
    """Return the configured PostgreSQL DSN, if any."""

    for key in ("PCG_CONTENT_STORE_DSN", "PCG_POSTGRES_DSN"):
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


class PostgresRuntimeStatusStore:
    """Persist worker runtime status in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Bind the status store to a PostgreSQL DSN."""

        self._dsn = dsn
        self._lock = threading.Lock()
        self._conn: Any | None = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        """Return whether the status store is usable in the current process."""

        return psycopg is not None and bool(self._dsn)

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor and initialize schema on first use."""

        if not self.enabled:
            raise RuntimeError("runtime status store requires psycopg and a DSN")

        with self._lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            if not self._initialized:
                with self._conn.cursor() as cursor:
                    cursor.execute(_STATUS_SCHEMA)
                self._initialized = True
            with self._conn.cursor() as cursor:
                yield cursor

    def upsert_runtime_status(
        self,
        *,
        component: str,
        source_mode: str | None,
        status: str,
        active_run_id: str | None = None,
        last_attempt_at: str | datetime | None = None,
        last_success_at: str | datetime | None = None,
        next_retry_at: str | datetime | None = None,
        last_error_kind: str | None = None,
        last_error_message: str | None = None,
        repository_count: int = 0,
        pending_repositories: int = 0,
        completed_repositories: int = 0,
        failed_repositories: int = 0,
    ) -> None:
        """Insert or update one worker status row."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO runtime_worker_status (
                    component,
                    source_mode,
                    status,
                    active_run_id,
                    last_attempt_at,
                    last_success_at,
                    next_retry_at,
                    last_error_kind,
                    last_error_message,
                    repository_count,
                    pending_repositories,
                    completed_repositories,
                    failed_repositories,
                    updated_at
                ) VALUES (
                    %(component)s,
                    %(source_mode)s,
                    %(status)s,
                    %(active_run_id)s,
                    %(last_attempt_at)s,
                    %(last_success_at)s,
                    %(next_retry_at)s,
                    %(last_error_kind)s,
                    %(last_error_message)s,
                    %(repository_count)s,
                    %(pending_repositories)s,
                    %(completed_repositories)s,
                    %(failed_repositories)s,
                    %(updated_at)s
                )
                ON CONFLICT (component) DO UPDATE
                SET source_mode = EXCLUDED.source_mode,
                    status = EXCLUDED.status,
                    active_run_id = EXCLUDED.active_run_id,
                    last_attempt_at = EXCLUDED.last_attempt_at,
                    last_success_at = EXCLUDED.last_success_at,
                    next_retry_at = EXCLUDED.next_retry_at,
                    last_error_kind = EXCLUDED.last_error_kind,
                    last_error_message = EXCLUDED.last_error_message,
                    repository_count = EXCLUDED.repository_count,
                    pending_repositories = EXCLUDED.pending_repositories,
                    completed_repositories = EXCLUDED.completed_repositories,
                    failed_repositories = EXCLUDED.failed_repositories,
                    updated_at = EXCLUDED.updated_at
                """,
                {
                    "component": component,
                    "source_mode": source_mode,
                    "status": status,
                    "active_run_id": active_run_id,
                    "last_attempt_at": last_attempt_at,
                    "last_success_at": last_success_at,
                    "next_retry_at": next_retry_at,
                    "last_error_kind": last_error_kind,
                    "last_error_message": last_error_message,
                    "repository_count": repository_count,
                    "pending_repositories": pending_repositories,
                    "completed_repositories": completed_repositories,
                    "failed_repositories": failed_repositories,
                    "updated_at": _utc_now(),
                },
            )

    def get_runtime_status(self, *, component: str) -> dict[str, Any] | None:
        """Return the persisted runtime status for one component."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT component,
                       source_mode,
                       status,
                       active_run_id,
                       last_attempt_at,
                       last_success_at,
                       next_retry_at,
                       last_error_kind,
                       last_error_message,
                       repository_count,
                       pending_repositories,
                       completed_repositories,
                       failed_repositories,
                       updated_at
                FROM runtime_worker_status
                WHERE component = %(component)s
                """,
                {"component": component},
            )
            return cursor.fetchone()


def get_runtime_status_store() -> PostgresRuntimeStatusStore | None:
    """Return the shared runtime status store when configured."""

    global _STORE
    if not _content_store_enabled():
        return None
    dsn = _dsn()
    if not dsn:
        return None
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = PostgresRuntimeStatusStore(dsn)
        return _STORE


def update_runtime_status(**kwargs: Any) -> None:
    """Persist worker status when the runtime status store is configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return
    store.upsert_runtime_status(**kwargs)


def reset_runtime_status_store_for_tests() -> None:
    """Clear the shared runtime status store singleton."""

    global _STORE
    with _STORE_LOCK:
        if _STORE is not None and getattr(_STORE, "_conn", None) is not None:
            try:
                _STORE._conn.close()
            except Exception:
                pass
        _STORE = None
