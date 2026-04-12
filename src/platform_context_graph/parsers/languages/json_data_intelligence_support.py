"""Helpers for vendor-neutral data-intelligence extraction from JSON artifacts."""

from __future__ import annotations

from typing import Any

from ...data_intelligence.bi_replay import BIReplayPlugin
from ...data_intelligence.dbt import DbtCompiledSqlPlugin
from ...data_intelligence.quality_replay import QualityReplayPlugin
from ...data_intelligence.semantic_replay import SemanticReplayPlugin
from ...data_intelligence.warehouse_replay import WarehouseReplayPlugin


def is_dbt_manifest_document(document: Any, *, filename: str) -> bool:
    """Return whether one JSON document looks like a dbt manifest artifact."""

    lowered = filename.lower()
    if lowered not in {"manifest.json", "dbt_manifest.json"} or not isinstance(
        document, dict
    ):
        return False
    metadata = document.get("metadata")
    return (
        isinstance(metadata, dict)
        and isinstance(document.get("nodes"), dict)
        and isinstance(document.get("sources"), dict)
    )


def is_warehouse_replay_document(document: Any, *, filename: str) -> bool:
    """Return whether one JSON document looks like a warehouse replay artifact."""

    lowered = filename.lower()
    if lowered != "warehouse_replay.json" or not isinstance(document, dict):
        return False
    metadata = document.get("metadata")
    return (
        isinstance(metadata, dict)
        and isinstance(document.get("assets"), list)
        and isinstance(document.get("query_history"), list)
    )


def is_bi_replay_document(document: Any, *, filename: str) -> bool:
    """Return whether one JSON document looks like a BI replay artifact."""

    lowered = filename.lower()
    if lowered != "bi_replay.json" or not isinstance(document, dict):
        return False
    metadata = document.get("metadata")
    return isinstance(metadata, dict) and isinstance(document.get("dashboards"), list)


def is_semantic_replay_document(document: Any, *, filename: str) -> bool:
    """Return whether one JSON document looks like a semantic replay artifact."""

    lowered = filename.lower()
    if lowered != "semantic_replay.json" or not isinstance(document, dict):
        return False
    metadata = document.get("metadata")
    return isinstance(metadata, dict) and isinstance(document.get("models"), list)


def is_quality_replay_document(document: Any, *, filename: str) -> bool:
    """Return whether one JSON document looks like a quality replay artifact."""

    lowered = filename.lower()
    if lowered != "quality_replay.json" or not isinstance(document, dict):
        return False
    metadata = document.get("metadata")
    return isinstance(metadata, dict) and isinstance(document.get("checks"), list)


def apply_dbt_manifest_document(result: dict[str, Any], document: dict[str, Any]) -> None:
    """Populate one parse result from a dbt manifest replay artifact."""

    normalized = DbtCompiledSqlPlugin().normalize(document)
    result["analytics_models"] = list(normalized["analytics_models"])
    result["data_assets"] = list(normalized["data_assets"])
    result["data_columns"] = list(normalized["data_columns"])
    result["data_relationships"] = list(normalized["relationships"])
    result["data_intelligence_coverage"] = dict(normalized["coverage"])


def apply_warehouse_replay_document(
    result: dict[str, Any], document: dict[str, Any]
) -> None:
    """Populate one parse result from a warehouse replay fixture."""

    normalized = WarehouseReplayPlugin().normalize(document)
    result["data_assets"] = list(normalized["data_assets"])
    result["data_columns"] = list(normalized["data_columns"])
    result["query_executions"] = list(normalized["query_executions"])
    result["data_relationships"] = list(normalized["relationships"])
    result["data_intelligence_coverage"] = dict(normalized["coverage"])


def apply_bi_replay_document(result: dict[str, Any], document: dict[str, Any]) -> None:
    """Populate one parse result from a BI replay fixture."""

    normalized = BIReplayPlugin().normalize(document)
    result["dashboard_assets"] = list(normalized["dashboard_assets"])
    result["data_relationships"] = list(normalized["relationships"])
    result["data_intelligence_coverage"] = dict(normalized["coverage"])


def apply_semantic_replay_document(
    result: dict[str, Any], document: dict[str, Any]
) -> None:
    """Populate one parse result from a semantic replay fixture."""

    normalized = SemanticReplayPlugin().normalize(document)
    result["data_assets"] = list(normalized["data_assets"])
    result["data_columns"] = list(normalized["data_columns"])
    result["data_relationships"] = list(normalized["relationships"])
    result["data_intelligence_coverage"] = dict(normalized["coverage"])


def apply_quality_replay_document(
    result: dict[str, Any], document: dict[str, Any]
) -> None:
    """Populate one parse result from a quality replay fixture."""

    normalized = QualityReplayPlugin().normalize(document)
    result["data_quality_checks"] = list(normalized["data_quality_checks"])
    result["data_relationships"] = list(normalized["relationships"])
    result["data_intelligence_coverage"] = dict(normalized["coverage"])


__all__ = [
    "apply_bi_replay_document",
    "apply_dbt_manifest_document",
    "apply_quality_replay_document",
    "apply_semantic_replay_document",
    "apply_warehouse_replay_document",
    "is_bi_replay_document",
    "is_dbt_manifest_document",
    "is_quality_replay_document",
    "is_semantic_replay_document",
    "is_warehouse_replay_document",
]
