"""Tests for listing filtered fact work items."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.facts.work_queue.postgres import PostgresFactWorkQueue


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for work-item listing tests."""

    return datetime(2026, 4, 3, 17, 15, tzinfo=timezone.utc)


def test_list_work_items_preserves_status_and_failure_filters(monkeypatch) -> None:
    """Work-item listing should carry status and failure filters into SQL."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "work_item_id": "work-1",
            "work_type": "project-git-facts",
            "repository_id": "repository:r_payments",
            "source_run_id": "run-123",
            "lease_owner": "indexing",
            "lease_expires_at": None,
            "status": "failed",
            "attempt_count": 3,
            "last_error": "boom",
            "failure_stage": "project_work_item",
            "error_class": "TimeoutError",
            "failure_class": "timeout",
            "failure_code": "timeout_error",
            "retry_disposition": "retryable",
            "dead_lettered_at": _utc_now(),
            "last_attempt_started_at": _utc_now(),
            "last_attempt_finished_at": _utc_now(),
            "next_retry_at": None,
            "operator_note": "watch",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    rows = queue.list_work_items(
        statuses=["failed"],
        repository_id="repository:r_payments",
        failure_class="timeout",
        limit=25,
    )

    query, params = cursor.execute.call_args.args
    assert "status = ANY(%(statuses)s::text[])" in query
    assert "repository_id = %(repository_id)s" in query
    assert "failure_class = %(failure_class)s" in query
    assert params["statuses"] == ["failed"]
    assert params["failure_class"] == "timeout"
    assert params["limit"] == 25
    assert rows[0].work_item_id == "work-1"
    assert rows[0].lease_owner == "indexing"


def test_list_work_items_omits_status_filter_when_statuses_are_absent(
    monkeypatch,
) -> None:
    """Work-item listing should not bind a status array when no filter is set."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = []

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    queue.list_work_items(limit=10)

    query, params = cursor.execute.call_args.args
    assert "status = ANY(%(statuses)s::text[])" not in query
    assert "WHERE" not in query
    assert "statuses" not in params
    assert params["limit"] == 10
