from __future__ import annotations

from contextlib import contextmanager

from platform_context_graph.runtime.status_store_db import PostgresRuntimeStatusStore


class _Cursor:
    """Minimal fake cursor for deterministic status-store reads."""

    def __init__(self, rows: list[dict[str, object] | None]) -> None:
        self._rows = rows
        self.executed: list[str] = []

    def execute(self, query: str, _params: dict[str, object]) -> None:
        """Record each executed query for debugging."""

        self.executed.append(query)

    def fetchone(self) -> dict[str, object] | None:
        """Return the next queued row."""

        if not self._rows:
            return None
        return self._rows.pop(0)


def test_get_runtime_status_excludes_reindex_control_fields(monkeypatch) -> None:
    """Generic ingester status payloads should omit reindex control internals."""

    status_row = {
        "ingester": "repository",
        "source_mode": "githubOrg",
        "status": "idle",
        "active_run_id": "run-123",
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
        "repository_count": 3,
        "pulled_repositories": 3,
        "in_sync_repositories": 3,
        "pending_repositories": 0,
        "completed_repositories": 3,
        "failed_repositories": 0,
        "updated_at": None,
    }
    control_row = {
        "ingester": "repository",
        "scan_request_token": "scan-123",
        "scan_request_state": "completed",
        "scan_requested_at": None,
        "scan_requested_by": "api",
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
    }
    reindex_row = {
        "ingester": "repository",
        "reindex_request_token": "reindex-123",
        "reindex_request_state": "pending",
        "reindex_requested_at": "2026-04-02T16:00:00+00:00",
        "reindex_requested_by": "api",
        "reindex_started_at": None,
        "reindex_completed_at": None,
        "reindex_error_message": None,
        "reindex_force": True,
        "reindex_scope": "workspace",
        "reindex_run_id": None,
    }
    cursor = _Cursor([status_row, control_row, reindex_row])
    store = PostgresRuntimeStatusStore("postgresql://example.test/runtime")

    @contextmanager
    def _fake_cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _fake_cursor)

    payload = store.get_runtime_status(ingester="repository")

    assert payload is not None
    assert payload["scan_request_token"] == "scan-123"
    assert "reindex_request_token" not in payload
    assert "reindex_requested_at" not in payload

