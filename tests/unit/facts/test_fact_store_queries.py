"""Tests for partitioned fact-store query helpers."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from platform_context_graph.facts.storage.queries import iter_fact_batches


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for query-helper tests."""

    return datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc)


def test_iter_fact_batches_defers_reads_until_consumed() -> None:
    """Entity pagination should execute one page at a time during iteration."""

    cursor = MagicMock()
    cursor.fetchall.side_effect = [
        [
            {
                "fact_id": "fact-1",
                "fact_type": "ParsedEntityObserved",
                "repository_id": "repository:r_service",
                "checkout_path": "/tmp/service",
                "relative_path": "src/a.py",
                "source_system": "git",
                "source_run_id": "run-123",
                "source_snapshot_id": "snapshot-abc",
                "payload": {"entity_kind": "Function"},
                "observed_at": _utc_now(),
                "ingested_at": _utc_now(),
                "provenance": {},
            },
            {
                "fact_id": "fact-2",
                "fact_type": "ParsedEntityObserved",
                "repository_id": "repository:r_service",
                "checkout_path": "/tmp/service",
                "relative_path": "src/b.py",
                "source_system": "git",
                "source_run_id": "run-123",
                "source_snapshot_id": "snapshot-abc",
                "payload": {"entity_kind": "Function"},
                "observed_at": _utc_now(),
                "ingested_at": _utc_now(),
                "provenance": {},
            },
        ],
        [
            {
                "fact_id": "fact-3",
                "fact_type": "ParsedEntityObserved",
                "repository_id": "repository:r_service",
                "checkout_path": "/tmp/service",
                "relative_path": "src/c.py",
                "source_system": "git",
                "source_run_id": "run-123",
                "source_snapshot_id": "snapshot-abc",
                "payload": {"entity_kind": "Function"},
                "observed_at": _utc_now(),
                "ingested_at": _utc_now(),
                "provenance": {},
            }
        ],
    ]

    @contextmanager
    def _cursor_factory():
        yield cursor

    batch_iter = iter_fact_batches(
        cursor_factory=_cursor_factory,
        record_operation=lambda **kwargs: kwargs["callback"](),
        repository_id="repository:r_service",
        source_run_id="run-123",
        fact_type="ParsedEntityObserved",
        batch_size=2,
    )

    assert cursor.execute.call_count == 0

    first_batch = next(batch_iter)

    assert cursor.execute.call_count == 1
    assert [row.fact_id for row in first_batch] == ["fact-1", "fact-2"]

    second_batch = next(batch_iter)

    assert cursor.execute.call_count == 2
    assert [row.fact_id for row in second_batch] == ["fact-3"]

    with pytest.raises(StopIteration):
        next(batch_iter)
