"""Tests for durable fact work-queue recovery helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import platform_context_graph.facts.work_queue.recovery as recovery_mod
from platform_context_graph.facts.work_queue.recovery import dead_letter_work_items
from platform_context_graph.facts.work_queue.recovery import list_replay_events
from platform_context_graph.facts.work_queue.recovery import request_backfill


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for recovery tests."""

    return datetime(2026, 4, 3, 18, 30, tzinfo=timezone.utc)


def test_dead_letter_work_items_updates_matching_rows(monkeypatch) -> None:
    """Manual dead-letter should preserve selectors and operator metadata."""

    queue = MagicMock()
    queue._fetchall.return_value = [
        {
            "work_item_id": "work-1",
            "work_type": "project-git-facts",
            "repository_id": "repository:r_payments",
            "source_run_id": "run-123",
            "lease_owner": None,
            "lease_expires_at": None,
            "status": "failed",
            "attempt_count": 3,
            "last_error": "Operator moved work item to dead letter",
            "failure_stage": "operator_action",
            "error_class": None,
            "failure_class": "manual_override",
            "failure_code": "manual_dead_letter",
            "retry_disposition": "manual_review",
            "dead_lettered_at": _utc_now(),
            "last_attempt_started_at": None,
            "last_attempt_finished_at": _utc_now(),
            "next_retry_at": None,
            "operator_note": "stop retrying during incident",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
    ]
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )
    monkeypatch.setattr(recovery_mod, "utc_now", _utc_now)

    rows = dead_letter_work_items(
        queue,
        repository_id="repository:r_payments",
        operator_note="stop retrying during incident",
        limit=5,
    )

    assert [row.work_item_id for row in rows] == ["work-1"]
    queue._fetchall.assert_called_once()
    query, params = queue._fetchall.call_args.args
    assert "SET status = 'failed'" in query
    assert params["repository_id"] == "repository:r_payments"
    assert params["failure_class"] == "manual_override"
    assert params["failure_code"] == "manual_dead_letter"
    assert params["retry_disposition"] == "manual_review"
    assert params["operator_note"] == "stop retrying during incident"


def test_request_backfill_persists_durable_request(monkeypatch) -> None:
    """Backfill requests should create durable operator audit rows."""

    queue = MagicMock()
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )
    monkeypatch.setattr(recovery_mod, "utc_now", _utc_now)
    monkeypatch.setattr(recovery_mod, "uuid4", lambda: "uuid-1")

    row = request_backfill(
        queue,
        repository_id="repository:r_payments",
        source_run_id="run-123",
        operator_note="refresh graph after incident replay",
    )

    assert row.backfill_request_id == "fact-backfill:uuid-1"
    assert row.repository_id == "repository:r_payments"
    assert row.source_run_id == "run-123"
    assert row.operator_note == "refresh graph after incident replay"
    queue._execute.assert_called_once()
    query, params = queue._execute.call_args.args
    assert "INSERT INTO fact_backfill_requests" in query
    assert params["backfill_request_id"] == "fact-backfill:uuid-1"
    assert params["operator_note"] == "refresh graph after incident replay"


def test_list_replay_events_returns_filtered_rows() -> None:
    """Replay-event listing should preserve filters and row shape."""

    queue = MagicMock()
    queue._fetchall.return_value = [
        {
            "replay_event_id": "fact-replay:1",
            "work_item_id": "work-1",
            "repository_id": "repository:r_payments",
            "source_run_id": "run-123",
            "work_type": "project-git-facts",
            "failure_class": "timeout",
            "operator_note": "operator replay",
            "created_at": _utc_now(),
        }
    ]
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )

    rows = list_replay_events(
        queue,
        repository_id="repository:r_payments",
        work_item_id="work-1",
        limit=10,
    )

    assert [row.replay_event_id for row in rows] == ["fact-replay:1"]
    queue._fetchall.assert_called_once()
    query, params = queue._fetchall.call_args.args
    assert "FROM fact_replay_events" in query
    assert params["repository_id"] == "repository:r_payments"
    assert params["work_item_id"] == "work-1"
    assert params["limit"] == 10
