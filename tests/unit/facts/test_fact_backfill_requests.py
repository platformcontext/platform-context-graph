"""Tests for durable fact backfill request helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.facts.work_queue.recovery import (
    delete_backfill_requests,
    list_backfill_requests,
    list_repository_ids_for_source_run,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for backfill helper tests."""

    return datetime(2026, 4, 11, 12, 0, tzinfo=timezone.utc)


def test_list_backfill_requests_returns_oldest_rows() -> None:
    """Listing backfills should preserve row shape and oldest-first ordering."""

    queue = MagicMock()
    queue._fetchall.return_value = [
        {
            "backfill_request_id": "fact-backfill:1",
            "repository_id": "repository:r_payments",
            "source_run_id": "run-123",
            "operator_note": "refresh repo",
            "created_at": _utc_now(),
        }
    ]
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )

    rows = list_backfill_requests(queue, limit=25)

    assert [row.backfill_request_id for row in rows] == ["fact-backfill:1"]
    queue._fetchall.assert_called_once()
    query, params = queue._fetchall.call_args.args
    assert "FROM fact_backfill_requests" in query
    assert "ORDER BY created_at ASC, backfill_request_id ASC" in query
    assert params["limit"] == 25


def test_delete_backfill_requests_deletes_matching_rows() -> None:
    """Deleting satisfied backfill requests should return the removed count."""

    queue = MagicMock()
    queue._fetchall.return_value = [
        {"backfill_request_id": "fact-backfill:1"},
        {"backfill_request_id": "fact-backfill:2"},
    ]
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )

    deleted = delete_backfill_requests(
        queue,
        backfill_request_ids=[
            "fact-backfill:2",
            "fact-backfill:1",
            "fact-backfill:2",
        ],
    )

    assert deleted == 2
    queue._fetchall.assert_called_once()
    query, params = queue._fetchall.call_args.args
    assert "DELETE FROM fact_backfill_requests" in query
    assert params["backfill_request_ids"] == [
        "fact-backfill:1",
        "fact-backfill:2",
    ]


def test_list_repository_ids_for_source_run_returns_distinct_ids() -> None:
    """Source-run resolution should return distinct canonical repository ids."""

    queue = MagicMock()
    queue._fetchall.return_value = [
        {"repository_id": "repository:r_orders"},
        {"repository_id": "repository:r_payments"},
    ]
    queue._record_operation.side_effect = (
        lambda *, operation, callback, row_count=None: callback()
    )

    repository_ids = list_repository_ids_for_source_run(
        queue,
        source_run_id="run-123",
        limit=500,
    )

    assert repository_ids == [
        "repository:r_orders",
        "repository:r_payments",
    ]
    queue._fetchall.assert_called_once()
    query, params = queue._fetchall.call_args.args
    assert "SELECT DISTINCT repository_id" in query
    assert "FROM fact_work_items" in query
    assert params["source_run_id"] == "run-123"
    assert params["limit"] == 500
