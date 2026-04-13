"""Tests for emitting facts from repository parse snapshots."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.emission.git_snapshot import emit_git_snapshot_facts


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for fact emission tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_emit_git_snapshot_facts_persists_run_facts_and_work_item() -> None:
    """Snapshot emission should write facts and enqueue one work item."""

    fact_store = MagicMock()
    work_queue = MagicMock()
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=1,
        imports_map={"handler": ["src/app.py"]},
        file_data=[
            {
                "path": "/tmp/service/src/app.py",
                "repo_path": "/tmp/service",
                "lang": "python",
                "functions": [
                    {
                        "name": "handler",
                        "line_number": 10,
                        "end_line": 20,
                    }
                ],
            }
        ],
    )

    emitted = emit_git_snapshot_facts(
        snapshot=snapshot,
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at=_utc_now(),
    )

    assert emitted.fact_count > 0
    fact_store.upsert_fact_run.assert_called_once()
    fact_store.upsert_facts.assert_called_once()
    work_queue.enqueue_work_item.assert_called_once()
    assert emitted.work_item_id
    fact_rows = fact_store.upsert_facts.call_args.args[0]
    file_fact_row = next(row for row in fact_rows if row.fact_type == "FileObserved")
    assert (
        file_fact_row.payload["parsed_file_data"]["functions"][0]["name"] == "handler"
    )
    assert file_fact_row.payload["parsed_file_data"]["lang"] == "python"


def test_emit_git_snapshot_facts_preleases_inline_projection_work_item() -> None:
    """Inline-owned emission should enqueue a leased work item for bootstrap."""

    fact_store = MagicMock()
    work_queue = MagicMock()
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=0,
        imports_map={},
        file_data=[],
    )

    emitted = emit_git_snapshot_facts(
        snapshot=snapshot,
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at=_utc_now(),
        inline_projection_owner="indexing",
        inline_projection_lease_ttl_seconds=300,
    )

    queued_row = work_queue.enqueue_work_item.call_args.args[0]
    assert queued_row.status == "leased"
    assert queued_row.lease_owner == "indexing"
    assert queued_row.attempt_count == 1
    assert queued_row.last_attempt_started_at == _utc_now()
    assert emitted.work_item is not None
    assert emitted.work_item.status == "leased"


def test_emit_git_snapshot_facts_keeps_import_map_only_on_repository_fact() -> None:
    """Only the repository fact should carry the imports map in provenance."""

    fact_store = MagicMock()
    work_queue = MagicMock()
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=1,
        imports_map={"handler": ["src/app.py"]},
        file_data=[
            {
                "path": "/tmp/service/src/app.py",
                "repo_path": "/tmp/service",
                "lang": "python",
                "functions": [
                    {
                        "name": "handler",
                        "line_number": 10,
                        "end_line": 20,
                    }
                ],
            }
        ],
    )

    emit_git_snapshot_facts(
        snapshot=snapshot,
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at=_utc_now(),
    )

    fact_rows = fact_store.upsert_facts.call_args.args[0]
    repository_row = next(
        row for row in fact_rows if row.fact_type == "RepositoryObserved"
    )
    file_row = next(row for row in fact_rows if row.fact_type == "FileObserved")
    entity_row = next(
        row for row in fact_rows if row.fact_type == "ParsedEntityObserved"
    )

    assert repository_row.provenance["imports_map"] == {"handler": ["src/app.py"]}
    assert "imports_map" not in file_row.provenance
    assert "imports_map" not in entity_row.provenance
