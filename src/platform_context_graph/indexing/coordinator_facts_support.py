"""Shared helpers for the facts-first indexing coordinator."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from platform_context_graph.facts.models.base import stable_fact_id
from platform_context_graph.observability import get_observability
from platform_context_graph.repository_identity import git_remote_for_path
from platform_context_graph.repository_identity import repository_metadata


def utc_now() -> datetime:
    """Return the current UTC timestamp for fact runtime writes."""

    return datetime.now(tz=timezone.utc)


def graph_store_adapter(builder: object) -> object:
    """Return the graph store adapter used by facts-first projection."""

    from .coordinator_storage import _graph_store_adapter as storage_adapter

    return storage_adapter(builder)


def repository_id_for_path(repo_path: Path) -> str:
    """Return the canonical repository identifier for one local checkout."""

    metadata = repository_metadata(
        name=repo_path.name,
        local_path=str(repo_path),
        remote_url=git_remote_for_path(repo_path),
    )
    return str(metadata["id"])


def source_snapshot_id(*, source_run_id: str, repo_path: Path) -> str:
    """Return a deterministic snapshot id for one repository in a run."""

    return stable_fact_id(
        fact_type="GitRepositorySnapshot",
        identity={
            "source_run_id": source_run_id,
            "repo_path": str(repo_path.resolve()),
        },
    )


def fact_metric_row_count(metrics: dict[str, Any] | None) -> int:
    """Return a best-effort row count derived from nested projection metrics."""

    if not isinstance(metrics, dict):
        return 0

    total = 0
    for value in metrics.values():
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            total += value
            continue
        if isinstance(value, dict):
            total += fact_metric_row_count(value)
    return total


def refresh_fact_queue_metrics(queue: object, *, component: str) -> None:
    """Update observable fact queue depth and lag gauges when supported."""

    snapshot_fn = getattr(queue, "list_queue_snapshot", None)
    if not callable(snapshot_fn):
        return
    observability = get_observability()
    for row in snapshot_fn():
        observability.set_fact_queue_depth(
            component=component,
            work_type=row.work_type,
            status=row.status,
            depth=row.depth,
        )
        observability.set_fact_queue_oldest_age_seconds(
            component=component,
            work_type=row.work_type,
            status=row.status,
            age_seconds=row.oldest_age_seconds,
        )


def clear_repository_projection_state(
    *,
    builder: object,
    repository_id: str,
    graph_store: object,
) -> None:
    """Delete graph/content state before facts-first reprojection."""

    graph_store.delete_repository(repository_id)
    content_provider = getattr(builder, "_content_provider", None)
    if content_provider is not None and getattr(content_provider, "enabled", False):
        content_provider.delete_repository_content(repository_id)


__all__ = [
    "fact_metric_row_count",
    "clear_repository_projection_state",
    "graph_store_adapter",
    "repository_id_for_path",
    "refresh_fact_queue_metrics",
    "source_snapshot_id",
    "utc_now",
]
