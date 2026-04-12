"""Helpers for vendor-neutral data-intelligence extraction from JSON artifacts."""

from __future__ import annotations

from typing import Any

from ...data_intelligence.dbt import DbtCompiledSqlPlugin


def is_dbt_manifest_document(document: Any, *, filename: str) -> bool:
    """Return whether one JSON document looks like a dbt manifest artifact."""

    if filename.lower() != "manifest.json" or not isinstance(document, dict):
        return False
    metadata = document.get("metadata")
    return (
        isinstance(metadata, dict)
        and isinstance(document.get("nodes"), dict)
        and isinstance(document.get("sources"), dict)
    )


def apply_dbt_manifest_document(result: dict[str, Any], document: dict[str, Any]) -> None:
    """Populate one parse result from a dbt manifest replay artifact."""

    normalized = DbtCompiledSqlPlugin().normalize(document)
    result["analytics_models"] = list(normalized["analytics_models"])
    result["data_assets"] = list(normalized["data_assets"])
    result["data_columns"] = list(normalized["data_columns"])
    result["data_relationships"] = list(normalized["relationships"])
    result["data_intelligence_coverage"] = dict(normalized["coverage"])


__all__ = ["apply_dbt_manifest_document", "is_dbt_manifest_document"]
