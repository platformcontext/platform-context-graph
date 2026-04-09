"""Core orchestration hooks for fact-driven graph projection."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
import time
from collections.abc import Iterable
from typing import Any

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.facts.work_queue.stages import LOAD_FACTS_STAGE
from platform_context_graph.facts.work_queue.stages import PROJECT_ENTITY_BATCHES_STAGE
from platform_context_graph.facts.work_queue.stages import PROJECT_FACTS_STAGE
from platform_context_graph.facts.work_queue.stages import PROJECT_PLATFORMS_STAGE
from platform_context_graph.facts.work_queue.stages import PROJECT_RELATIONSHIPS_STAGE
from platform_context_graph.facts.work_queue.stages import PROJECT_WORKLOADS_STAGE
from platform_context_graph.facts.work_queue.stages import ProjectionStageError
from platform_context_graph.observability import get_observability
from platform_context_graph.observability.facts_first_logs import (
    log_projection_decision,
    log_resolution_stage_failure,
    log_resolution_work_item,
)
from platform_context_graph.resolution.decisions.recording import (
    build_projection_decision,
)
from platform_context_graph.resolution.decisions.recording import (
    build_projection_evidence,
)
from platform_context_graph.resolution.projection import project_git_fact_records
from platform_context_graph.resolution.projection.relationships import (
    project_git_relationship_fact_records,
)
from platform_context_graph.resolution.projection.workloads import (
    project_platform_facts,
    project_workload_facts,
)
from platform_context_graph.resolution.shared_projection import (
    run_inline_shared_followup,
)
from platform_context_graph.resolution.workloads.metrics import (
    merge_shared_projection_payload,
)


def _metric_output_count(metrics: Any) -> int:
    """Return a best-effort projected output count from nested stage metrics."""

    if isinstance(metrics, bool):
        return 0
    if isinstance(metrics, int):
        return metrics
    if isinstance(metrics, dict):
        return sum(_metric_output_count(value) for value in metrics.values())
    if isinstance(metrics, (list, tuple, set)):
        return sum(_metric_output_count(value) for value in metrics)
    return 0


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(tz=timezone.utc)


def _record_projection_decision(
    *,
    decision_store: Any | None,
    stage: str,
    work_item: FactWorkItemRow,
    fact_records: list[FactRecordRow],
    metrics: Any,
) -> None:
    """Persist one bounded projection decision when a store is configured."""

    if decision_store is None:
        return
    observability = get_observability()
    created_at = _utc_now()
    decision = build_projection_decision(
        stage=stage,
        work_item=work_item,
        fact_records=fact_records,
        output_count=_metric_output_count(metrics),
        created_at=created_at,
    )
    decision_store.upsert_decision(decision)
    evidence = build_projection_evidence(
        decision=decision,
        fact_records=fact_records,
        created_at=created_at,
    )
    if evidence:
        decision_store.insert_evidence(evidence)
    observability.record_projection_decision(
        component="resolution-engine",
        decision_type=decision.decision_type,
        confidence_score=decision.confidence_score,
        evidence_count=len(evidence),
    )
    log_projection_decision(
        repository_id=work_item.repository_id,
        source_run_id=work_item.source_run_id,
        work_item_id=work_item.work_item_id,
        decision_id=decision.decision_id,
        decision_type=decision.decision_type,
        confidence_score=decision.confidence_score,
        evidence_count=len(evidence),
    )


def _clear_repository_projection_state(*, builder: Any, repository_id: str) -> None:
    """Delete existing graph and content state before reprojection."""

    reset_repository = getattr(builder, "reset_repository_subtree_in_graph", None)
    if callable(reset_repository):
        reset_repository(repository_id)
    else:
        delete_repository = getattr(builder, "delete_repository_from_graph", None)
        if callable(delete_repository):
            delete_repository(repository_id)
    content_provider = getattr(builder, "_content_provider", None)
    if content_provider is not None and getattr(content_provider, "enabled", False):
        content_provider.delete_repository_content(repository_id)


def project_work_item(
    work_item: FactWorkItemRow,
    *,
    builder: Any | None = None,
    fact_store: Any | None = None,
    fact_work_queue: Any | None = None,
    decision_store: Any | None = None,
    shared_projection_intent_store: Any | None = None,
    fact_projector: Any = project_git_fact_records,
    relationship_projector: Any = project_git_relationship_fact_records,
    workload_projector: Any = project_workload_facts,
    platform_projector: Any = project_platform_facts,
    info_logger_fn: Any = lambda *_args, **_kwargs: None,
    debug_log_fn: Any = lambda *_args, **_kwargs: None,
    warning_logger_fn: Any = lambda *_args, **_kwargs: None,
) -> dict[str, Any] | None:
    """Project one work item into canonical graph state.

    Loads facts partitioned by type to keep peak memory proportional to
    file count rather than total fact count.  Entity facts (the bulk) are
    streamed in batches so a single 200K-fact repository never materialises
    the full result set in Python.

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
        _clear_repository_projection_state(
            builder=builder,
            repository_id=work_item.repository_id,
        )

        # ----------------------------------------------------------------
        # Partitioned fact loading: load by type to bound peak memory.
        # Repository + file facts are loaded eagerly (bounded by file count).
        # Entity facts are streamed in batches during projection.
        # ----------------------------------------------------------------
        load_started = time.perf_counter()
        list_by_type = getattr(type(fact_store), "list_facts_by_type", None)
        try:
            with observability.start_span(
                "pcg.resolution.load_facts",
                component="resolution-engine",
                attributes={"pcg.facts.work_item_id": work_item.work_item_id},
            ):
                if callable(list_by_type):
                    repo_facts = fact_store.list_facts_by_type(
                        repository_id=work_item.repository_id,
                        source_run_id=work_item.source_run_id,
                        fact_type="RepositoryObserved",
                    )
                    file_facts = fact_store.list_facts_by_type(
                        repository_id=work_item.repository_id,
                        source_run_id=work_item.source_run_id,
                        fact_type="FileObserved",
                    )
                    graph_facts: list[FactRecordRow] = repo_facts + file_facts
                    count_facts = getattr(type(fact_store), "count_facts", None)
                    total_fact_count = (
                        fact_store.count_facts(
                            repository_id=work_item.repository_id,
                            source_run_id=work_item.source_run_id,
                        )
                        if callable(count_facts)
                        else len(graph_facts)
                    )
                    entity_batches = (
                        _load_entity_batches(fact_store, work_item)
                        if total_fact_count > len(graph_facts)
                        else None
                    )
                else:
                    # Fallback for stores without partitioned loading (tests).
                    graph_facts = fact_store.list_facts(
                        repository_id=work_item.repository_id,
                        source_run_id=work_item.source_run_id,
                    )
                    entity_batches = None
                    total_fact_count = len(graph_facts)
        except Exception as exc:
            observability.record_resolution_stage_failure(
                component="resolution-engine",
                work_type=work_item.work_type,
                stage=LOAD_FACTS_STAGE,
                error_class=type(exc).__name__,
            )
            raise ProjectionStageError(LOAD_FACTS_STAGE, exc) from exc
        observability.record_resolution_stage_duration(
            component="resolution-engine",
            work_type=work_item.work_type,
            stage=LOAD_FACTS_STAGE,
            duration_seconds=max(time.perf_counter() - load_started, 0.0),
        )
        observability.record_resolution_facts_loaded(
            component="resolution-engine",
            work_type=work_item.work_type,
            fact_count=total_fact_count,
        )

        def _run_stage(stage: str, callback: Any) -> dict[str, Any]:
            """Execute a projection stage with observability and error handling."""
            started = time.perf_counter()
            with observability.start_span(
                f"pcg.resolution.{stage}",
                component="resolution-engine",
                attributes={"pcg.facts.work_item_id": work_item.work_item_id},
            ):
                try:
                    metrics = callback()
                except Exception as exc:
                    log_resolution_stage_failure(
                        repository_id=work_item.repository_id,
                        source_run_id=work_item.source_run_id,
                        work_item_id=work_item.work_item_id,
                        work_type=work_item.work_type,
                        attempt_count=work_item.attempt_count,
                        stage=stage,
                        error_class=type(exc).__name__,
                    )
                    observability.record_resolution_stage_failure(
                        component="resolution-engine",
                        work_type=work_item.work_type,
                        stage=stage,
                        error_class=type(exc).__name__,
                    )
                    raise ProjectionStageError(stage, exc) from exc
            observability.record_resolution_stage_duration(
                component="resolution-engine",
                work_type=work_item.work_type,
                stage=stage,
                duration_seconds=max(time.perf_counter() - started, 0.0),
            )
            observability.record_resolution_stage_output(
                component="resolution-engine",
                work_type=work_item.work_type,
                stage=stage,
                output_count=_metric_output_count(metrics),
            )
            return metrics

        # -- Stage 1: repos + files + entities-from-file-payloads ----------
        fact_metrics = _run_stage(
            PROJECT_FACTS_STAGE,
            lambda: fact_projector(builder=builder, fact_records=graph_facts),
        )

        # -- Stage 1b: stream standalone entity facts in batches -----------
        if entity_batches is not None:
            entity_extra = _run_stage(
                PROJECT_ENTITY_BATCHES_STAGE,
                lambda: _project_entity_batches(builder, entity_batches, graph_facts),
            )
            fact_metrics["entities"] = fact_metrics.get(
                "entities", 0
            ) + entity_extra.get("entities", 0)

        # -- Stage 2: relationships ----------------------------------------
        relationship_metrics = _run_stage(
            PROJECT_RELATIONSHIPS_STAGE,
            lambda: relationship_projector(
                builder=builder,
                fact_records=graph_facts,
                debug_log_fn=debug_log_fn,
                warning_logger_fn=warning_logger_fn,
            ),
        )
        _record_projection_decision(
            decision_store=decision_store,
            stage=PROJECT_RELATIONSHIPS_STAGE,
            work_item=work_item,
            fact_records=graph_facts,
            metrics=relationship_metrics,
        )

        # -- Stage 3: workloads --------------------------------------------
        workload_metrics = _run_stage(
            PROJECT_WORKLOADS_STAGE,
            lambda: workload_projector(
                builder=builder,
                fact_records=graph_facts,
                info_logger_fn=info_logger_fn,
            ),
        )
        _record_projection_decision(
            decision_store=decision_store,
            stage=PROJECT_WORKLOADS_STAGE,
            work_item=work_item,
            fact_records=graph_facts,
            metrics=workload_metrics,
        )

        # -- Stage 4: platforms --------------------------------------------
        platform_metrics = _run_stage(
            PROJECT_PLATFORMS_STAGE,
            lambda: platform_projector(
                builder=builder,
                fact_records=graph_facts,
            ),
        )
        _record_projection_decision(
            decision_store=decision_store,
            stage="project_platforms",
            work_item=work_item,
            fact_records=graph_facts,
            metrics=platform_metrics,
        )

        log_resolution_work_item(
            "projected",
            repository_id=work_item.repository_id,
            source_run_id=work_item.source_run_id,
            work_item_id=work_item.work_item_id,
            work_type=work_item.work_type,
            attempt_count=work_item.attempt_count,
            fact_count=total_fact_count,
            output_count=_metric_output_count(
                {
                    "facts": fact_metrics,
                    "relationships": relationship_metrics,
                    "workloads": workload_metrics,
                    "platforms": platform_metrics,
                }
            ),
        )

    shared_followup_metrics: dict[str, object] = {}
    merge_shared_projection_payload(shared_followup_metrics, workload_metrics)
    merge_shared_projection_payload(shared_followup_metrics, platform_metrics)
    shared_payload = shared_followup_metrics.get("shared_projection")
    if isinstance(shared_payload, dict):
        accepted_generation_id = str(
            shared_payload.get("accepted_generation_id") or ""
        ).strip()
        if accepted_generation_id:
            if fact_work_queue is None:
                from platform_context_graph.facts.state import get_fact_work_queue

                fact_work_queue = get_fact_work_queue()
            if shared_projection_intent_store is None:
                from platform_context_graph.facts.state import (
                    get_shared_projection_intent_store,
                )

                shared_projection_intent_store = get_shared_projection_intent_store()
            shared_followup_metrics = run_inline_shared_followup(
                builder=builder,
                repository_id=work_item.repository_id,
                source_run_id=work_item.source_run_id,
                accepted_generation_id=accepted_generation_id,
                authoritative_domains=list(
                    shared_payload.get("authoritative_domains") or []
                ),
                fact_work_queue=fact_work_queue,
                shared_projection_intent_store=shared_projection_intent_store,
            )

    result = {
        "facts": fact_metrics,
        "relationships": relationship_metrics,
        "workloads": workload_metrics,
        "platforms": platform_metrics,
    }
    if shared_followup_metrics:
        result["shared_projection"] = shared_followup_metrics
    return result


