"""Facts-first coordinator helpers for the Phase 2 Git cutover."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from platform_context_graph.facts.emission.git_snapshot import (
    GitSnapshotFactEmissionResult,
)
from platform_context_graph.facts.models.base import stable_fact_id
from platform_context_graph.facts.state import get_fact_store
from platform_context_graph.facts.state import get_fact_work_queue
from platform_context_graph.facts.state import get_projection_decision_store
from platform_context_graph.facts.state import git_facts_first_enabled
from platform_context_graph.facts.storage.models import FactRunRow
from platform_context_graph.observability import get_observability
from platform_context_graph.observability.facts_first_logs import log_inline_projection
from platform_context_graph.resolution.orchestration import project_work_item

from .commit_timing import CommitTimingResult
from .coordinator_facts_emission import create_snapshot_fact_emitter
from .coordinator_facts_emission import emit_repository_snapshot_facts
from .coordinator_facts_emission import facts_first_projection_enabled
from .coordinator_facts_support import fact_metric_row_count
from .coordinator_facts_support import clear_repository_projection_state
from .coordinator_facts_support import graph_store_adapter
from .coordinator_facts_support import refresh_fact_queue_metrics
from .coordinator_facts_support import repository_id_for_path
from .coordinator_facts_support import source_snapshot_id
from .coordinator_facts_support import utc_now

__all__ = [
    "commit_repository_snapshot_from_facts",
    "create_facts_first_commit_callback",
    "create_snapshot_fact_emitter",
    "emit_repository_snapshot_facts",
    "finalize_fact_projection_batch",
    "finalize_facts_first_run",
    "git_facts_first_enabled",
    "project_repository_snapshot_facts",
]


def project_repository_snapshot_facts(
    builder: object,
    snapshot: object,
    *,
    fact_emission_result: GitSnapshotFactEmissionResult,
    fact_store: object | None = None,
    work_queue: object | None = None,
    decision_store: object | None = None,
    graph_store: object,
    project_work_item_fn: Callable[..., dict[str, Any] | None] = project_work_item,
    lease_owner: str = "indexing",
    lease_ttl_seconds: int = 300,
    info_logger_fn: Any = lambda *_args, **_kwargs: None,
    warning_logger_fn: Any = lambda *_args, **_kwargs: None,
    debug_log_fn: Any = lambda *_args, **_kwargs: None,
    progress_callback: Any | None = None,
    iter_snapshot_file_data_batches_fn: Any | None = None,
    repo_class: str | None = None,
) -> CommitTimingResult:
    """Project one emitted repository snapshot into canonical graph state."""

    del snapshot
    del progress_callback
    del iter_snapshot_file_data_batches_fn
    del repo_class

    store = fact_store or get_fact_store()
    queue = work_queue or get_fact_work_queue()
    decisions = decision_store or get_projection_decision_store()
    if store is None or queue is None:
        raise RuntimeError("facts-first indexing requires a configured fact runtime")

    started = time.perf_counter()
    observability = get_observability()
    with observability.start_span(
        "pcg.facts.inline_projection",
        component="ingester",
        attributes={
            "pcg.repository_id": fact_emission_result.repository_id,
            "pcg.facts.source_run_id": fact_emission_result.source_run_id,
            "pcg.facts.source_snapshot_id": fact_emission_result.source_snapshot_id,
            "pcg.facts.work_item_id": fact_emission_result.work_item_id,
            "pcg.facts.fact_count": fact_emission_result.fact_count,
            "pcg.queue.lease_owner": lease_owner,
            "pcg.queue.lease_ttl_seconds": lease_ttl_seconds,
        },
    ) as span:
        work_item = queue.lease_work_item(
            work_item_id=fact_emission_result.work_item_id,
            lease_owner=lease_owner,
            lease_ttl_seconds=lease_ttl_seconds,
        )
        if work_item is None:
            observability.record_fact_work_item(
                component="ingester",
                work_type="project-git-facts",
                outcome="lease_miss",
            )
            log_inline_projection(
                "lease_missed",
                repository_id=fact_emission_result.repository_id,
                source_run_id=fact_emission_result.source_run_id,
                work_item_id=fact_emission_result.work_item_id,
            )
            refresh_fact_queue_metrics(queue, component="ingester")
            raise RuntimeError(
                "facts-first projection could not lease work item "
                f"{fact_emission_result.work_item_id}"
            )
        if span is not None:
            span.set_attribute("pcg.queue.attempt_count", work_item.attempt_count)
        observability.record_fact_work_item(
            component="ingester",
            work_type=work_item.work_type,
            outcome="leased",
        )
        log_inline_projection(
            "leased",
            repository_id=work_item.repository_id,
            source_run_id=work_item.source_run_id,
            work_item_id=work_item.work_item_id,
            attempt_count=work_item.attempt_count,
        )
        refresh_fact_queue_metrics(queue, component="ingester")
        clear_repository_projection_state(
            builder=builder,
            repository_id=fact_emission_result.repository_id,
            graph_store=graph_store,
        )
    try:
        metrics = project_work_item_fn(
            work_item,
            builder=builder,
            fact_store=store,
            decision_store=decisions,
            info_logger_fn=info_logger_fn,
            debug_log_fn=debug_log_fn,
            warning_logger_fn=warning_logger_fn,
        )
    except Exception as exc:
        queue.fail_work_item(
            work_item_id=work_item.work_item_id,
            error_message=str(exc),
            terminal=False,
        )
        log_inline_projection(
            "failed",
            repository_id=work_item.repository_id,
            source_run_id=work_item.source_run_id,
            work_item_id=work_item.work_item_id,
            attempt_count=work_item.attempt_count,
            error_class=type(exc).__name__,
        )
        observability.record_fact_work_item(
            component="ingester",
            work_type=work_item.work_type,
            outcome="failed",
        )
        refresh_fact_queue_metrics(queue, component="ingester")
        raise

    queue.complete_work_item(work_item_id=work_item.work_item_id)
    log_inline_projection(
        "completed",
        repository_id=work_item.repository_id,
        source_run_id=work_item.source_run_id,
        work_item_id=work_item.work_item_id,
        attempt_count=work_item.attempt_count,
    )
    observability.record_fact_work_item(
        component="ingester",
        work_type=work_item.work_type,
        outcome="completed",
    )
    observability.record_resolution_stage_duration(
        component="ingester",
        work_type=work_item.work_type,
        stage="inline_projection",
        duration_seconds=max(time.perf_counter() - started, 0.0),
    )
    refresh_fact_queue_metrics(queue, component="ingester")
    timing = CommitTimingResult()
    timing.accumulate_graph_batch(
        duration_seconds=max(time.perf_counter() - started, 0.0),
        row_count=max(fact_metric_row_count(metrics), 1),
    )
    return timing


def commit_repository_snapshot_from_facts(
    *,
    builder: object,
    snapshot: object,
    fact_emission_result: GitSnapshotFactEmissionResult,
    fact_store: object | None = None,
    work_queue: object | None = None,
    decision_store: object | None = None,
    graph_store: object,
    project_work_item_fn: Callable[..., dict[str, Any] | None] = project_work_item,
    lease_owner: str = "indexing",
    lease_ttl_seconds: int = 300,
    info_logger_fn: Any = lambda *_args, **_kwargs: None,
    warning_logger_fn: Any = lambda *_args, **_kwargs: None,
    debug_log_fn: Any = lambda *_args, **_kwargs: None,
    progress_callback: Any | None = None,
    iter_snapshot_file_data_batches_fn: Any | None = None,
    repo_class: str | None = None,
) -> CommitTimingResult:
    """Compatibility wrapper for tests and coordinator callbacks."""

    return project_repository_snapshot_facts(
        builder,
        snapshot,
        fact_emission_result=fact_emission_result,
        fact_store=fact_store,
        work_queue=work_queue,
        decision_store=decision_store,
        graph_store=graph_store,
        project_work_item_fn=project_work_item_fn,
        lease_owner=lease_owner,
        lease_ttl_seconds=lease_ttl_seconds,
        info_logger_fn=info_logger_fn,
        warning_logger_fn=warning_logger_fn,
        debug_log_fn=debug_log_fn,
        progress_callback=progress_callback,
        iter_snapshot_file_data_batches_fn=iter_snapshot_file_data_batches_fn,
        repo_class=repo_class,
    )


def create_facts_first_commit_callback(
    *,
    builder: object,
    source_run_id: str,
    fact_store: object | None = None,
    work_queue: object | None = None,
    fact_emission_results: dict[str, GitSnapshotFactEmissionResult] | None = None,
    info_logger_fn: Any = lambda *_args, **_kwargs: None,
    warning_logger_fn: Any = lambda *_args, **_kwargs: None,
    observed_at_fn: Callable[[], Any] = utc_now,
) -> Callable[..., CommitTimingResult]:
    """Build the commit callback that projects graph state from facts."""

    store = fact_store or get_fact_store()
    queue = work_queue or get_fact_work_queue()
    if store is None or queue is None:
        raise RuntimeError("facts-first indexing requires a configured fact runtime")

    def _commit_snapshot_from_facts(
        _builder: object,
        snapshot: object,
        *,
        is_dependency: bool,
        progress_callback: Any | None = None,
        iter_snapshot_file_data_batches_fn: Any | None = None,
        repo_class: str | None = None,
        fact_emission_result: GitSnapshotFactEmissionResult | None = None,
        project_repository_snapshot_facts_fn: Callable[..., CommitTimingResult] = (
            project_repository_snapshot_facts
        ),
        graph_store_adapter_fn: Callable[[object], object] = graph_store_adapter,
    ) -> CommitTimingResult:
        """Project one repository snapshot into the graph from stored facts."""

        del _builder
        del is_dependency

        repo_path = Path(str(snapshot.repo_path)).resolve()
        repository_id = repository_id_for_path(repo_path)
        snapshot_id = source_snapshot_id(
            source_run_id=source_run_id,
            repo_path=repo_path,
        )
        emission_result = fact_emission_result
        if emission_result is None and fact_emission_results is not None:
            emission_result = fact_emission_results.get(str(repo_path))
        if emission_result is None:
            emission_result = GitSnapshotFactEmissionResult(
                repository_id=repository_id,
                source_run_id=source_run_id,
                source_snapshot_id=snapshot_id,
                work_item_id=stable_fact_id(
                    fact_type="FactProjectionWorkItem",
                    identity={
                        "repository_id": repository_id,
                        "source_run_id": source_run_id,
                        "source_snapshot_id": snapshot_id,
                    },
                ),
                fact_count=max(getattr(snapshot, "file_count", 0), 1),
            )
        try:
            timing = project_repository_snapshot_facts_fn(
                builder,
                snapshot,
                fact_emission_result=emission_result,
                fact_store=store,
                work_queue=queue,
                graph_store=graph_store_adapter_fn(builder),
                project_work_item_fn=project_work_item,
                lease_owner="indexing",
                lease_ttl_seconds=300,
                info_logger_fn=info_logger_fn,
                warning_logger_fn=warning_logger_fn,
                progress_callback=progress_callback,
                iter_snapshot_file_data_batches_fn=iter_snapshot_file_data_batches_fn,
                repo_class=repo_class,
            )
        except Exception:
            store.upsert_fact_run(
                FactRunRow(
                    source_run_id=source_run_id,
                    source_system="git",
                    source_snapshot_id=emission_result.source_snapshot_id,
                    repository_id=emission_result.repository_id,
                    status="failed",
                    started_at=observed_at_fn(),
                    completed_at=observed_at_fn(),
                )
            )
            raise

        store.upsert_fact_run(
            FactRunRow(
                source_run_id=source_run_id,
                source_system="git",
                source_snapshot_id=emission_result.source_snapshot_id,
                repository_id=emission_result.repository_id,
                status="completed",
                started_at=observed_at_fn(),
                completed_at=observed_at_fn(),
            )
        )
        return timing

    return _commit_snapshot_from_facts


def finalize_fact_projection_batch(*_args, **_kwargs) -> dict[str, float]:
    """Return an empty stage map for facts-first projection batches."""

    return {}


def finalize_facts_first_run(
    *,
    run_state: Any,
    persist_run_state_fn: Callable[[Any], None],
    delete_snapshots_fn: Callable[[str], None],
    publish_runtime_progress_fn: Callable[..., None],
    publish_run_repository_coverage_fn: Callable[..., None],
    builder: object,
    repo_paths: list[Path],
    committed_repo_paths: list[Path],
    component: str,
    source: str,
    utc_now_fn: Callable[[], str],
    run_started_at: str | None = None,
    last_metrics: dict[str, Any] | None = None,
) -> None:
    """Close out one facts-first indexing run without legacy finalization."""

    blocking_count = run_state.blocking_repositories()
    has_committed_repos = bool(committed_repo_paths)
    run_state.finalization_stage_details = (
        {"facts_projection": last_metrics.get("facts", {})}
        if isinstance(last_metrics, dict) and "facts" in last_metrics
        else {}
    )
    if not has_committed_repos and blocking_count > 0:
        run_state.status = "partial_failure"
        run_state.finalization_status = "pending"
        persist_run_state_fn(run_state)
        publish_run_repository_coverage_fn(
            builder=builder,
            run_state=run_state,
            repo_paths=repo_paths,
            include_graph_counts=True,
            include_content_counts=True,
        )
        publish_runtime_progress_fn(
            ingester=component,
            source=source,
            run_state=run_state,
            repository_count=len(repo_paths),
            status="partial_failure",
        )
        return

    finished_at = utc_now_fn()
    run_state.status = "completed"
    run_state.finalization_status = "completed"
    run_state.finalization_started_at = run_started_at or finished_at
    run_state.finalization_finished_at = finished_at
    run_state.finalization_duration_seconds = 0.0
    run_state.finalization_current_stage = None
    run_state.finalization_stage_started_at = None
    run_state.finalization_stage_durations = {}
    persist_run_state_fn(run_state)
    publish_run_repository_coverage_fn(
        builder=builder,
        run_state=run_state,
        repo_paths=repo_paths,
        include_graph_counts=True,
        include_content_counts=True,
    )
    publish_runtime_progress_fn(
        ingester=component,
        source=source,
        run_state=run_state,
        repository_count=len(repo_paths),
        status="completed",
        last_success_at=finished_at,
    )
    delete_snapshots_fn(run_state.run_id)
