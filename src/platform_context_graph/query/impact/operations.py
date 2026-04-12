"""High-level impact query operations over the in-memory graph store."""

from __future__ import annotations

from typing import Any

from ...domain import EntityType
from ..data_change_classification import (
    classify_data_change,
    classify_impacted_data_change,
    summarize_data_change_classifications,
)
from .common import dedupe_evidence
from ..data_lineage_evidence import merge_lineage_summaries, summarize_lineage_hops
from .store import _GraphStore


def path_summary(hops: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a graph path into a portable response payload.

    Args:
        hops: Traversal hops forming a path.

    Returns:
        Path summary with confidence, reason, and evidence.
    """

    evidence = dedupe_evidence(item for hop in hops for item in hop.get("evidence", []))
    confidences = [float(hop.get("confidence") or 0.0) for hop in hops] or [0.0]
    reason = hops[-1].get("reason") if hops else None
    lineage_evidence = summarize_lineage_hops(hops)
    return {
        "source": hops[0]["from"] if hops else None,
        "target": hops[-1]["to"] if hops else None,
        "hops": hops,
        "confidence": round(min(confidences), 2),
        "reason": reason,
        "evidence": evidence,
        **(
            {"lineage_evidence": lineage_evidence}
            if lineage_evidence is not None
            else {}
        ),
    }


def path_sort_key(
    summary: dict[str, Any],
    environment: str | None,
) -> tuple[int, float, int, str]:
    """Return a sort key that favors environment-specific, high-confidence paths.

    Args:
        summary: Path summary payload.
        environment: Optional preferred environment.

    Returns:
        Sort key used to rank candidate paths.
    """

    hops = summary.get("hops", [])
    first_target = hops[0]["to"] if hops else {}
    first_type = first_target.get("type")
    confidence = float(summary.get("confidence") or 0.0)
    if environment:
        if first_type == EntityType.workload_instance.value and first_target.get(
            "environment"
        ) in {None, environment}:
            priority = 0
        elif first_type == EntityType.cloud_resource.value:
            priority = 1
        elif first_type == EntityType.workload.value:
            priority = 2
        else:
            priority = 3
        return (priority, -confidence, len(hops), summary["target"]["id"])
    return (0, -confidence, len(hops), summary["target"]["id"])


def trace_resource_to_code_store(
    store: _GraphStore,
    *,
    start_id: str,
    environment: str | None,
    max_depth: int,
) -> dict[str, Any]:
    """Trace a resource to the repositories that define or consume it.

    Args:
        store: In-memory impact graph store.
        start_id: Starting entity identifier.
        environment: Optional preferred environment.
        max_depth: Maximum traversal depth.

    Returns:
        Resource-to-code trace response payload.
    """

    paths = store.paths_to(
        source_id=start_id,
        target_predicate=lambda ref: ref["type"] == EntityType.repository.value,
        environment=environment,
        max_depth=max_depth,
    )

    summaries = [path_summary(hops) for hops in paths]
    summaries.sort(key=lambda item: path_sort_key(item, environment))
    top = summaries[0] if summaries else None
    lineage_evidence = merge_lineage_summaries(
        summary.get("lineage_evidence") for summary in summaries
    )
    return {
        "start": store.snapshot(start_id),
        "environment": environment,
        "paths": summaries,
        "confidence": top["confidence"] if top else 0.0,
        "reason": top["reason"] if top else f"No repository path found for {start_id}",
        "evidence": top["evidence"] if top else [],
        **(
            {"lineage_evidence": lineage_evidence}
            if lineage_evidence is not None
            else {}
        ),
    }


def explain_dependency_path_store(
    store: _GraphStore,
    *,
    source_id: str,
    target_id: str,
    environment: str | None,
    max_depth: int,
) -> dict[str, Any]:
    """Explain the dependency path between two entities.

    Args:
        store: In-memory impact graph store.
        source_id: Source entity identifier.
        target_id: Target entity identifier.
        environment: Optional preferred environment.
        max_depth: Maximum traversal depth.

    Returns:
        Dependency-path response payload.
    """

    hops = store.shortest_path(
        source_id=source_id,
        target_id=target_id,
        environment=environment,
        max_depth=max_depth,
    )
    if hops is None:
        return {
            "source": store.snapshot(source_id),
            "target": store.snapshot(target_id),
            "environment": environment,
            "path": None,
            "confidence": 0.0,
            "reason": f"No path found from {source_id} to {target_id}",
            "evidence": [],
        }
    summary = path_summary(hops)
    return {
        "source": store.snapshot(source_id),
        "target": store.snapshot(target_id),
        "environment": environment,
        "path": summary,
        "confidence": summary["confidence"],
        "reason": summary["reason"],
        "evidence": summary["evidence"],
        **(
            {"lineage_evidence": summary.get("lineage_evidence")}
            if summary.get("lineage_evidence") is not None
            else {}
        ),
    }


def change_surface_store(
    store: _GraphStore,
    *,
    target_id: str,
    environment: str | None,
    max_depth: int,
) -> dict[str, Any]:
    """Compute the change surface for a starting entity.

    Args:
        store: In-memory impact graph store.
        target_id: Starting entity identifier.
        environment: Optional preferred environment.
        max_depth: Maximum traversal depth.

    Returns:
        Change-surface response payload.
    """

    impacted_ids: dict[str, dict[str, Any]] = {}
    target_snapshot = store.entities.get(target_id) or store.snapshot(target_id)
    target_change_classification = classify_data_change(target_snapshot)
    paths = store.paths_to(
        source_id=target_id,
        target_predicate=lambda ref: ref["id"] != target_id
        and ref["type"]
        in {
            EntityType.repository.value,
            EntityType.workload.value,
            EntityType.workload_instance.value,
            EntityType.cloud_resource.value,
            EntityType.terraform_module.value,
            EntityType.data_asset.value,
            EntityType.data_column.value,
            EntityType.analytics_model.value,
            EntityType.query_execution.value,
            EntityType.dashboard_asset.value,
            EntityType.data_quality_check.value,
        },
        environment=environment,
        max_depth=max_depth,
        continue_through_targets=True,
    )

    for hops in paths:
        summary = path_summary(hops)
        if summary["target"]["type"] != EntityType.repository.value and any(
            hop["to"]["type"] == EntityType.repository.value for hop in hops[:-1]
        ):
            continue
        target = summary["target"]
        existing = impacted_ids.get(target["id"])
        impacted_snapshot = store.entities.get(target["id"]) or target
        change_classification = classify_impacted_data_change(
            impacted_snapshot,
            path=summary,
        )
        item = {
            "entity": target,
            "path": summary,
            "confidence": summary["confidence"],
            "reason": summary["reason"],
            "evidence": summary["evidence"],
            "change_classification": change_classification,
            **(
                {"lineage_evidence": summary.get("lineage_evidence")}
                if summary.get("lineage_evidence") is not None
                else {}
            ),
        }
        if existing is None or item["confidence"] > existing["confidence"]:
            impacted_ids[target["id"]] = item

    impacted = sorted(
        impacted_ids.values(),
        key=lambda item: (-item["confidence"], item["entity"]["id"]),
    )
    top = impacted[0] if impacted else None
    lineage_evidence = merge_lineage_summaries(
        item.get("lineage_evidence") for item in impacted
    )
    classification_summary = summarize_data_change_classifications(
        [target_change_classification]
        + [item.get("change_classification") for item in impacted]
    )
    return {
        "target": store.snapshot(target_id),
        "environment": environment,
        "target_change_classification": target_change_classification,
        "classification_summary": classification_summary,
        "impacted": impacted,
        "confidence": top["confidence"] if top else 0.0,
        "reason": (
            top["reason"] if top else f"No impacted entities found for {target_id}"
        ),
        "evidence": top["evidence"] if top else [],
        **(
            {"lineage_evidence": lineage_evidence}
            if lineage_evidence is not None
            else {}
        ),
    }