def _load_entity_batches(
    fact_store: Any,
    work_item: FactWorkItemRow,
) -> Iterable[list[FactRecordRow]] | None:
    """Load entity fact batches when the store supports partitioned reads."""

    iter_batches = getattr(type(fact_store), "iter_fact_batches", None)
    if not callable(iter_batches):
        return None
    return fact_store.iter_fact_batches(
        repository_id=work_item.repository_id,
        source_run_id=work_item.source_run_id,
        fact_type="ParsedEntityObserved",
        batch_size=2000,
    )


def _project_entity_batches(
    builder: Any,
    entity_batches: Iterable[list[FactRecordRow]],
    graph_facts: list[FactRecordRow],
) -> dict[str, int]:
    """Project standalone entity facts that were streamed separately.

    Entities already projected from FileObserved payloads (via
    ``project_parsed_entity_facts``) are skipped using the same
    file-key deduplication the original code path uses.
    """

    from platform_context_graph.resolution.projection.entities import (
        _project_standalone_entity_facts,
    )
    from platform_context_graph.resolution.projection.files import iter_file_facts
    from platform_context_graph.resolution.projection.common import run_managed_write

    # Build the set of file keys already projected from FileObserved payloads.
    projected_file_keys: set[tuple[str, str]] = set()
    for file_fact in iter_file_facts(graph_facts):
        if not file_fact.relative_path:
            continue
        parsed_file_data = file_fact.payload.get("parsed_file_data")
        if isinstance(parsed_file_data, dict):
            projected_file_keys.add((file_fact.checkout_path, file_fact.relative_path))

    projected = 0
    with builder.driver.session() as session:
        for batch in entity_batches:

            def _write(tx: object, _batch: list[FactRecordRow] = batch) -> None:
                """Project one bounded parsed-entity batch inside a managed write."""

                nonlocal projected
                projected += _project_standalone_entity_facts(
                    tx,
                    _batch,
                    projected_file_keys=projected_file_keys,
                )

            run_managed_write(session, _write)

    return {"entities": projected}
