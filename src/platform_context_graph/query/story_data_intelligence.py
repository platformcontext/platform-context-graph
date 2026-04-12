"""Structured story helpers for compiled analytics coverage."""

from __future__ import annotations

from typing import Any


def summarize_data_intelligence_overview(overview: dict[str, Any]) -> str:
    """Return a short human-readable compiled analytics summary."""

    model_count = int(overview.get("analytics_model_count") or 0)
    asset_count = int(overview.get("data_asset_count") or 0)
    column_count = int(overview.get("data_column_count") or 0)
    query_execution_count = int(overview.get("query_execution_count") or 0)
    dashboard_asset_count = int(overview.get("dashboard_asset_count") or 0)
    reconciliation = dict(overview.get("reconciliation") or {})
    parse_states = dict(overview.get("parse_states") or {})
    partial_count = int(parse_states.get("partial") or 0)
    summary = (
        f"Compiled analytics covers {model_count} models, "
        f"{asset_count} data assets, {column_count} data columns"
    )
    if query_execution_count:
        summary += f", {query_execution_count} warehouse quer{'y' if query_execution_count == 1 else 'ies'}"
    if dashboard_asset_count:
        summary += f", and {dashboard_asset_count} dashboard{'s' if dashboard_asset_count != 1 else ''}"
    reconciliation_summary = _reconciliation_summary_text(reconciliation)
    if reconciliation_summary:
        summary += f"; {reconciliation_summary}"
    if partial_count:
        suffix = f"lineage is partial for {partial_count} model"
        if partial_count != 1:
            suffix += "s"
        return f"{summary}; {suffix}."
    return f"{summary}; lineage is complete for all indexed models."


def build_data_intelligence_story_items(
    overview: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return compact story items for the compiled analytics section."""

    return list(
        overview.get("sample_models")
        or overview.get("sample_dashboards")
        or overview.get("sample_queries")
        or overview.get("sample_assets")
        or []
    )


def _reconciliation_summary_text(reconciliation: dict[str, Any]) -> str:
    """Return a short declared-versus-observed lineage summary."""

    if not reconciliation:
        return ""
    shared_asset_count = int(reconciliation.get("shared_asset_count") or 0)
    declared_only_asset_count = int(
        reconciliation.get("declared_only_asset_count") or 0
    )
    observed_only_asset_count = int(
        reconciliation.get("observed_only_asset_count") or 0
    )
    if (
        shared_asset_count == 0
        and declared_only_asset_count == 0
        and observed_only_asset_count == 0
    ):
        return ""
    if declared_only_asset_count == 0 and observed_only_asset_count == 0:
        return f"declared and observed lineage align on {shared_asset_count} assets"
    return (
        f"declared and observed lineage overlap on {shared_asset_count} assets, "
        f"with {declared_only_asset_count} declared-only and "
        f"{observed_only_asset_count} observed-only asset"
        f"{'' if observed_only_asset_count == 1 and declared_only_asset_count == 1 else 's'}"
    )


__all__ = [
    "build_data_intelligence_story_items",
    "summarize_data_intelligence_overview",
]
