"""Small shared metrics helpers for workload finalization."""

from __future__ import annotations

from typing import Any


def extract_cleanup_metrics(result: Any) -> dict[str, int]:
    """Return deleted node/relationship counters from one Neo4j result."""

    consume = getattr(result, "consume", None)
    summary = consume() if callable(consume) else None
    counters = getattr(summary, "counters", None)
    return {
        "cleanup_deleted_edges": int(
            getattr(counters, "relationships_deleted", 0) or 0
        ),
        "cleanup_deleted_nodes": int(getattr(counters, "nodes_deleted", 0) or 0),
    }


def merge_metrics(
    totals: dict[str, int],
    current: dict[str, int],
) -> dict[str, int]:
    """Merge integer metrics into one mutable totals mapping."""

    for key, value in current.items():
        totals[key] = totals.get(key, 0) + int(value)
    return totals


def run_cleanup_query(session: Any, query: str, /, **parameters: object) -> dict[str, int]:
    """Execute one cleanup query and return deleted node/edge counters."""

    return extract_cleanup_metrics(session.run(query, **parameters))


__all__ = ["extract_cleanup_metrics", "merge_metrics", "run_cleanup_query"]
