"""Integration coverage for the facts-first Git indexing seam."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.storage.models import FactRunRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.indexing.coordinator_facts import (
    commit_repository_snapshot_from_facts,
)
from platform_context_graph.indexing.coordinator_facts import create_snapshot_fact_emitter


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for facts-first integration tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


class _InMemoryFactStore:
    """Minimal in-memory fact store for cutover integration tests."""

    def __init__(self) -> None:
        self.runs: list[FactRunRow] = []
        self.records: list[FactRecordRow] = []
        self.enabled = True

    def upsert_fact_run(self, entry: FactRunRow) -> None:
        self.runs = [row for row in self.runs if row.source_run_id != entry.source_run_id]
        self.runs.append(entry)

    def upsert_facts(self, entries: list[FactRecordRow]) -> None:
        by_id = {record.fact_id: record for record in self.records}
        for entry in entries:
            by_id[entry.fact_id] = entry
        self.records = list(by_id.values())

    def list_facts(
        self,
        *,
        repository_id: str,
        source_run_id: str,
    ) -> list[FactRecordRow]:
        return [
            record
            for record in self.records
            if record.repository_id == repository_id
            and record.source_run_id == source_run_id
        ]


class _InMemoryFactWorkQueue:
    """Minimal in-memory work queue for cutover integration tests."""

    def __init__(self) -> None:
        self.rows: dict[str, FactWorkItemRow] = {}
        self.enabled = True

    def enqueue_work_item(self, entry: FactWorkItemRow) -> None:
        self.rows[entry.work_item_id] = entry

    def lease_work_item(
        self,
        *,
        work_item_id: str,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        del lease_ttl_seconds
        row = self.rows.get(work_item_id)
        if row is None:
            return None
        leased = replace(row, lease_owner=lease_owner, status="leased")
        self.rows[work_item_id] = leased
        return leased

    def complete_work_item(self, *, work_item_id: str) -> None:
        row = self.rows[work_item_id]
        self.rows[work_item_id] = replace(
            row,
            status="completed",
            lease_owner=None,
            last_error=None,
        )

    def fail_work_item(
        self,
        *,
        work_item_id: str,
        error_message: str,
        terminal: bool,
    ) -> None:
        row = self.rows[work_item_id]
        self.rows[work_item_id] = replace(
            row,
            status="failed" if terminal else "pending",
            lease_owner=None,
            last_error=error_message,
        )


def test_emitted_git_snapshot_projects_through_facts_first_commit_path() -> None:
    """Emitted Git facts should flow through the commit helper into projection."""

    fact_store = _InMemoryFactStore()
    work_queue = _InMemoryFactWorkQueue()
    emitter = create_snapshot_fact_emitter(
        source_run_id="run-123",
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at_fn=_utc_now,
    )
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=1,
        imports_map={"handler": ["/tmp/service/src/app.py"]},
        file_data=[
            {
                "path": "/tmp/service/src/app.py",
                "repo_path": "/tmp/service",
                "lang": "python",
                "functions": [{"name": "handler", "line_number": 10}],
            }
        ],
    )
    emission_result = emitter(
        run_id="run-123",
        repo_path=Path(snapshot.repo_path),
        snapshot=snapshot,
        is_dependency=False,
    )

    captured: dict[str, object] = {}

    def _project_work_item(
        work_item: FactWorkItemRow,
        *,
        builder,
        fact_store,
        info_logger_fn,
        debug_log_fn,
        warning_logger_fn,
    ) -> dict[str, object]:
        del builder
        del info_logger_fn
        del debug_log_fn
        del warning_logger_fn
        fact_records = fact_store.list_facts(
            repository_id=work_item.repository_id,
            source_run_id=work_item.source_run_id,
        )
        captured["fact_types"] = sorted(record.fact_type for record in fact_records)
        return {"facts": {"records": len(fact_records)}}

    graph_store = SimpleNamespace(delete_repository=MagicMock())
    timing = commit_repository_snapshot_from_facts(
        builder=SimpleNamespace(_content_provider=SimpleNamespace(enabled=False)),
        snapshot=snapshot,
        fact_emission_result=emission_result,
        fact_store=fact_store,
        work_queue=work_queue,
        graph_store=graph_store,
        project_work_item_fn=_project_work_item,
    )

    assert timing.graph_batch_count == 1
    graph_store.delete_repository.assert_called_once_with(emission_result.repository_id)
    assert captured["fact_types"] == [
        "FileObserved",
        "ParsedEntityObserved",
        "RepositoryObserved",
    ]
    assert work_queue.rows[emission_result.work_item_id].status == "completed"
