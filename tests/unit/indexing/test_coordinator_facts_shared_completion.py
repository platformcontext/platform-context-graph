"""Tests for shared-projection completion fencing in facts-first commits."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY
from unittest.mock import MagicMock

from platform_context_graph.facts.emission.git_snapshot import (
    GitSnapshotFactEmissionResult,
)
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.indexing.coordinator_facts import (
    commit_repository_snapshot_from_facts,
    create_facts_first_commit_callback,
)
from platform_context_graph.indexing.coordinator_models import RepositorySnapshot


def _utc_now() -> datetime:
    """Return a stable timestamp for shared-completion coordinator tests."""

    return datetime(2026, 4, 9, 12, 0, tzinfo=timezone.utc)


def test_commit_repository_snapshot_from_facts_fences_on_authoritative_shared_work(
    tmp_path: Path,
) -> None:
    """Inline projection should stop short of completed when follow-up is authoritative."""

    repo_path = tmp_path / "payments"
    snapshot = RepositorySnapshot(
        repo_path=str(repo_path),
        file_count=1,
        imports_map={},
        file_data=[],
    )
    builder = SimpleNamespace(
        reset_repository_subtree_in_graph=MagicMock(return_value=True),
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
    projector = MagicMock(
        return_value={
            "facts": {"repositories": 1},
            "shared_projection": {
                "authoritative_domains": ["platform_infra"],
                "accepted_generation_id": "gen-123",
            },
        }
    )

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
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert result.shared_projection_pending is True
    assert result.authoritative_shared_domains == ("platform_infra",)
    assert result.accepted_generation_id == "gen-123"
    work_queue.mark_shared_projection_pending.assert_called_once_with(
        work_item_id="work-1",
        accepted_generation_id="gen-123",
        authoritative_shared_domains=["platform_infra"],
    )
    work_queue.complete_work_item.assert_not_called()


def test_commit_repository_snapshot_from_facts_falls_back_to_snapshot_generation(
    tmp_path: Path,
) -> None:
    """Inline projection should use the emitted snapshot id as safe fallback."""

    repo_path = tmp_path / "payments"
    snapshot = RepositorySnapshot(
        repo_path=str(repo_path),
        file_count=1,
        imports_map={},
        file_data=[],
    )
    builder = SimpleNamespace(
        reset_repository_subtree_in_graph=MagicMock(return_value=True),
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
    projector = MagicMock(
        return_value={
            "facts": {"repositories": 1},
            "shared_projection": {
                "authoritative_domains": ["platform_infra"],
            },
        }
    )

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
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert result.shared_projection_pending is True
    assert result.accepted_generation_id == "snapshot-abc"
    work_queue.mark_shared_projection_pending.assert_called_once_with(
        work_item_id="work-1",
        accepted_generation_id="snapshot-abc",
        authoritative_shared_domains=["platform_infra"],
    )
    work_queue.complete_work_item.assert_not_called()


def test_create_facts_first_commit_callback_marks_fact_run_pending_shared_follow_up() -> (
    None
):
    """Fact-run status should stay pending until authoritative shared work finishes."""

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
    project_snapshot = MagicMock(
        return_value=SimpleNamespace(
            shared_projection_pending=True,
            authoritative_shared_domains=("platform_infra",),
            accepted_generation_id="gen-123",
        )
    )

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
        fact_emission_result=emission_result,
        project_repository_snapshot_facts_fn=project_snapshot,
        graph_store_adapter_fn=lambda _builder: MagicMock(),
    )

    fact_run = store.upsert_fact_run.call_args.args[0]
    assert fact_run.status == "awaiting_shared_projection"
    assert fact_run.completed_at is None
    project_snapshot.assert_called_once_with(
        builder,
        snapshot,
        fact_emission_result=emission_result,
        fact_store=store,
        work_queue=queue,
        graph_store=ANY,
        project_work_item_fn=ANY,
        lease_owner="indexing",
        lease_ttl_seconds=300,
        max_attempts=3,
        info_logger_fn=ANY,
        warning_logger_fn=ANY,
        progress_callback=progress_callback,
        iter_snapshot_file_data_batches_fn=iter_batches,
        repo_class=None,
    )
