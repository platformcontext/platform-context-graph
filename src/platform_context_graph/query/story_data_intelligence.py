"""Structured story helpers for compiled analytics coverage."""

from __future__ import annotations

from typing import Any


def summarize_data_intelligence_overview(overview: dict[str, Any]) -> str:
    """Return a short human-readable compiled analytics summary."""

    model_count = int(overview.get("analytics_model_count") or 0)
    asset_count = int(overview.get("data_asset_count") or 0)
    column_count = int(overview.get("data_column_count") or 0)
    parse_states = dict(overview.get("parse_states") or {})
    partial_count = int(parse_states.get("partial") or 0)
    summary = (
        f"Compiled analytics covers {model_count} models, {asset_count} data assets, "
        f"and {column_count} data columns"
    )
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

    return list(overview.get("sample_models") or overview.get("sample_assets") or [])


__all__ = [
    "build_data_intelligence_story_items",
    "summarize_data_intelligence_overview",
]
