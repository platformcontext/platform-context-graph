"""Tests for the Postgres-backed fact work queue."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.facts.work_queue.postgres import PostgresFactWorkQueue


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for queue tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_enqueue_work_item_persists_pending_row(monkeypatch) -> None:
    """Enqueue should write a pending work item row."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    queue.enqueue_work_item(
        FactWorkItemRow(
            work_item_id="work-1",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
            status="pending",
            attempt_count=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )

    query, params = cursor.execute.call_args.args
    assert "INSERT INTO fact_work_items" in query
    assert params["status"] == "pending"
    assert params["work_type"] == "project-git-facts"


def test_claim_work_item_returns_leased_row(monkeypatch) -> None:
    """Claiming should return a leased work item when one is available."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "work_item_id": "work-1",
        "work_type": "project-git-facts",
        "repository_id": "github.com/acme/service",
        "source_run_id": "run-123",
        "lease_owner": "resolution-worker-1",
        "lease_expires_at": _utc_now(),
        "status": "leased",
        "attempt_count": 1,
        "last_error": None,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    row = queue.claim_work_item(
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    assert row is not None
    assert row.work_item_id == "work-1"
    assert row.lease_owner == "resolution-worker-1"
    assert row.status == "leased"


def test_claim_work_item_can_reclaim_expired_leased_rows(monkeypatch) -> None:
    """Expired inline-owned leases should be reclaimable by the resolution engine."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = None

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    queue.claim_work_item(
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    query, _params = cursor.execute.call_args.args
    assert "status = 'pending'" in query
    assert "status = 'leased'" in query
    assert "lease_expires_at <= %(now)s" in query


def test_fail_work_item_marks_retryable_and_terminal_states(monkeypatch) -> None:
    """Failing work should support retryable and terminal outcomes."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    queue.fail_work_item(work_item_id="work-1", error_message="boom", terminal=False)
    retry_query, retry_params = cursor.execute.call_args.args

    assert "attempt_count =" not in retry_query
    assert retry_params["status"] == "pending"
    assert retry_params["last_error"] == "boom"

    queue.fail_work_item(work_item_id="work-1", error_message="fatal", terminal=True)
    terminal_query, terminal_params = cursor.execute.call_args.args

    assert terminal_params["status"] == "failed"
    assert terminal_params["last_error"] == "fatal"


def test_lease_work_item_targets_one_pending_row(monkeypatch) -> None:
    """Leasing a known work item should return that specific row."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "work_item_id": "work-1",
        "work_type": "project-git-facts",
        "repository_id": "github.com/acme/service",
        "source_run_id": "run-123",
        "lease_owner": "indexing-worker-1",
        "lease_expires_at": _utc_now(),
        "status": "leased",
        "attempt_count": 1,
        "last_error": None,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    row = queue.lease_work_item(
        work_item_id="work-1",
        lease_owner="indexing-worker-1",
        lease_ttl_seconds=60,
    )

    assert row is not None
    assert row.work_item_id == "work-1"
    query, params = cursor.execute.call_args.args
    assert "WHERE work_item_id = %(work_item_id)s" in query
    assert params["work_item_id"] == "work-1"


def test_replay_failed_work_items_resets_attempts_and_status(monkeypatch) -> None:
    """Replay should move failed work back to pending with fresh attempts."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "work_item_id": "work-1",
            "work_type": "project-git-facts",
            "repository_id": "github.com/acme/service",
            "source_run_id": "run-123",
            "lease_owner": None,
            "lease_expires_at": None,
            "status": "pending",
            "attempt_count": 0,
            "last_error": "boom",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    rows = queue.replay_failed_work_items(work_item_ids=["work-1"], limit=10)

    assert [row.work_item_id for row in rows] == ["work-1"]
    query, params = cursor.execute.call_args_list[0].args
    assert "status = 'failed'" in query
    assert "attempt_count = 0" in query
    assert "dead_lettered_at = NULL" in query
    assert "next_retry_at = NULL" in query
    assert params["work_item_ids"] == ["work-1"]
    assert params["limit"] == 10
