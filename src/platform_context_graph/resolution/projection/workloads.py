"""Workload and platform projection helpers driven by stored Git facts."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from typing import Iterable

from platform_context_graph.facts.storage.models import FactRecordRow

from .repositories import iter_repository_facts


def repository_paths_from_facts(
    fact_records: Iterable[FactRecordRow],
) -> list[Path]:
    """Return targeted repository paths rebuilt from repository facts."""

    return [
        Path(fact.checkout_path).resolve()
        for fact in iter_repository_facts(fact_records)
    ]


def repository_projection_context_from_facts(
    fact_records: Iterable[FactRecordRow],
) -> dict[str, dict[str, str]]:
    """Return stable per-repository shadow projection context from facts."""

    context_by_repo_id: dict[str, dict[str, str]] = {}
    for fact in iter_repository_facts(fact_records):
        if (
            not fact.repository_id
            or not fact.source_run_id
            or not fact.source_snapshot_id
        ):
            continue
        context_by_repo_id.setdefault(
            fact.repository_id,
            {
                "generation_id": fact.source_snapshot_id,
                "source_run_id": fact.source_run_id,
            },
        )
    return context_by_repo_id


def project_workload_facts(
    *,
    builder: Any,
    fact_records: Iterable[FactRecordRow],
    materialize_workloads_fn: Any | None = None,
    info_logger_fn: Any,
    progress_callback: Any | None = None,
    shared_projection_intent_store: Any | None = None,
) -> dict[str, int]:
    """Materialize workloads for repositories represented by stored facts."""

    if materialize_workloads_fn is None:
        from platform_context_graph.resolution.workloads.materialization import (
            materialize_workloads,
        )

        materialize_workloads_fn = materialize_workloads
    if shared_projection_intent_store is None:
        from platform_context_graph.facts.state import (
            get_shared_projection_intent_store,
        )

        shared_projection_intent_store = get_shared_projection_intent_store()

    return materialize_workloads_fn(
        builder,
        info_logger_fn=info_logger_fn,
        committed_repo_paths=repository_paths_from_facts(fact_records),
        progress_callback=progress_callback,
        projection_context_by_repo_id=repository_projection_context_from_facts(
            fact_records
        ),
        shared_projection_intent_store=shared_projection_intent_store,
    )


def project_platform_facts(
    *,
    builder: Any,
    fact_records: Iterable[FactRecordRow],
    materialize_platforms_fn: Any | None = None,
    progress_callback: Any | None = None,
    shared_projection_intent_store: Any | None = None,
) -> dict[str, int]:
    """Materialize infrastructure platform edges for fact-backed repositories."""

    if materialize_platforms_fn is None:
        from platform_context_graph.resolution.platforms import (
            materialize_infrastructure_platforms_for_repo_paths,
        )

        materialize_platforms_fn = materialize_infrastructure_platforms_for_repo_paths
    if shared_projection_intent_store is None:
        from platform_context_graph.facts.state import (
            get_shared_projection_intent_store,
        )

        shared_projection_intent_store = get_shared_projection_intent_store()

    repo_paths = repository_paths_from_facts(fact_records)
    with builder.driver.session() as session:
        return materialize_platforms_fn(
            session,
            repo_paths=repo_paths,
            progress_callback=progress_callback,
            projection_context_by_repo_id=repository_projection_context_from_facts(
                fact_records
            ),
            shared_projection_intent_store=shared_projection_intent_store,
        )


__all__ = [
    "project_platform_facts",
    "project_workload_facts",
    "repository_projection_context_from_facts",
    "repository_paths_from_facts",
]
