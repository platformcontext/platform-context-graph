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


def merge_projection_metrics(
    totals: dict[str, int],
    current: dict[str, object],
) -> dict[str, int]:
    """Merge projection metrics while skipping nested structured payloads."""

    for key, value in current.items():
        if isinstance(value, dict):
            continue
        totals[key] = totals.get(key, 0) + int(value)
    return totals


def merge_shared_projection_payload(
    totals: dict[str, object],
    current: dict[str, object],
) -> dict[str, object]:
    """Merge authoritative shared projection metadata from one metrics payload."""

    payload = current.get("shared_projection")
    if not isinstance(payload, dict):
        return totals
    merged = dict(totals.get("shared_projection") or {})
    existing_domains = {
        str(domain).strip()
        for domain in merged.get("authoritative_domains", [])
        if str(domain).strip()
    }
    current_domains = {
        str(domain).strip()
        for domain in payload.get("authoritative_domains", [])
        if str(domain).strip()
    }
    all_domains = sorted(existing_domains | current_domains)
    if all_domains:
        merged["authoritative_domains"] = all_domains
    intent_count = int(merged.get("intent_count") or 0) + int(
        payload.get("intent_count") or 0
    )
    if intent_count:
        merged["intent_count"] = intent_count
    accepted_generation_ids = {
        str(value).strip()
        for value in (
            merged.get("accepted_generation_id"),
            payload.get("accepted_generation_id"),
        )
        if str(value).strip()
    }
    if len(accepted_generation_ids) == 1:
        merged["accepted_generation_id"] = next(iter(accepted_generation_ids))
    elif accepted_generation_ids:
        merged["accepted_generation_id"] = None
    if merged:
        totals["shared_projection"] = merged
    return totals


def run_cleanup_query(
    session: Any, query: str, /, **parameters: object
) -> dict[str, int]:
    """Execute one cleanup query and return deleted node/edge counters."""

    return extract_cleanup_metrics(session.run(query, **parameters))


__all__ = [
    "extract_cleanup_metrics",
    "merge_metrics",
    "merge_projection_metrics",
    "merge_shared_projection_payload",
    "run_cleanup_query",
]
