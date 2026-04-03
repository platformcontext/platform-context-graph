"""Tests for the Phase 2 Resolution Engine runtime shell."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.resolution.orchestration.engine import project_work_item
from platform_context_graph.resolution.orchestration.runtime import (
    run_resolution_iteration,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for runtime tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_run_resolution_iteration_claims_and_projects_one_work_item() -> None:
    """One resolution iteration should claim, project, and complete work."""

    queue = MagicMock()
    queue.claim_work_item.return_value = FactWorkItemRow(
        work_item_id="work-1",
        work_type="project-git-facts",
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        lease_owner="resolution-worker-1",
        lease_expires_at=_utc_now(),
        status="leased",
        attempt_count=1,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
    handled: list[str] = []

    def _projector(row: FactWorkItemRow) -> None:
        handled.append(row.work_item_id)

    processed = run_resolution_iteration(
        queue=queue,
        projector=_projector,
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    assert processed is True
    assert handled == ["work-1"]
    queue.complete_work_item.assert_called_once_with(work_item_id="work-1")


def test_run_resolution_iteration_marks_failures() -> None:
    """One resolution iteration should mark a failed work item retryable."""

    queue = MagicMock()
    queue.claim_work_item.return_value = FactWorkItemRow(
        work_item_id="work-2",
        work_type="project-git-facts",
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        lease_owner="resolution-worker-1",
        lease_expires_at=_utc_now(),
        status="leased",
        attempt_count=1,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )

    def _projector(_row: FactWorkItemRow) -> None:
        raise RuntimeError("boom")

    processed = run_resolution_iteration(
        queue=queue,
        projector=_projector,
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    assert processed is True
    queue.fail_work_item.assert_called_once_with(
        work_item_id="work-2",
        error_message="boom",
        terminal=False,
    )


def test_project_work_item_loads_facts_and_runs_projection_stages() -> None:
    """Projecting one work item should load facts and run both projection stages."""

    fact_store = MagicMock()
    fact_store.list_facts.return_value = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={"language": "python", "is_dependency": False},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]
    handled: list[str] = []
    builder = MagicMock()
    debug_logger = MagicMock()
    warning_logger = MagicMock()
    info_logger = MagicMock()
    seen_fact_records: list[object] = []

    def _fact_projector(*, builder, fact_records):  # type: ignore[no-untyped-def]
        assert builder is not None
        assert builder is builder_obj
        seen_fact_records.append(fact_records)
        handled.append(f"facts:{len(fact_records)}")
        return {"repositories": 0, "files": 1, "entities": 0}

    def _relationship_projector(  # type: ignore[no-untyped-def]
        *,
        builder,
        fact_records,
        debug_log_fn,
        warning_logger_fn,
    ):
        assert builder is builder_obj
        assert fact_records is seen_fact_records[0]
        assert debug_log_fn is debug_logger
        assert warning_logger_fn is warning_logger
        handled.append(f"relationships:{len(fact_records)}")
        return {"files": 1, "imports": 0, "call_metrics": {}}

    def _workload_projector(  # type: ignore[no-untyped-def]
        *,
        builder,
        fact_records,
        info_logger_fn,
    ):
        assert builder is builder_obj
        assert fact_records is seen_fact_records[0]
        assert info_logger_fn is info_logger
        handled.append(f"workloads:{len(fact_records)}")
        return {"workloads_projected": 1, "runtime_platform_edges_projected": 1}

    def _platform_projector(*, builder, fact_records):  # type: ignore[no-untyped-def]
        assert builder is builder_obj
        assert fact_records is seen_fact_records[0]
        handled.append(f"platforms:{len(fact_records)}")
        return {"infrastructure_platform_edges_projected": 1}

    builder_obj = builder
    metrics = project_work_item(
        FactWorkItemRow(
            work_item_id="work-3",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
        ),
        builder=builder,
        fact_store=fact_store,
        fact_projector=_fact_projector,
        relationship_projector=_relationship_projector,
        workload_projector=_workload_projector,
        platform_projector=_platform_projector,
        debug_log_fn=debug_logger,
        warning_logger_fn=warning_logger,
        info_logger_fn=info_logger,
    )

    assert handled == ["facts:1", "relationships:1", "workloads:1", "platforms:1"]
    fact_store.list_facts.assert_called_once_with(
        repository_id="github.com/acme/service",
        source_run_id="run-123",
    )
    assert metrics == {
        "facts": {"repositories": 0, "files": 1, "entities": 0},
        "relationships": {"files": 1, "imports": 0, "call_metrics": {}},
        "workloads": {
            "workloads_projected": 1,
            "runtime_platform_edges_projected": 1,
        },
        "platforms": {"infrastructure_platform_edges_projected": 1},
    }
