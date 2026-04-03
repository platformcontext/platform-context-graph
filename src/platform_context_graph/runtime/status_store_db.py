"""Database implementation for PostgreSQL-backed runtime ingester status."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime
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
    COVERAGE_SCHEMA,
    STATUS_SCHEMA,
    idle_reindex_control,
    idle_scan_control,
    utc_now,
)


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
                    cursor.execute(COVERAGE_SCHEMA)
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
            cursor.execute(
                """
                SELECT ingester,
                       reindex_request_token,
                       reindex_request_state,
                       reindex_requested_at,
                       reindex_requested_by,
                       reindex_started_at,
                       reindex_completed_at,
                       reindex_error_message,
                       reindex_force,
                       reindex_scope,
                       reindex_run_id
                FROM runtime_ingester_control
                WHERE ingester = %(ingester)s
                """,
                {"ingester": ingester},
            )
            reindex_row = cursor.fetchone() or idle_reindex_control(ingester)
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

    def upsert_repository_coverage(
        self,
        *,
        run_id: str,
        repo_id: str,
        repo_name: str,
        repo_path: str,
        status: str,
        phase: str | None = None,
        finalization_status: str | None = None,
        discovered_file_count: int | None = 0,
        graph_recursive_file_count: int | None = 0,
        content_file_count: int | None = 0,
        content_entity_count: int | None = 0,
        root_file_count: int | None = 0,
        root_directory_count: int | None = 0,
        top_level_function_count: int | None = 0,
        class_method_count: int | None = 0,
        total_function_count: int | None = 0,
        class_count: int | None = 0,
        graph_available: bool = False,
        server_content_available: bool = False,
        last_error: str | None = None,
        created_at: str | datetime | None = None,
        updated_at: str | datetime | None = None,
        commit_finished_at: str | datetime | None = None,
        finalization_finished_at: str | datetime | None = None,
    ) -> None:
        """Insert or update one durable per-run repository coverage row."""

        now = utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO runtime_repository_coverage (
                    run_id,
                    repo_id,
                    repo_name,
                    repo_path,
                    status,
                    phase,
                    finalization_status,
                    discovered_file_count,
                    graph_recursive_file_count,
                    content_file_count,
                    content_entity_count,
                    root_file_count,
                    root_directory_count,
                    top_level_function_count,
                    class_method_count,
                    total_function_count,
                    class_count,
                    graph_available,
                    server_content_available,
                    last_error,
                    created_at,
                    updated_at,
                    commit_finished_at,
                    finalization_finished_at
                ) VALUES (
                    %(run_id)s,
                    %(repo_id)s,
                    %(repo_name)s,
                    %(repo_path)s,
                    %(status)s,
                    %(phase)s,
                    %(finalization_status)s,
                    %(discovered_file_count)s,
                    %(graph_recursive_file_count)s,
                    %(content_file_count)s,
                    %(content_entity_count)s,
                    %(root_file_count)s,
                    %(root_directory_count)s,
                    %(top_level_function_count)s,
                    %(class_method_count)s,
                    %(total_function_count)s,
                    %(class_count)s,
                    %(graph_available)s,
                    %(server_content_available)s,
                    %(last_error)s,
                    %(created_at)s,
                    %(updated_at)s,
                    %(commit_finished_at)s,
                    %(finalization_finished_at)s
                )
                ON CONFLICT (run_id, repo_id) DO UPDATE
                SET repo_name = EXCLUDED.repo_name,
                    repo_path = EXCLUDED.repo_path,
                    status = EXCLUDED.status,
                    phase = EXCLUDED.phase,
                    finalization_status = EXCLUDED.finalization_status,
                    discovered_file_count = EXCLUDED.discovered_file_count,
                    graph_recursive_file_count = EXCLUDED.graph_recursive_file_count,
                    content_file_count = EXCLUDED.content_file_count,
                    content_entity_count = EXCLUDED.content_entity_count,
                    root_file_count = EXCLUDED.root_file_count,
                    root_directory_count = EXCLUDED.root_directory_count,
                    top_level_function_count = EXCLUDED.top_level_function_count,
                    class_method_count = EXCLUDED.class_method_count,
                    total_function_count = EXCLUDED.total_function_count,
                    class_count = EXCLUDED.class_count,
                    graph_available = EXCLUDED.graph_available,
                    server_content_available = EXCLUDED.server_content_available,
                    last_error = EXCLUDED.last_error,
                    updated_at = EXCLUDED.updated_at,
                    commit_finished_at = EXCLUDED.commit_finished_at,
                    finalization_finished_at = EXCLUDED.finalization_finished_at
                """,
                {
                    "run_id": run_id,
                    "repo_id": repo_id,
                    "repo_name": repo_name,
                    "repo_path": repo_path,
                    "status": status,
                    "phase": phase,
                    "finalization_status": finalization_status,
                    "discovered_file_count": _normalize_count(discovered_file_count),
                    "graph_recursive_file_count": _normalize_count(
                        graph_recursive_file_count
                    ),
                    "content_file_count": _normalize_count(content_file_count),
                    "content_entity_count": _normalize_count(content_entity_count),
                    "root_file_count": _normalize_count(root_file_count),
                    "root_directory_count": _normalize_count(root_directory_count),
                    "top_level_function_count": _normalize_count(
                        top_level_function_count
                    ),
                    "class_method_count": _normalize_count(class_method_count),
                    "total_function_count": _normalize_count(total_function_count),
                    "class_count": _normalize_count(class_count),
                    "graph_available": bool(graph_available),
                    "server_content_available": bool(server_content_available),
                    "last_error": last_error,
                    "created_at": created_at or now,
                    "updated_at": updated_at or now,
                    "commit_finished_at": commit_finished_at,
                    "finalization_finished_at": finalization_finished_at,
                },
            )

    def get_repository_coverage(
        self, *, repo_id: str, run_id: str | None = None
    ) -> dict[str, Any] | None:
        """Return the latest durable coverage row for one repository."""

        with self._cursor() as cursor:
            if run_id is not None:
                cursor.execute(
                    """
                    SELECT *
                    FROM runtime_repository_coverage
                    WHERE repo_id = %(repo_id)s
                      AND run_id = %(run_id)s
                    """,
                    {"repo_id": repo_id, "run_id": run_id},
                )
            else:
                cursor.execute(
                    """
                    SELECT *
                    FROM runtime_repository_coverage
                    WHERE repo_id = %(repo_id)s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    {"repo_id": repo_id},
                )
            return cursor.fetchone()

    def update_latest_repository_coverage_finalization(
        self,
        *,
        repo_ids: list[str],
        finalization_status: str,
        finalization_finished_at: str | datetime | None,
        last_error: str | None,
        updated_at: str | datetime | None = None,
    ) -> None:
        """Update finalization-only fields on the latest coverage row per repo."""

        normalized_repo_ids = list(
            dict.fromkeys(repo_id for repo_id in repo_ids if repo_id)
        )
        if not normalized_repo_ids:
            return

        now = updated_at or utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT DISTINCT repo_id
                FROM runtime_repository_coverage
                WHERE repo_id = ANY(%(repo_ids)s)
                """,
                {"repo_ids": normalized_repo_ids},
            )
            existing_repo_ids = {
                row["repo_id"] for row in cursor.fetchall() if row.get("repo_id")
            }
            missing_repo_ids = [
                repo_id
                for repo_id in normalized_repo_ids
                if repo_id not in existing_repo_ids
            ]
            if missing_repo_ids:
                raise ValueError(
                    "Cannot repair finalization status for repositories with missing "
                    "durable coverage rows: " + ", ".join(sorted(missing_repo_ids))
                )

            cursor.execute(
                """
                WITH latest AS (
                    SELECT DISTINCT ON (repo_id) ctid, repo_id
                    FROM runtime_repository_coverage
                    WHERE repo_id = ANY(%(repo_ids)s)
                    ORDER BY repo_id, updated_at DESC
                )
                UPDATE runtime_repository_coverage AS coverage
                SET finalization_status = %(finalization_status)s,
                    finalization_finished_at = %(finalization_finished_at)s,
                    last_error = %(last_error)s,
                    updated_at = %(updated_at)s
                FROM latest
                WHERE coverage.ctid = latest.ctid
                """,
                {
                    "repo_ids": normalized_repo_ids,
                    "finalization_status": finalization_status,
                    "finalization_finished_at": finalization_finished_at,
                    "last_error": last_error,
                    "updated_at": now,
                },
            )

    def list_repository_coverage(
        self,
        *,
        run_id: str | None = None,
        only_incomplete: bool = False,
        statuses: list[str] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Return durable repository coverage rows for one run or across runs."""

        predicates: list[str] = []
        params: dict[str, Any] = {"limit": max(1, int(limit))}
        if run_id is not None:
            predicates.append("run_id = %(run_id)s")
            params["run_id"] = run_id
        if statuses:
            predicates.append("status = ANY(%(statuses)s)")
            params["statuses"] = statuses
        if only_incomplete:
            predicates.append(
                "(status NOT IN ('completed', 'skipped') "
                "OR coalesce(finalization_status, 'pending') <> 'completed')"
            )
        where_clause = ""
        if predicates:
            where_clause = "WHERE " + " AND ".join(predicates)
        with self._cursor() as cursor:
            cursor.execute(
                f"""
                SELECT *
                FROM runtime_repository_coverage
                {where_clause}
                ORDER BY updated_at DESC, repo_id
                LIMIT %(limit)s
                """,
                params,
            )
            return list(cursor.fetchall())

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

    def request_reindex(
        self,
        *,
        ingester: str,
        requested_by: str = "api",
        force: bool = True,
        scope: str = "workspace",
    ) -> dict[str, Any]:
        """Persist a pending manual ingester reindex request."""

        request_token = str(uuid4())
        requested_at = utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO runtime_ingester_control (
                    ingester,
                    reindex_request_token,
                    reindex_request_state,
                    reindex_requested_at,
                    reindex_requested_by,
                    reindex_started_at,
                    reindex_completed_at,
                    reindex_error_message,
                    reindex_force,
                    reindex_scope,
                    reindex_run_id,
                    updated_at
                ) VALUES (
                    %(ingester)s,
                    %(reindex_request_token)s,
                    %(reindex_request_state)s,
                    %(reindex_requested_at)s,
                    %(reindex_requested_by)s,
                    NULL,
                    NULL,
                    NULL,
                    %(reindex_force)s,
                    %(reindex_scope)s,
                    NULL,
                    %(updated_at)s
                )
                ON CONFLICT (ingester) DO UPDATE
                SET reindex_request_token = EXCLUDED.reindex_request_token,
                    reindex_request_state = EXCLUDED.reindex_request_state,
                    reindex_requested_at = EXCLUDED.reindex_requested_at,
                    reindex_requested_by = EXCLUDED.reindex_requested_by,
                    reindex_started_at = NULL,
                    reindex_completed_at = NULL,
                    reindex_error_message = NULL,
                    reindex_force = EXCLUDED.reindex_force,
                    reindex_scope = EXCLUDED.reindex_scope,
                    reindex_run_id = NULL,
                    updated_at = EXCLUDED.updated_at
                RETURNING ingester,
                          reindex_request_token,
                          reindex_request_state,
                          reindex_requested_at,
                          reindex_requested_by,
                          reindex_started_at,
                          reindex_completed_at,
                          reindex_error_message,
                          reindex_force AS requested_force,
                          reindex_scope AS requested_scope,
                          reindex_run_id AS run_id
                """,
                {
                    "ingester": ingester,
                    "reindex_request_token": request_token,
                    "reindex_request_state": "pending",
                    "reindex_requested_at": requested_at,
                    "reindex_requested_by": requested_by,
                    "reindex_force": force,
                    "reindex_scope": scope,
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

    def claim_reindex_request(self, *, ingester: str) -> dict[str, Any] | None:
        """Atomically claim the next pending reindex request for an ingester."""

        started_at = utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE runtime_ingester_control
                SET reindex_request_state = %(reindex_request_state)s,
                    reindex_started_at = %(reindex_started_at)s,
                    updated_at = %(updated_at)s
                WHERE ingester = %(ingester)s
                  AND reindex_request_state = 'pending'
                RETURNING ingester,
                          reindex_request_token,
                          reindex_request_state,
                          reindex_requested_at,
                          reindex_requested_by,
                          reindex_started_at,
                          reindex_completed_at,
                          reindex_error_message,
                          reindex_force AS requested_force,
                          reindex_scope AS requested_scope,
                          reindex_run_id AS run_id
                """,
                {
                    "ingester": ingester,
                    "reindex_request_state": "running",
                    "reindex_started_at": started_at,
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

    def complete_reindex_request(
        self,
        *,
        ingester: str,
        request_token: str,
        error_message: str | None = None,
    ) -> None:
        """Mark one claimed reindex request completed or failed."""

        completed_at = utc_now()
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE runtime_ingester_control
                SET reindex_request_state = %(reindex_request_state)s,
                    reindex_completed_at = %(reindex_completed_at)s,
                    reindex_error_message = %(reindex_error_message)s,
                    updated_at = %(updated_at)s
                WHERE ingester = %(ingester)s
                  AND reindex_request_token = %(reindex_request_token)s
                """,
                {
                    "ingester": ingester,
                    "reindex_request_token": request_token,
                    "reindex_request_state": (
                        "failed" if error_message is not None else "completed"
                    ),
                    "reindex_completed_at": completed_at,
                    "reindex_error_message": error_message,
                    "updated_at": completed_at,
                },
            )
