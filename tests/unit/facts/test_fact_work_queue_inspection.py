"""Tests for fact work queue inspection helpers."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from platform_context_graph.facts.work_queue.postgres import PostgresFactWorkQueue


def test_count_shared_projection_pending_omits_source_run_filter_when_absent(
    monkeypatch,
) -> None:
    """Pending-count SQL should not bind a nullable source-run selector."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {"pending_count": 3}

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)
    monkeypatch.setattr(
        queue,
        "_record_operation",
        lambda *, operation, callback, row_count=None: callback(),
    )

    try:
        pending_count = queue.count_shared_projection_pending()
    finally:
        queue.close()

    query, params = cursor.execute.call_args.args
    assert pending_count == 3
    assert "source_run_id = %(source_run_id)s" not in query
    assert "source_run_id" not in params


def test_count_shared_projection_pending_filters_by_source_run_when_present(
    monkeypatch,
) -> None:
    """Pending-count SQL should bind one explicit source-run predicate."""

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {"pending_count": 1}

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)
    monkeypatch.setattr(
        queue,
        "_record_operation",
        lambda *, operation, callback, row_count=None: callback(),
    )

    try:
        pending_count = queue.count_shared_projection_pending(source_run_id="run-123")
    finally:
        queue.close()

    query, params = cursor.execute.call_args.args
    assert pending_count == 1
    assert "source_run_id = %(source_run_id)s" in query
    assert params["source_run_id"] == "run-123"
