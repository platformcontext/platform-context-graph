from __future__ import annotations

from contextlib import contextmanager

from platform_context_graph.runtime.status_store_db import PostgresRuntimeStatusStore


class _Cursor:
    """Minimal fake cursor for deterministic shared-projection status reads."""

    def __init__(self, rows: list[dict[str, object] | None]) -> None:
        self._rows = rows

    def execute(self, _query: str, _params: dict[str, object]) -> None:
        """Accept the issued query without extra bookkeeping."""

    def fetchone(self) -> dict[str, object] | None:
        """Return the next queued row."""

        if not self._rows:
            return None
        return self._rows.pop(0)


def test_get_runtime_status_includes_shared_projection_pending_count(
    monkeypatch,
) -> None:
    """Runtime status should preserve shared-projection pending counts."""

    status_row = {
        "ingester": "repository",
        "source_mode": "githubOrg",
        "status": "indexing",
        "active_run_id": "run-123",
        "active_repository_path": None,
        "active_phase": "awaiting_shared_projection",
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
        "in_sync_repositories": 1,
        "pending_repositories": 2,
        "completed_repositories": 1,
        "failed_repositories": 0,
        "shared_projection_pending_repositories": 2,
        "updated_at": None,
    }
    control_row = {
        "ingester": "repository",
        "scan_request_token": None,
        "scan_request_state": "idle",
        "scan_requested_at": None,
        "scan_requested_by": None,
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
    }
    reindex_row = {
        "ingester": "repository",
        "reindex_request_token": None,
        "reindex_request_state": "idle",
        "reindex_requested_at": None,
        "reindex_requested_by": None,
        "reindex_started_at": None,
        "reindex_completed_at": None,
        "reindex_error_message": None,
        "reindex_force": True,
        "reindex_scope": None,
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
    assert payload["shared_projection_pending_repositories"] == 2
