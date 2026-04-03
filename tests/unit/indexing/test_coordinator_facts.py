"""Tests for facts-first coordinator helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY
from unittest.mock import MagicMock

import pytest

from platform_context_graph.facts.emission.git_snapshot import (
    GitSnapshotFactEmissionResult,
)
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.indexing.coordinator_facts import (
    commit_repository_snapshot_from_facts,
    finalize_facts_first_run,
)
from platform_context_graph.indexing.coordinator_models import IndexRunState
from platform_context_graph.indexing.coordinator_models import RepositoryRunState
from platform_context_graph.indexing.coordinator_models import RepositorySnapshot


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for facts-first coordinator tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_commit_repository_snapshot_from_facts_resets_repo_and_projects_work_item(
    tmp_path: Path,
) -> None:
    """Facts-first commits should clear old repo state and project one work item."""

    repo_path = tmp_path / "payments"
    snapshot = RepositorySnapshot(
        repo_path=str(repo_path),
        file_count=1,
        imports_map={},
        file_data=[],
    )
    builder = SimpleNamespace(
        _content_provider=SimpleNamespace(
            enabled=True,
            delete_repository_content=MagicMock(),
        ),
    )
    graph_store = SimpleNamespace(delete_repository=MagicMock())
    work_item = FactWorkItemRow(
        work_item_id="work-1",
        work_type="project-git-facts",
        repository_id="repository:r_123",
        source_run_id="run-123",
        status="leased",
        lease_owner="indexing",
        lease_expires_at=_utc_now(),
        attempt_count=1,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    work_queue = MagicMock()
    work_queue.lease_work_item.return_value = work_item
    fact_store = MagicMock()
    projector = MagicMock(return_value={"facts": {"repositories": 1}})

    result = commit_repository_snapshot_from_facts(
        builder=builder,
        snapshot=snapshot,
        fact_emission_result=GitSnapshotFactEmissionResult(
            repository_id="repository:r_123",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            work_item_id="work-1",
            fact_count=3,
        ),
        fact_store=fact_store,
        work_queue=work_queue,
        graph_store=graph_store,
        project_work_item_fn=projector,
        lease_owner="indexing-worker",
        lease_ttl_seconds=60,
        progress_callback=None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert result.graph_batch_count == 1
    graph_store.delete_repository.assert_called_once_with("repository:r_123")
    builder._content_provider.delete_repository_content.assert_called_once_with(
        "repository:r_123"
    )
    work_queue.lease_work_item.assert_called_once_with(
        work_item_id="work-1",
        lease_owner="indexing-worker",
        lease_ttl_seconds=60,
    )
    projector.assert_called_once_with(
        work_item,
        builder=builder,
        fact_store=fact_store,
        info_logger_fn=ANY,
        debug_log_fn=ANY,
        warning_logger_fn=ANY,
    )
    work_queue.complete_work_item.assert_called_once_with(work_item_id="work-1")


def test_commit_repository_snapshot_from_facts_marks_projection_failures_retryable(
    tmp_path: Path,
) -> None:
    """Projection failures should return the work item to the retry queue."""

    repo_path = tmp_path / "payments"
    snapshot = RepositorySnapshot(
        repo_path=str(repo_path),
        file_count=1,
        imports_map={},
        file_data=[],
    )
    work_item = FactWorkItemRow(
        work_item_id="work-1",
        work_type="project-git-facts",
        repository_id="repository:r_123",
        source_run_id="run-123",
        status="leased",
        lease_owner="indexing",
        lease_expires_at=_utc_now(),
        attempt_count=1,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    work_queue = MagicMock()
    work_queue.lease_work_item.return_value = work_item

    with pytest.raises(RuntimeError, match="boom"):
        commit_repository_snapshot_from_facts(
            builder=SimpleNamespace(_content_provider=SimpleNamespace(enabled=False)),
            snapshot=snapshot,
            fact_emission_result=GitSnapshotFactEmissionResult(
                repository_id="repository:r_123",
                source_run_id="run-123",
                source_snapshot_id="snapshot-abc",
                work_item_id="work-1",
                fact_count=3,
            ),
            fact_store=MagicMock(),
            work_queue=work_queue,
            graph_store=SimpleNamespace(delete_repository=MagicMock()),
            project_work_item_fn=MagicMock(side_effect=RuntimeError("boom")),
            lease_owner="indexing-worker",
            lease_ttl_seconds=60,
            warning_logger_fn=lambda *_args, **_kwargs: None,
        )

    work_queue.fail_work_item.assert_called_once_with(
        work_item_id="work-1",
        error_message="boom",
        terminal=False,
    )
    work_queue.complete_work_item.assert_not_called()


def test_finalize_facts_first_run_marks_completed_and_deletes_snapshots() -> None:
    """Facts-first runs should close out run state without legacy finalization."""

    run_state = IndexRunState(
        run_id="run-123",
        root_path="/tmp/root",
        family="index",
        source="manual",
        discovery_signature="sig",
        is_dependency=False,
        status="running",
        finalization_status="pending",
        created_at="2026-04-02T12:00:00Z",
        updated_at="2026-04-02T12:00:00Z",
        repositories={
            "/tmp/root/repo": RepositoryRunState(
                repo_path="/tmp/root/repo",
                status="completed",
            )
        },
    )
    delete_snapshots = MagicMock()

    finalize_facts_first_run(
        run_state=run_state,
        repo_paths=[Path("/tmp/root/repo")],
        committed_repo_paths=[Path("/tmp/root/repo")],
        builder=SimpleNamespace(),
        component="ingester",
        source="manual",
        persist_run_state_fn=lambda _state: None,
        delete_snapshots_fn=delete_snapshots,
        publish_run_repository_coverage_fn=lambda **_kwargs: None,
        publish_runtime_progress_fn=lambda **_kwargs: None,
        utc_now_fn=lambda: "2026-04-02T12:05:00Z",
    )

    assert run_state.status == "completed"
    assert run_state.finalization_status == "completed"
    assert run_state.finalization_started_at == "2026-04-02T12:05:00Z"
    assert run_state.finalization_finished_at == "2026-04-02T12:05:00Z"
    delete_snapshots.assert_called_once_with("run-123")
