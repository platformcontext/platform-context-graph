"""Helpers for summarizing declared-versus-observed data lineage evidence."""

from __future__ import annotations

from typing import Any, Iterable

_DECLARED_LINEAGE_RELATIONSHIPS = frozenset(
    {"COMPILES_TO", "ASSET_DERIVES_FROM", "COLUMN_DERIVES_FROM"}
)
_OBSERVED_LINEAGE_RELATIONSHIPS = frozenset({"RUNS_QUERY_AGAINST"})


def summarize_lineage_relationship_types(
    relationship_types: Iterable[str | None],
) -> dict[str, Any] | None:
    """Summarize lineage evidence families from relationship type names.

    Args:
        relationship_types: Relationship names collected from edges or hops.

    Returns:
        Compact lineage-evidence summary, or ``None`` when no lineage
        relationships are present.
    """

    normalized = {
        str(relationship_type).strip()
        for relationship_type in relationship_types
        if str(relationship_type or "").strip()
    }
    has_declared = bool(normalized & _DECLARED_LINEAGE_RELATIONSHIPS)
    has_observed = bool(normalized & _OBSERVED_LINEAGE_RELATIONSHIPS)
    if not has_declared and not has_observed:
        return None

    evidence_sources: list[str] = []
    if has_declared:
        evidence_sources.append("declared_lineage")
    if has_observed:
        evidence_sources.append("observed_lineage")

    if has_declared and has_observed:
        status = "combined"
    elif has_declared:
        status = "declared_only"
    else:
        status = "observed_only"
    return {
        "status": status,
        "evidence_sources": evidence_sources,
    }


def summarize_lineage_hops(hops: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Summarize lineage evidence from one graph path."""

    return summarize_lineage_relationship_types(hop.get("type") for hop in hops)


def summarize_lineage_edges(edges: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Summarize lineage evidence from connected graph edges."""

    relationship_types = []
    for edge in edges:
        relationship_type = edge.get("type")
        if relationship_type is None and isinstance(edge.get("path"), dict):
            relationship_type = edge["path"].get("type")
        relationship_types.append(relationship_type)
    return summarize_lineage_relationship_types(relationship_types)


def merge_lineage_summaries(
    summaries: Iterable[dict[str, Any] | None],
) -> dict[str, Any] | None:
    """Merge path-level lineage summaries into one aggregate summary."""

    evidence_sources = {
        source
        for summary in summaries
        if isinstance(summary, dict)
        for source in summary.get("evidence_sources") or []
        if isinstance(source, str) and source
    }
    if not evidence_sources:
        return None
    if evidence_sources == {"declared_lineage", "observed_lineage"}:
        status = "combined"
    elif "declared_lineage" in evidence_sources:
        status = "declared_only"
    else:
        status = "observed_only"
    return {
        "status": status,
        "evidence_sources": sorted(evidence_sources),
    }


__all__ = [
    "merge_lineage_summaries",
    "summarize_lineage_edges",
    "summarize_lineage_hops",
    "summarize_lineage_relationship_types",
]
