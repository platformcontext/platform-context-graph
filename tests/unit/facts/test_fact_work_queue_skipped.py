"""Tests for archived-repository skipped fact work items."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import platform_context_graph.facts.work_queue.recovery as recovery_mod
from platform_context_graph.facts.work_queue.recovery import skip_repository_work_items


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for skipped-work-item tests."""

    return datetime(2026, 4, 9, 20, 30, tzinfo=timezone.utc)


def test_skip_repository_work_items_marks_matching_rows_skipped(
    monkeypatch,
) -> None:
    """Archived repositories should no longer remain actionable queue failures."""

    queue = MagicMock()
    queue._fetchall.return_value = [
        {
            "work_item_id": "work-1",
            "work_type": "project-git-facts",
            "repository_id": "repository:r_archived",
            "source_run_id": "run-123",
            "lease_owner": None,
            "lease_expires_at": None,
            "status": "skipped",
            "attempt_count": 3,
            "last_error": "fatal: could not read Username for 'https://github.com'",
            "failure_stage": "repo_sync",
            "error_class": None,
            "failure_class": "skipped_repository",
            "failure_code": "archived_repository",
            "retry_disposition": "non_retryable",
            "dead_lettered_at": None,
            "last_attempt_started_at": _utc_now(),
            "last_attempt_finished_at": _utc_now(),
            "next_retry_at": None,
            "operator_note": "Repository is archived and excluded by repo-sync policy.",
            "created_at": _utc_now(),
            "updated_at": _utc_now(),
        }
    ]
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )
    monkeypatch.setattr(recovery_mod, "utc_now", _utc_now)

    rows = skip_repository_work_items(
        queue,
        repository_id="repository:r_archived",
        operator_note="Repository is archived and excluded by repo-sync policy.",
    )

    assert [row.work_item_id for row in rows] == ["work-1"]
    query, params = queue._fetchall.call_args.args
    assert "SET status = 'skipped'" in query
    assert "status NOT IN ('completed', 'skipped')" in query
    assert params["repository_id"] == "repository:r_archived"
    assert params["failure_class"] == "skipped_repository"
    assert params["failure_code"] == "archived_repository"
    assert params["retry_disposition"] == "non_retryable"
    assert params["operator_note"] == (
        "Repository is archived and excluded by repo-sync policy."
    )
