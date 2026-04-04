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
    create_facts_first_commit_callback,
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
    decision_store = MagicMock()
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
        decision_store=decision_store,
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
        decision_store=decision_store,
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


def test_commit_repository_snapshot_from_facts_uses_inline_owned_work_item(
    tmp_path: Path,
) -> None:
    """Inline-owned emissions should skip the second lease call entirely."""

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
    work_queue = MagicMock()
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
            work_item=FactWorkItemRow(
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
            ),
        ),
        fact_store=fact_store,
        work_queue=work_queue,
        graph_store=graph_store,
        project_work_item_fn=projector,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert result.graph_batch_count == 1
    work_queue.lease_work_item.assert_not_called()
    projector.assert_called_once()
    work_queue.complete_work_item.assert_called_once_with(work_item_id="work-1")


def test_commit_repository_snapshot_from_facts_does_not_clear_state_on_lease_miss(
    tmp_path: Path,
) -> None:
    """A lease miss should fail before clearing repository graph or content state."""

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
    work_queue = MagicMock()
    work_queue.lease_work_item.return_value = None

    with pytest.raises(RuntimeError, match="could not lease work item work-1"):
        commit_repository_snapshot_from_facts(
            builder=builder,
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
            graph_store=graph_store,
            project_work_item_fn=MagicMock(),
            warning_logger_fn=lambda *_args, **_kwargs: None,
        )

    graph_store.delete_repository.assert_not_called()
    builder._content_provider.delete_repository_content.assert_not_called()


def test_create_facts_first_commit_callback_reuses_cached_emission_result() -> None:
    """The cached emission result should be forwarded unchanged to projection."""

    builder = SimpleNamespace()
    store = MagicMock()
    queue = MagicMock()
    snapshot = RepositorySnapshot(
        repo_path="/tmp/payments",
        file_count=2,
        imports_map={"handler": ["/tmp/payments/app.py"]},
        file_data=[],
    )
    emission_result = GitSnapshotFactEmissionResult(
        repository_id="repository:r_123",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        work_item_id="work-1",
        fact_count=2,
    )
    progress_callback = MagicMock()
    iter_batches = MagicMock()
    project_snapshot = MagicMock(return_value=SimpleNamespace())

    callback = create_facts_first_commit_callback(
        builder=builder,
        source_run_id="run-123",
        fact_store=store,
        work_queue=queue,
        fact_emission_results={
            str(Path(snapshot.repo_path).resolve()): emission_result
        },
        observed_at_fn=_utc_now,
    )

    callback(
        builder,
        snapshot,
        is_dependency=False,
        progress_callback=progress_callback,
        iter_snapshot_file_data_batches_fn=iter_batches,
        repo_class="medium",
        fact_emission_result=None,
        project_repository_snapshot_facts_fn=project_snapshot,
        graph_store_adapter_fn=lambda _builder: "graph-store",
    )

    project_snapshot.assert_called_once_with(
        builder,
        snapshot,
        fact_emission_result=emission_result,
        fact_store=store,
        work_queue=queue,
        graph_store="graph-store",
        project_work_item_fn=ANY,
        lease_owner="indexing",
        lease_ttl_seconds=300,
        info_logger_fn=ANY,
        warning_logger_fn=ANY,
        progress_callback=progress_callback,
        iter_snapshot_file_data_batches_fn=iter_batches,
        repo_class="medium",
    )
    fact_run = store.upsert_fact_run.call_args.args[0]
    assert fact_run.status == "completed"
    assert fact_run.repository_id == emission_result.repository_id
    assert fact_run.source_snapshot_id == emission_result.source_snapshot_id


def test_create_facts_first_commit_callback_builds_deterministic_fallback_ids() -> None:
    """Missing cached emissions should fall back to deterministic identifiers."""

    builder = SimpleNamespace()
    store = MagicMock()
    queue = MagicMock()
    snapshot = RepositorySnapshot(
        repo_path="/tmp/payments",
        file_count=2,
        imports_map={"handler": ["/tmp/payments/app.py"]},
        file_data=[],
    )
    project_snapshot = MagicMock(side_effect=RuntimeError("projection failed"))

    callback = create_facts_first_commit_callback(
        builder=builder,
        source_run_id="run-123",
        fact_store=store,
        work_queue=queue,
        fact_emission_results={},
        observed_at_fn=_utc_now,
    )

    with pytest.raises(RuntimeError, match="projection failed"):
        callback(
            builder,
            snapshot,
            is_dependency=False,
            project_repository_snapshot_facts_fn=project_snapshot,
            graph_store_adapter_fn=lambda _builder: "graph-store",
        )

    forwarded_emission_result = project_snapshot.call_args.kwargs[
        "fact_emission_result"
    ]
    assert forwarded_emission_result.source_run_id == "run-123"
    assert forwarded_emission_result.repository_id.startswith("repository:")
    assert forwarded_emission_result.source_snapshot_id
    assert forwarded_emission_result.work_item_id
    failed_run = store.upsert_fact_run.call_args.args[0]
    assert failed_run.status == "failed"
    assert failed_run.repository_id == forwarded_emission_result.repository_id
    assert failed_run.source_snapshot_id == forwarded_emission_result.source_snapshot_id


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


def test_finalize_facts_first_run_records_partial_failure_details() -> None:
    """Partial-failure runs should keep facts-first status and publish details."""

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
                status="commit_incomplete",
            )
        },
    )
    published_statuses: list[str] = []

    finalize_facts_first_run(
        run_state=run_state,
        repo_paths=[Path("/tmp/root/repo")],
        committed_repo_paths=[],
        builder=SimpleNamespace(),
        component="ingester",
        source="manual",
        persist_run_state_fn=lambda _state: None,
        delete_snapshots_fn=MagicMock(),
        publish_run_repository_coverage_fn=lambda **_kwargs: None,
        publish_runtime_progress_fn=lambda **kwargs: published_statuses.append(
            kwargs["status"]
        ),
        utc_now_fn=lambda: "2026-04-02T12:05:00Z",
        last_metrics={"facts": {"repositories": 0}},
    )

    assert run_state.status == "partial_failure"
    assert run_state.finalization_status == "pending"
    assert run_state.finalization_stage_details == {
        "facts_projection": {"repositories": 0}
    }
    assert published_statuses == ["partial_failure"]
