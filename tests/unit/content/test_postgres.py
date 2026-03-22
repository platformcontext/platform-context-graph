"""Unit tests for the PostgreSQL content provider."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from platform_context_graph.content.postgres import PostgresContentProvider
from platform_context_graph.runtime.status_store import PostgresRuntimeStatusStore


def test_delete_repository_content_removes_entities_and_files(monkeypatch) -> None:
    """Deleting repository content should purge entity and file rows for one repo."""

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.delete_repository_content("repository:r_test")

    queries = [call.args[0] for call in cursor.execute.call_args_list]
    params = [call.args[1] for call in cursor.execute.call_args_list]
    assert queries == [
        """
                DELETE FROM content_entities
                WHERE repo_id = %(repo_id)s
                """,
        """
                DELETE FROM content_files
                WHERE repo_id = %(repo_id)s
                """,
    ]
    assert params == [
        {"repo_id": "repository:r_test"},
        {"repo_id": "repository:r_test"},
    ]


def test_upsert_runtime_status_persists_worker_status(monkeypatch) -> None:
    """Worker status writes should upsert into the runtime status table."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_runtime_status(
        component="repo-sync",
        source_mode="githubOrg",
        status="degraded",
        active_run_id="run-123",
        last_attempt_at="2026-03-22T12:00:00+00:00",
        last_success_at="2026-03-22T11:00:00+00:00",
        next_retry_at="2026-03-22T12:05:00+00:00",
        last_error_kind="dns",
        last_error_message="temporary failure in name resolution",
        repository_count=200,
        pending_repositories=200,
        completed_repositories=0,
        failed_repositories=0,
    )

    query, params = cursor.execute.call_args.args
    assert "INSERT INTO runtime_worker_status" in query
    assert params["component"] == "repo-sync"
    assert params["status"] == "degraded"
    assert params["active_run_id"] == "run-123"
    assert params["last_error_kind"] == "dns"
    assert params["pending_repositories"] == 200


def test_get_runtime_status_returns_persisted_row(monkeypatch) -> None:
    """Worker status reads should return the latest row for one component."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "component": "repo-sync",
        "source_mode": "githubOrg",
        "status": "idle",
        "active_run_id": "run-123",
        "last_attempt_at": "2026-03-22T12:00:00+00:00",
        "last_success_at": "2026-03-22T12:01:00+00:00",
        "next_retry_at": None,
        "last_error_kind": None,
        "last_error_message": None,
        "repository_count": 200,
        "pending_repositories": 0,
        "completed_repositories": 200,
        "failed_repositories": 0,
        "updated_at": "2026-03-22T12:01:00+00:00",
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.get_runtime_status(component="repo-sync")

    assert result["component"] == "repo-sync"
    assert result["status"] == "idle"
    assert result["completed_repositories"] == 200
