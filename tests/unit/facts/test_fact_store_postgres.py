"""Tests for PostgreSQL-backed fact storage."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.storage.models import FactRunRow
from platform_context_graph.facts.storage.postgres import PostgresFactStore


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for storage tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_upsert_fact_run_and_batch_include_idempotent_conflicts(monkeypatch) -> None:
    """Fact run and record writes should use upserts for idempotency."""

    store = PostgresFactStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_fact_run(
        FactRunRow(
            source_run_id="run-123",
            source_system="git",
            source_snapshot_id="snapshot-abc",
            repository_id="github.com/acme/service",
            status="pending",
            started_at=_utc_now(),
        )
    )
    store.upsert_facts(
        [
            FactRecordRow(
                fact_id="fact-1",
                fact_type="RepositoryObserved",
                repository_id="github.com/acme/service",
                checkout_path="/tmp/service",
                relative_path=None,
                source_system="git",
                source_run_id="run-123",
                source_snapshot_id="snapshot-abc",
                payload={"is_dependency": False},
                observed_at=_utc_now(),
                ingested_at=_utc_now(),
                provenance={"source": "git"},
            )
        ]
    )

    run_query, _run_params = cursor.execute.call_args_list[0].args
    batch_query, batch_rows = cursor.executemany.call_args.args

    assert "ON CONFLICT (source_run_id) DO UPDATE" in run_query
    assert "ON CONFLICT (fact_id) DO UPDATE" in batch_query
    assert len(batch_rows) == 1
    assert batch_rows[0]["fact_type"] == "RepositoryObserved"


def test_list_facts_returns_rows_for_repository_and_run(monkeypatch) -> None:
    """Fact reads should return normalized row models for one repo/run pair."""

    store = PostgresFactStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "fact_id": "fact-1",
            "fact_type": "FileObserved",
            "repository_id": "github.com/acme/service",
            "checkout_path": "/tmp/service",
            "relative_path": "src/app.py",
            "source_system": "git",
            "source_run_id": "run-123",
            "source_snapshot_id": "snapshot-abc",
            "payload": {"language": "python"},
            "observed_at": _utc_now(),
            "ingested_at": _utc_now(),
            "provenance": {"source": "git"},
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    rows = store.list_facts(
        repository_id="github.com/acme/service",
        source_run_id="run-123",
    )

    assert len(rows) == 1
    assert rows[0].fact_id == "fact-1"
    assert rows[0].relative_path == "src/app.py"
    assert rows[0].payload["language"] == "python"
