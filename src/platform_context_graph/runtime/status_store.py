"""PostgreSQL-backed runtime ingester status persistence."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised when optional dependency missing.
    psycopg = None
    dict_row = None

from .status_store_support import (
    CONTROL_SCHEMA,
    STATUS_SCHEMA,
    idle_scan_control,
    utc_now,
)

__all__ = [
    "claim_ingester_scan_request",
    "complete_ingester_scan_request",
    "get_runtime_status_store",
    "request_ingester_scan",
    "reset_runtime_status_store_for_tests",
    "update_runtime_ingester_status",
]

_STORE_LOCK = threading.Lock()
_STORE: PostgresRuntimeStatusStore | None = None
_COUNT_FIELDS = frozenset(
    {
        "repository_count",
        "pulled_repositories",
        "in_sync_repositories",
        "pending_repositories",
        "completed_repositories",
        "failed_repositories",
    }
)


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


def _normalize_count(value: int | None) -> int:
    """Normalize nullable repository count fields before persistence."""

    return 0 if value is None else int(value)


class PostgresRuntimeStatusStore:
    """Persist ingester runtime status in PostgreSQL."""

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
                    cursor.execute(STATUS_SCHEMA)
                    cursor.execute(CONTROL_SCHEMA)
                self._initialized = True
            with self._conn.cursor() as cursor:
                yield cursor

    def upsert_runtime_status(
        self,
        *,
        ingester: str,
        source_mode: str | None,
        status: str,
        active_run_id: str | None = None,
        active_repository_path: str | None = None,
        active_phase: str | None = None,
        active_phase_started_at: str | datetime | None = None,
        active_current_file: str | None = None,
        active_last_progress_at: str | datetime | None = None,
        active_commit_started_at: str | datetime | None = None,
        last_attempt_at: str | datetime | None = None,
        last_success_at: str | datetime | None = None,
        next_retry_at: str | datetime | None = None,
        last_error_kind: str | None = None,
        last_error_message: str | None = None,
        repository_count: int | None = 0,
        pulled_repositories: int | None = 0,
        in_sync_repositories: int | None = 0,
        pending_repositories: int | None = 0,
        completed_repositories: int | None = 0,
        failed_repositories: int | None = 0,
    ) -> None:
        """Insert or update one ingester status row."""

        repository_count = _normalize_count(repository_count)
        pulled_repositories = _normalize_count(pulled_repositories)
        in_sync_repositories = _normalize_count(in_sync_repositories)
        pending_repositories = _normalize_count(pending_repositories)
        completed_repositories = _normalize_count(completed_repositories)
        failed_repositories = _normalize_count(failed_repositories)

        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO runtime_ingester_status (
                    ingester,
                    source_mode,
                    status,
                    active_run_id,
                    active_repository_path,
                    active_phase,
                    active_phase_started_at,
                    active_current_file,
                    active_last_progress_at,
                    active_commit_started_at,
                    last_attempt_at,
                    last_success_at,
                    next_retry_at,
                    last_error_kind,
                    last_error_message,
                    repository_count,
                    pulled_repositories,
                    in_sync_repositories,
                    pending_repositories,
                    completed_repositories,
                    failed_repositories,
                    updated_at
                ) VALUES (
                    %(ingester)s,
                    %(source_mode)s,
                    %(status)s,
                    %(active_run_id)s,
                    %(active_repository_path)s,
                    %(active_phase)s,
                    %(active_phase_started_at)s,
                    %(active_current_file)s,
                    %(active_last_progress_at)s,
                    %(active_commit_started_at)s,
                    %(last_attempt_at)s,
                    %(last_success_at)s,
                    %(next_retry_at)s,
                    %(last_error_kind)s,
                    %(last_error_message)s,
                    %(repository_count)s,
                    %(pulled_repositories)s,
                    %(in_sync_repositories)s,
                    %(pending_repositories)s,
                    %(completed_repositories)s,
                    %(failed_repositories)s,
                    %(updated_at)s
                )
                ON CONFLICT (ingester) DO UPDATE
                SET source_mode = EXCLUDED.source_mode,
                    status = EXCLUDED.status,
                    active_run_id = EXCLUDED.active_run_id,
                    active_repository_path = EXCLUDED.active_repository_path,
                    active_phase = EXCLUDED.active_phase,
                    active_phase_started_at = EXCLUDED.active_phase_started_at,
                    active_current_file = EXCLUDED.active_current_file,
                    active_last_progress_at = EXCLUDED.active_last_progress_at,
                    active_commit_started_at = EXCLUDED.active_commit_started_at,
                    last_attempt_at = EXCLUDED.last_attempt_at,
                    last_success_at = EXCLUDED.last_success_at,
                    next_retry_at = EXCLUDED.next_retry_at,
                    last_error_kind = EXCLUDED.last_error_kind,
                    last_error_message = EXCLUDED.last_error_message,
                    repository_count = EXCLUDED.repository_count,
                    pulled_repositories = EXCLUDED.pulled_repositories,
                    in_sync_repositories = EXCLUDED.in_sync_repositories,
                    pending_repositories = EXCLUDED.pending_repositories,
                    completed_repositories = EXCLUDED.completed_repositories,
                    failed_repositories = EXCLUDED.failed_repositories,
                    updated_at = EXCLUDED.updated_at
                """,
                {
                    "ingester": ingester,
                    "source_mode": source_mode,
                    "status": status,
                    "active_run_id": active_run_id,
                    "active_repository_path": active_repository_path,
                    "active_phase": active_phase,
                    "active_phase_started_at": active_phase_started_at,
                    "active_current_file": active_current_file,
                    "active_last_progress_at": active_last_progress_at,
                    "active_commit_started_at": active_commit_started_at,
                    "last_attempt_at": last_attempt_at,
                    "last_success_at": last_success_at,
                    "next_retry_at": next_retry_at,
                    "last_error_kind": last_error_kind,
                    "last_error_message": last_error_message,
                    "repository_count": repository_count,
                    "pulled_repositories": pulled_repositories,
                    "in_sync_repositories": in_sync_repositories,
                    "pending_repositories": pending_repositories,
                    "completed_repositories": completed_repositories,
                    "failed_repositories": failed_repositories,
                    "updated_at": utc_now(),
                },
            )

    def get_runtime_status(self, *, ingester: str) -> dict[str, Any] | None:
        """Return the persisted runtime status for one ingester."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT ingester,
                       source_mode,
                       status,
                       active_run_id,
                       active_repository_path,
                       active_phase,
                       active_phase_started_at,
                       active_current_file,
                       active_last_progress_at,
                       active_commit_started_at,
                       last_attempt_at,
                       last_success_at,
                       next_retry_at,
                       last_error_kind,
                       last_error_message,
                       repository_count,
                       pulled_repositories,
                       in_sync_repositories,
                       pending_repositories,
                       completed_repositories,
                       failed_repositories,
                       updated_at
                FROM runtime_ingester_status
                WHERE ingester = %(ingester)s
                """,
                {"ingester": ingester},
            )
            status_row = cursor.fetchone()
            cursor.execute(
                """
                SELECT ingester,
                       scan_request_token,
                       scan_request_state,
                       scan_requested_at,
                       scan_requested_by,
                       scan_started_at,
                       scan_completed_at,
                       scan_error_message
                FROM runtime_ingester_control
                WHERE ingester = %(ingester)s
                """,
                {"ingester": ingester},
            )
            control_row = cursor.fetchone() or idle_scan_control(ingester)
            if status_row is None:
                if control_row["scan_request_state"] == "idle":
                    return None
                return {
                    "runtime_family": "ingester",
                    "ingester": ingester,
                    "provider": ingester,
                    "source_mode": None,
                    "status": "bootstrap_pending",
                    "active_run_id": None,
                    "active_repository_path": None,
                    "active_phase": None,
                    "active_phase_started_at": None,
                    "active_current_file": None,
                    "active_last_progress_at": None,
                    "active_commit_started_at": None,
                    "last_attempt_at": None,
                    "last_success_at": None,
                    "next_retry_at": None,
                    "last_error_kind": None,
                    "last_error_message": None,
                    "repository_count": 0,
                    "pulled_repositories": 0,
                    "in_sync_repositories": 0,
                    "pending_repositories": 0,
                    "completed_repositories": 0,
                    "failed_repositories": 0,
                    "updated_at": None,
                    **control_row,
                }
            merged = {
                "runtime_family": "ingester",
                "provider": ingester,
                **dict(status_row),
            }
            merged.update(control_row)
            return merged

    def request_scan(
        self,
        *,
        ingester: str,
        requested_by: str = "api",
    ) -> dict[str, Any]:
        """Persist a pending manual ingester scan request."""

        request_token = str(uuid4())
        requested_at = utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO runtime_ingester_control (
                    ingester,
                    scan_request_token,
                    scan_request_state,
                    scan_requested_at,
                    scan_requested_by,
                    scan_started_at,
                    scan_completed_at,
                    scan_error_message,
                    updated_at
                ) VALUES (
                    %(ingester)s,
                    %(scan_request_token)s,
                    %(scan_request_state)s,
                    %(scan_requested_at)s,
                    %(scan_requested_by)s,
                    NULL,
                    NULL,
                    NULL,
                    %(updated_at)s
                )
                ON CONFLICT (ingester) DO UPDATE
                SET scan_request_token = EXCLUDED.scan_request_token,
                    scan_request_state = EXCLUDED.scan_request_state,
                    scan_requested_at = EXCLUDED.scan_requested_at,
                    scan_requested_by = EXCLUDED.scan_requested_by,
                    scan_started_at = NULL,
                    scan_completed_at = NULL,
                    scan_error_message = NULL,
                    updated_at = EXCLUDED.updated_at
                RETURNING ingester,
                          scan_request_token,
                          scan_request_state,
                          scan_requested_at,
                          scan_requested_by,
                          scan_started_at,
                          scan_completed_at,
                          scan_error_message
                """,
                {
                    "ingester": ingester,
                    "scan_request_token": request_token,
                    "scan_request_state": "pending",
                    "scan_requested_at": requested_at,
                    "scan_requested_by": requested_by,
                    "updated_at": requested_at,
                },
            )
            return cursor.fetchone()

    def claim_scan_request(self, *, ingester: str) -> dict[str, Any] | None:
        """Atomically claim the next pending scan request for an ingester."""

        started_at = utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE runtime_ingester_control
                SET scan_request_state = %(scan_request_state)s,
                    scan_started_at = %(scan_started_at)s,
                    updated_at = %(updated_at)s
                WHERE ingester = %(ingester)s
                  AND scan_request_state = 'pending'
                RETURNING ingester,
                          scan_request_token,
                          scan_request_state,
                          scan_requested_at,
                          scan_requested_by,
                          scan_started_at,
                          scan_completed_at,
                          scan_error_message
                """,
                {
                    "ingester": ingester,
                    "scan_request_state": "running",
                    "scan_started_at": started_at,
                    "updated_at": started_at,
                },
            )
            return cursor.fetchone()

    def complete_scan_request(
        self,
        *,
        ingester: str,
        request_token: str,
        error_message: str | None = None,
    ) -> None:
        """Mark one claimed scan request completed or failed."""

        completed_at = utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE runtime_ingester_control
                SET scan_request_state = %(scan_request_state)s,
                    scan_completed_at = %(scan_completed_at)s,
                    scan_error_message = %(scan_error_message)s,
                    updated_at = %(updated_at)s
                WHERE ingester = %(ingester)s
                  AND scan_request_token = %(scan_request_token)s
                """,
                {
                    "ingester": ingester,
                    "scan_request_token": request_token,
                    "scan_request_state": (
                        "failed" if error_message is not None else "completed"
                    ),
                    "scan_completed_at": completed_at,
                    "scan_error_message": error_message,
                    "updated_at": completed_at,
                },
            )


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


def update_runtime_ingester_status(**kwargs: Any) -> None:
    """Persist ingester status when the runtime status store is configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return
    for key in _COUNT_FIELDS:
        if key in kwargs:
            kwargs[key] = _normalize_count(kwargs[key])
    store.upsert_runtime_status(**kwargs)


def request_ingester_scan(
    *, ingester: str, requested_by: str = "api"
) -> dict[str, Any] | None:
    """Persist a manual ingester scan request when the status store is configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return None
    return store.request_scan(ingester=ingester, requested_by=requested_by)


def claim_ingester_scan_request(*, ingester: str) -> dict[str, Any] | None:
    """Claim the next pending manual ingester scan request when configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return None
    return store.claim_scan_request(ingester=ingester)


def complete_ingester_scan_request(
    *,
    ingester: str,
    request_token: str,
    error_message: str | None = None,
) -> None:
    """Mark one claimed ingester scan request completed when configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return
    store.complete_scan_request(
        ingester=ingester,
        request_token=request_token,
        error_message=error_message,
    )


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
