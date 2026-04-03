"""Fact-emission helpers for the Phase 2 Git facts-first cutover."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import time
from typing import Any

from platform_context_graph.facts.emission import emit_git_snapshot_facts
from platform_context_graph.facts.emission.git_snapshot import (
    GitSnapshotFactEmissionResult,
)
from platform_context_graph.facts.state import get_fact_store
from platform_context_graph.facts.state import get_fact_work_queue
from platform_context_graph.facts.state import git_facts_first_enabled
from platform_context_graph.observability import get_observability
from platform_context_graph.observability.facts_first_logs import (
    log_snapshot_emitted,
)

from .coordinator_facts_support import refresh_fact_queue_metrics
from .coordinator_facts_support import repository_id_for_path
from .coordinator_facts_support import source_snapshot_id
from .coordinator_facts_support import utc_now


def facts_first_projection_enabled() -> bool:
    """Return whether Git indexing should switch to facts-first projection."""

    if not git_facts_first_enabled():
        return False
    fact_store = get_fact_store()
    work_queue = get_fact_work_queue()
    return bool(
        fact_store is not None
        and work_queue is not None
        and getattr(fact_store, "enabled", True)
        and getattr(work_queue, "enabled", True)
    )


def emit_repository_snapshot_facts(
    *,
    source_run_id: str,
    repo_path: Path,
    snapshot: object,
    is_dependency: bool,
    fact_store: object | None = None,
    work_queue: object | None = None,
    observed_at_fn: Callable[[], Any] = utc_now,
) -> GitSnapshotFactEmissionResult:
    """Persist facts for one parsed repository snapshot."""

    store = fact_store or get_fact_store()
    queue = work_queue or get_fact_work_queue()
    if store is None or queue is None:
        raise RuntimeError("facts-first indexing requires a configured fact runtime")

    resolved_repo_path = repo_path.resolve()
    repository_id = repository_id_for_path(resolved_repo_path)
    snapshot_id = source_snapshot_id(
        source_run_id=source_run_id,
        repo_path=resolved_repo_path,
    )
    observed_at = observed_at_fn()
    started = time.perf_counter()
    observability = get_observability()
    with observability.start_span(
        "pcg.facts.emit_snapshot",
        component="ingester",
        attributes={
            "pcg.repository_id": repository_id,
            "pcg.facts.source_run_id": source_run_id,
            "pcg.facts.source_snapshot_id": snapshot_id,
            "pcg.index.is_dependency": is_dependency,
        },
    ):
        result = emit_git_snapshot_facts(
            snapshot=snapshot,
            repository_id=repository_id,
            source_run_id=source_run_id,
            source_snapshot_id=snapshot_id,
            is_dependency=is_dependency,
            fact_store=store,
            work_queue=queue,
            observed_at=observed_at,
        )
    observability.record_fact_emission(
        component="ingester",
        source_system="git",
        work_type="project-git-facts",
        fact_count=result.fact_count,
        duration_seconds=max(time.perf_counter() - started, 0.0),
    )
    observability.record_fact_work_item(
        component="ingester",
        work_type="project-git-facts",
        outcome="enqueued",
    )
    refresh_fact_queue_metrics(queue, component="ingester")
    log_snapshot_emitted(
        repository_id=repository_id,
        source_run_id=source_run_id,
        source_snapshot_id=snapshot_id,
        work_item_id=result.work_item_id,
        fact_count=result.fact_count,
        is_dependency=is_dependency,
    )
    return result


def create_snapshot_fact_emitter(
    *,
    source_run_id: str,
    fact_store: object | None = None,
    work_queue: object | None = None,
    observed_at_fn: Callable[[], Any] = utc_now,
) -> Callable[..., GitSnapshotFactEmissionResult]:
    """Build the snapshot callback that persists facts for one run."""

    emission_results: dict[str, GitSnapshotFactEmissionResult] = {}

    def _emit_snapshot_facts(
        *,
        run_id: str,
        repo_path: Path,
        snapshot: object,
        is_dependency: bool,
    ) -> GitSnapshotFactEmissionResult:
        """Persist one parsed repository snapshot as durable facts."""

        del run_id
        result = emit_repository_snapshot_facts(
            source_run_id=source_run_id,
            repo_path=repo_path,
            snapshot=snapshot,
            is_dependency=is_dependency,
            fact_store=fact_store,
            work_queue=work_queue,
            observed_at_fn=observed_at_fn,
        )
        emission_results[str(repo_path.resolve())] = result
        return result

    setattr(_emit_snapshot_facts, "fact_emission_results", emission_results)
    return _emit_snapshot_facts
