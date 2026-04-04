"""Core orchestration hooks for fact-driven graph projection."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
import time
from typing import Any

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
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
    decision_store: Any | None = None,
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
                    entity_batches = _load_entity_batches(
                        fact_store, work_item,
                    )
                    total_fact_count = (
                        len(graph_facts) + sum(len(b) for b in entity_batches)
                    )
                else:
                    # Fallback for stores without partitioned loading (tests).
                    graph_facts = fact_store.list_facts(
                        repository_id=work_item.repository_id,
                        source_run_id=work_item.source_run_id,
                    )
                    entity_batches = []
                    total_fact_count = len(graph_facts)
        except Exception as exc:
            observability.record_resolution_stage_failure(
                component="resolution-engine",
                work_type=work_item.work_type,
                stage="load_facts",
                error_class=type(exc).__name__,
            )
            raise
        observability.record_resolution_stage_duration(
            component="resolution-engine",
            work_type=work_item.work_type,
            stage="load_facts",
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
                    raise
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
            "project_facts",
            lambda: fact_projector(builder=builder, fact_records=graph_facts),
        )

        # -- Stage 1b: stream standalone entity facts in batches -----------
        if entity_batches:
            entity_extra = _run_stage(
                "project_entity_batches",
                lambda: _project_entity_batches(builder, entity_batches, graph_facts),
            )
            fact_metrics["entities"] = (
                fact_metrics.get("entities", 0) + entity_extra.get("entities", 0)
            )

        # -- Stage 2: relationships ----------------------------------------
        relationship_metrics = _run_stage(
            "project_relationships",
            lambda: relationship_projector(
                builder=builder,
                fact_records=graph_facts,
                debug_log_fn=debug_log_fn,
                warning_logger_fn=warning_logger_fn,
            ),
        )
        _record_projection_decision(
            decision_store=decision_store,
            stage="project_relationships",
            work_item=work_item,
            fact_records=graph_facts,
            metrics=relationship_metrics,
        )

        # -- Stage 3: workloads --------------------------------------------
        workload_metrics = _run_stage(
            "project_workloads",
            lambda: workload_projector(
                builder=builder,
                fact_records=graph_facts,
                info_logger_fn=info_logger_fn,
            ),
        )
        _record_projection_decision(
            decision_store=decision_store,
            stage="project_workloads",
            work_item=work_item,
            fact_records=graph_facts,
            metrics=workload_metrics,
        )

        # -- Stage 4: platforms --------------------------------------------
        platform_metrics = _run_stage(
            "project_platforms",
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
    return {
        "facts": fact_metrics,
        "relationships": relationship_metrics,
        "workloads": workload_metrics,
        "platforms": platform_metrics,
    }


def _load_entity_batches(
    fact_store: Any,
    work_item: FactWorkItemRow,
) -> list[list[FactRecordRow]]:
    """Load entity fact batches when the store supports partitioned reads."""

    iter_batches = getattr(type(fact_store), "iter_fact_batches", None)
    if not callable(iter_batches):
        return []
    return fact_store.iter_fact_batches(
        repository_id=work_item.repository_id,
        source_run_id=work_item.source_run_id,
        fact_type="ParsedEntityObserved",
        batch_size=2000,
    )


def _project_entity_batches(
    builder: Any,
    entity_batches: list[list[FactRecordRow]],
    graph_facts: list[FactRecordRow],
) -> dict[str, int]:
    """Project standalone entity facts that were streamed separately.

    Entities already projected from FileObserved payloads (via
    ``project_parsed_entity_facts``) are skipped using the same
    file-key deduplication the original code path uses.
    """

    from platform_context_graph.resolution.projection.entities import (
        iter_parsed_entity_facts,
        build_entity_merge_statement,
    )
    from platform_context_graph.resolution.projection.files import iter_file_facts
    from platform_context_graph.resolution.projection.common import (
        run_managed_write,
        run_write_query,
    )

    # Build the set of file keys already projected from FileObserved payloads.
    projected_file_keys: set[tuple[str, str]] = set()
    for file_fact in iter_file_facts(graph_facts):
        if not file_fact.relative_path:
            continue
        parsed_file_data = file_fact.payload.get("parsed_file_data")
        if isinstance(parsed_file_data, dict):
            projected_file_keys.add(
                (file_fact.checkout_path, file_fact.relative_path)
            )

    projected = 0

    def _write_batch(tx: object, batch: list[FactRecordRow]) -> int:
        count = 0
        for fact_record in iter_parsed_entity_facts(batch):
            if not fact_record.relative_path:
                continue
            if (
                fact_record.checkout_path,
                fact_record.relative_path,
            ) in projected_file_keys:
                continue
            from pathlib import Path

            file_path = str(
                Path(fact_record.checkout_path).resolve() / fact_record.relative_path
            )
            entity_payload = {
                "name": str(fact_record.payload.get("entity_name") or ""),
                "line_number": int(fact_record.payload.get("start_line") or 0),
                "end_line": int(fact_record.payload.get("end_line") or 0),
                "lang": fact_record.payload.get("language"),
            }
            query, params = build_entity_merge_statement(
                label=str(fact_record.payload.get("entity_kind") or ""),
                item=entity_payload,
                file_path=file_path,
                use_uid_identity=False,
            )
            run_write_query(tx, query, **params)
            count += 1
        return count

    with builder.driver.session() as session:
        for batch in entity_batches:
            def _write(tx: object, _batch: list[FactRecordRow] = batch) -> None:
                nonlocal projected
                projected += _write_batch(tx, _batch)

            run_managed_write(session, _write)

    return {"entities": projected}
