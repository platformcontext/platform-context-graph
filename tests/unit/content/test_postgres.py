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


def test_upsert_runtime_status_persists_ingester_status(monkeypatch) -> None:
    """Ingester status writes should upsert into the runtime status table."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_runtime_status(
        ingester="repository",
        source_mode="githubOrg",
        status="degraded",
        active_run_id="run-123",
        last_attempt_at="2026-03-22T12:00:00+00:00",
        last_success_at="2026-03-22T11:00:00+00:00",
        next_retry_at="2026-03-22T12:05:00+00:00",
        last_error_kind="dns",
        last_error_message="temporary failure in name resolution",
        repository_count=200,
        pulled_repositories=180,
        in_sync_repositories=160,
        pending_repositories=200,
        completed_repositories=0,
        failed_repositories=0,
    )

    query, params = cursor.execute.call_args.args
    assert "INSERT INTO runtime_ingester_status" in query
    assert params["ingester"] == "repository"
    assert params["status"] == "degraded"
    assert params["active_run_id"] == "run-123"
    assert params["last_error_kind"] == "dns"
    assert params["pulled_repositories"] == 180
    assert params["in_sync_repositories"] == 160
    assert params["pending_repositories"] == 200


def test_get_runtime_status_returns_persisted_row(monkeypatch) -> None:
    """Ingester status reads should return the latest row for one ingester."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "ingester": "repository",
        "source_mode": "githubOrg",
        "status": "idle",
        "active_run_id": "run-123",
        "last_attempt_at": "2026-03-22T12:00:00+00:00",
        "last_success_at": "2026-03-22T12:01:00+00:00",
        "next_retry_at": None,
        "last_error_kind": None,
        "last_error_message": None,
        "repository_count": 200,
        "pulled_repositories": 200,
        "in_sync_repositories": 200,
        "pending_repositories": 0,
        "completed_repositories": 200,
        "failed_repositories": 0,
        "scan_request_state": "idle",
        "scan_request_token": None,
        "scan_requested_at": None,
        "scan_requested_by": None,
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
        "updated_at": "2026-03-22T12:01:00+00:00",
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.get_runtime_status(ingester="repository")

    assert result["ingester"] == "repository"
    assert result["status"] == "idle"
    assert result["completed_repositories"] == 200
    assert result["pulled_repositories"] == 200
    assert result["in_sync_repositories"] == 200
    assert result["scan_request_state"] == "idle"


def test_request_scan_persists_pending_ingester_control(monkeypatch) -> None:
    """Requesting a scan should upsert a pending ingester control row."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "ingester": "repository",
        "scan_request_token": "scan-123",
        "scan_request_state": "pending",
        "scan_requested_at": "2026-03-22T12:10:00+00:00",
        "scan_requested_by": "api",
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.request_scan(ingester="repository", requested_by="api")

    query, params = cursor.execute.call_args.args
    assert "INSERT INTO runtime_ingester_control" in query
    assert params["ingester"] == "repository"
    assert params["scan_requested_by"] == "api"
    assert result["scan_request_state"] == "pending"


def test_claim_scan_request_marks_it_running(monkeypatch) -> None:
    """Claiming a pending ingester scan should transition it to running."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "ingester": "repository",
        "scan_request_token": "scan-123",
        "scan_request_state": "running",
        "scan_requested_at": "2026-03-22T12:10:00+00:00",
        "scan_requested_by": "api",
        "scan_started_at": "2026-03-22T12:10:05+00:00",
        "scan_completed_at": None,
        "scan_error_message": None,
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    result = store.claim_scan_request(ingester="repository")

    query, params = cursor.execute.call_args.args
    assert "UPDATE runtime_ingester_control" in query
    assert params["ingester"] == "repository"
    assert result["scan_request_state"] == "running"


def test_complete_scan_request_marks_it_completed(monkeypatch) -> None:
    """Completing an ingester scan request should persist the terminal state."""

    store = PostgresRuntimeStatusStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.complete_scan_request(ingester="repository", request_token="scan-123")

    query, params = cursor.execute.call_args.args
    assert "UPDATE runtime_ingester_control" in query
    assert params["ingester"] == "repository"
    assert params["scan_request_token"] == "scan-123"
    assert params["scan_request_state"] == "completed"
