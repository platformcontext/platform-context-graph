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


def project_workload_facts(
    *,
    builder: Any,
    fact_records: Iterable[FactRecordRow],
    materialize_workloads_fn: Any | None = None,
    info_logger_fn: Any,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Materialize workloads for repositories represented by stored facts."""

    if materialize_workloads_fn is None:
        from platform_context_graph.resolution.workloads.materialization import (
            materialize_workloads,
        )

        materialize_workloads_fn = materialize_workloads

    return materialize_workloads_fn(
        builder,
        info_logger_fn=info_logger_fn,
        committed_repo_paths=repository_paths_from_facts(fact_records),
        progress_callback=progress_callback,
    )


def project_platform_facts(
    *,
    builder: Any,
    fact_records: Iterable[FactRecordRow],
    materialize_platforms_fn: Any | None = None,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Materialize infrastructure platform edges for fact-backed repositories."""

    if materialize_platforms_fn is None:
        from platform_context_graph.resolution.platforms import (
            materialize_infrastructure_platforms_for_repo_paths,
        )

        materialize_platforms_fn = materialize_infrastructure_platforms_for_repo_paths

    repo_paths = repository_paths_from_facts(fact_records)
    with builder.driver.session() as session:
        return materialize_platforms_fn(
            session,
            repo_paths=repo_paths,
            progress_callback=progress_callback,
        )


__all__ = [
    "project_platform_facts",
    "project_workload_facts",
    "repository_paths_from_facts",
]
