"""Core orchestration hooks for fact-driven graph projection."""

from __future__ import annotations

import time
from typing import Any

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.observability import get_observability
from platform_context_graph.resolution.projection import project_git_fact_records
from platform_context_graph.resolution.projection.relationships import (
    project_git_relationship_fact_records,
)
from platform_context_graph.resolution.projection.workloads import (
    project_platform_facts,
    project_workload_facts,
)


def project_work_item(
    work_item: FactWorkItemRow,
    *,
    builder: Any | None = None,
    fact_store: Any | None = None,
    fact_projector: Any = project_git_fact_records,
    relationship_projector: Any = project_git_relationship_fact_records,
    workload_projector: Any = project_workload_facts,
    platform_projector: Any = project_platform_facts,
    info_logger_fn: Any = lambda *_args, **_kwargs: None,
    debug_log_fn: Any = lambda *_args, **_kwargs: None,
    warning_logger_fn: Any = lambda *_args, **_kwargs: None,
) -> dict[str, Any] | None:
    """Project one work item into canonical graph state.

    Args:
        work_item: The claimed work item to process.
    """

    if builder is None or fact_store is None:
        return None

    observability = get_observability()
    with observability.start_span(
        "pcg.resolution.project_work_item",
        component="resolution-engine",
        attributes={
            "pcg.repository_id": work_item.repository_id,
            "pcg.facts.source_run_id": work_item.source_run_id,
            "pcg.facts.work_item_id": work_item.work_item_id,
            "pcg.queue.attempt_count": work_item.attempt_count,
        },
    ):
        load_started = time.perf_counter()
        with observability.start_span(
            "pcg.resolution.load_facts",
            component="resolution-engine",
            attributes={"pcg.facts.work_item_id": work_item.work_item_id},
        ):
            fact_records: list[FactRecordRow] = fact_store.list_facts(
                repository_id=work_item.repository_id,
                source_run_id=work_item.source_run_id,
            )
        observability.record_resolution_stage_duration(
            component="resolution-engine",
            work_type=work_item.work_type,
            stage="load_facts",
            duration_seconds=max(time.perf_counter() - load_started, 0.0),
        )
        observability.record_resolution_facts_loaded(
            component="resolution-engine",
            work_type=work_item.work_type,
            fact_count=len(fact_records),
        )

        def _run_stage(stage: str, callback: Any) -> dict[str, Any]:
            started = time.perf_counter()
            with observability.start_span(
                f"pcg.resolution.{stage}",
                component="resolution-engine",
                attributes={"pcg.facts.work_item_id": work_item.work_item_id},
            ):
                metrics = callback()
            observability.record_resolution_stage_duration(
                component="resolution-engine",
                work_type=work_item.work_type,
                stage=stage,
                duration_seconds=max(time.perf_counter() - started, 0.0),
            )
            return metrics

        fact_metrics = _run_stage(
            "project_facts",
            lambda: fact_projector(builder=builder, fact_records=fact_records),
        )
        relationship_metrics = _run_stage(
            "project_relationships",
            lambda: relationship_projector(
                builder=builder,
                fact_records=fact_records,
                debug_log_fn=debug_log_fn,
                warning_logger_fn=warning_logger_fn,
            ),
        )
        workload_metrics = _run_stage(
            "project_workloads",
            lambda: workload_projector(
                builder=builder,
                fact_records=fact_records,
                info_logger_fn=info_logger_fn,
            ),
        )
        platform_metrics = _run_stage(
            "project_platforms",
            lambda: platform_projector(
                builder=builder,
                fact_records=fact_records,
            ),
        )
    return {
        "facts": fact_metrics,
        "relationships": relationship_metrics,
        "workloads": workload_metrics,
        "platforms": platform_metrics,
    }
