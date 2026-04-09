"""Tests for the Phase 2 Resolution Engine runtime shell."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.resolution.orchestration import engine as engine_module
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
    kwargs = queue.fail_work_item.call_args.kwargs
    assert kwargs["work_item_id"] == "work-2"
    assert kwargs["error_message"] == "boom"
    assert kwargs["terminal"] is False
    assert kwargs["failure_stage"] == "project_work_item"
    assert kwargs["error_class"] == "RuntimeError"


def test_run_resolution_iteration_marks_shared_projection_pending() -> None:
    """Resolution runtime should preserve pending shared follow-up honestly."""

    queue = MagicMock()
    queue.claim_work_item.return_value = FactWorkItemRow(
        work_item_id="work-pending",
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

    processed = run_resolution_iteration(
        queue=queue,
        projector=lambda _row: {
            "shared_projection": {
                "authoritative_domains": ["platform_infra"],
                "accepted_generation_id": "gen-123",
            }
        },
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    assert processed is True
    queue.mark_shared_projection_pending.assert_called_once_with(
        work_item_id="work-pending",
        accepted_generation_id="gen-123",
        authoritative_shared_domains=["platform_infra"],
    )
    queue.complete_work_item.assert_not_called()


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


def test_project_work_item_records_projection_decisions() -> None:
    """Decision storage should receive relationship, workload, and platform rows."""

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
    decision_store = MagicMock()

    project_work_item(
        FactWorkItemRow(
            work_item_id="work-4",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
        ),
        builder=MagicMock(),
        fact_store=fact_store,
        decision_store=decision_store,
        fact_projector=lambda **_kwargs: {"files": 1},
        relationship_projector=lambda **_kwargs: {"files": 1, "imports": 0},
        workload_projector=lambda **_kwargs: {"workloads_projected": 1},
        platform_projector=lambda **_kwargs: {
            "infrastructure_platform_edges_projected": 1
        },
    )

    assert decision_store.upsert_decision.call_count == 3
    decision_types = [
        call.args[0].decision_type
        for call in decision_store.upsert_decision.call_args_list
    ]
    assert decision_types == [
        "project_relationships",
        "project_workloads",
        "project_platforms",
    ]
    assert decision_store.insert_evidence.call_count == 3


def test_project_work_item_consumes_entity_batches_after_fact_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Entity batches should stay lazy until the entity stage begins."""

    events: list[str] = []

    class _FactStore:
        def list_facts_by_type(
            self,
            *,
            repository_id: str,
            source_run_id: str,
            fact_type: str,
        ) -> list[FactRecordRow]:
            del repository_id, source_run_id
            if fact_type == "RepositoryObserved":
                return [
                    FactRecordRow(
                        fact_id="fact:repo",
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
                        provenance={},
                    )
                ]
            if fact_type == "FileObserved":
                return [
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
            raise AssertionError(f"unexpected fact_type {fact_type}")

        def count_facts(
            self,
            *,
            repository_id: str,
            source_run_id: str,
        ) -> int:
            del repository_id, source_run_id
            return 3

        def iter_fact_batches(
            self,
            *,
            repository_id: str,
            source_run_id: str,
            fact_type: str,
            batch_size: int,
        ):
            del repository_id, source_run_id, fact_type, batch_size

            def _iterator():
                events.append("yield_entity_batch")
                yield [
                    FactRecordRow(
                        fact_id="fact:entity",
                        fact_type="ParsedEntityObserved",
                        repository_id="github.com/acme/service",
                        checkout_path="/tmp/service",
                        relative_path="src/app.py",
                        source_system="git",
                        source_run_id="run-123",
                        source_snapshot_id="snapshot-abc",
                        payload={
                            "entity_kind": "Function",
                            "entity_name": "handler",
                            "start_line": 10,
                            "end_line": 20,
                            "language": "python",
                        },
                        observed_at=_utc_now(),
                        ingested_at=_utc_now(),
                        provenance={},
                    )
                ]

            return _iterator()

    def _fact_projector(*, builder, fact_records):  # type: ignore[no-untyped-def]
        del builder, fact_records
        events.append("project_facts")
        return {"repositories": 1, "files": 1, "entities": 0}

    def _relationship_projector(**_kwargs):  # type: ignore[no-untyped-def]
        events.append("project_relationships")
        return {"files": 1, "imports": 0}

    def _workload_projector(**_kwargs):  # type: ignore[no-untyped-def]
        events.append("project_workloads")
        return {"workloads_projected": 0}

    def _platform_projector(**_kwargs):  # type: ignore[no-untyped-def]
        events.append("project_platforms")
        return {"infrastructure_platform_edges_projected": 0}

    def _project_entity_batches(builder, entity_batches, graph_facts):  # type: ignore[no-untyped-def]
        del builder, graph_facts
        events.append("project_entity_batches")
        assert sum(len(batch) for batch in entity_batches) == 1
        return {"entities": 1}

    monkeypatch.setattr(
        engine_module,
        "_project_entity_batches",
        _project_entity_batches,
    )

    builder = MagicMock()
    builder._content_provider = MagicMock(enabled=False)

    project_work_item(
        FactWorkItemRow(
            work_item_id="work-6",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
        ),
        builder=builder,
        fact_store=_FactStore(),
        fact_projector=_fact_projector,
        relationship_projector=_relationship_projector,
        workload_projector=_workload_projector,
        platform_projector=_platform_projector,
    )

    assert events.index("project_facts") < events.index("yield_entity_batch")


def test_project_work_item_clears_repository_state_before_projection() -> None:
    """Standalone resolution should clear repo graph/content state before projection."""

    fact_store = MagicMock()
    fact_store.list_facts.return_value = []
    builder = MagicMock()
    builder.reset_repository_subtree_in_graph = MagicMock(return_value=True)
    builder._content_provider = MagicMock(enabled=True)

    project_work_item(
        FactWorkItemRow(
            work_item_id="work-5",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
        ),
        builder=builder,
        fact_store=fact_store,
        fact_projector=lambda **_kwargs: {"files": 0},
        relationship_projector=lambda **_kwargs: {"files": 0, "imports": 0},
        workload_projector=lambda **_kwargs: {"workloads_projected": 0},
        platform_projector=lambda **_kwargs: {
            "infrastructure_platform_edges_projected": 0
        },
    )

    builder.reset_repository_subtree_in_graph.assert_called_once_with(
        "github.com/acme/service"
    )
    builder.delete_repository_from_graph.assert_not_called()
    builder._content_provider.delete_repository_content.assert_called_once_with(
        "github.com/acme/service"
    )
