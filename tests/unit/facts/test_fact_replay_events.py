"""Tests for durable fact replay event recording."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import platform_context_graph.facts.work_queue.replay as replay_mod
from platform_context_graph.facts.work_queue.replay import replay_failed_work_items


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for replay-event tests."""

    return datetime(2026, 4, 3, 12, 0, tzinfo=timezone.utc)


def test_replay_failed_work_items_records_replay_events(monkeypatch) -> None:
    """Replay should persist one audit row for each replayed work item."""

    queue = MagicMock()
    queue._fetchall.return_value = [
        {
            "work_item_id": "work-1",
            "work_type": "project-git-facts",
            "repository_id": "repository:r_payments",
            "source_run_id": "run-123",
            "lease_owner": None,
            "lease_expires_at": None,
            "status": "pending",
            "attempt_count": 0,
            "last_error": "boom",
            "failure_stage": "project_work_item",
            "error_class": "TimeoutError",
            "failure_class": "timeout",
            "failure_code": "timeout_error",
            "retry_disposition": "retryable",
            "dead_lettered_at": None,
            "last_attempt_started_at": None,
            "last_attempt_finished_at": None,
            "next_retry_at": None,
            "operator_note": "operator replay",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
    ]
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )
    monkeypatch.setattr(replay_mod, "utc_now", _utc_now)
    monkeypatch.setattr(replay_mod, "uuid4", lambda: "uuid-1")

    rows = replay_failed_work_items(
        queue,
        work_item_ids=["work-1"],
        failure_class="timeout",
        operator_note="operator replay",
        limit=10,
    )

    assert [row.work_item_id for row in rows] == ["work-1"]
    queue._fetchall.assert_called_once()
    replay_query, replay_params = queue._fetchall.call_args.args
    assert "failure_class = %(failure_class)s" in replay_query
    assert replay_params["failure_class"] == "timeout"
    assert replay_params["operator_note"] == "operator replay"
    queue._execute.assert_called_once()
    event_query, event_params = queue._execute.call_args.args
    assert "INSERT INTO fact_replay_events" in event_query
    assert event_params["replay_event_id"] == "fact-replay:uuid-1"
    assert event_params["operator_note"] == "operator replay"
