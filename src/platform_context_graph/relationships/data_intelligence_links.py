"""Data-intelligence relationship materialization helpers."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .sql_links import (
    _build_entity_lookup,
    _resolve_uid,
    _run_uid_relationship_query,
)

_CONTENT_ENTITY_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("analytics_models", ("AnalyticsModel",)),
    ("data_assets", ("DataAsset",)),
    ("data_columns", ("DataColumn",)),
    ("query_executions", ("QueryExecution",)),
    ("dashboard_assets", ("DashboardAsset",)),
)
_RELATIONSHIP_SOURCE_KINDS = {
    "COMPILES_TO": ("AnalyticsModel",),
    "ASSET_DERIVES_FROM": ("DataAsset",),
    "COLUMN_DERIVES_FROM": ("DataColumn",),
    "RUNS_QUERY_AGAINST": ("QueryExecution",),
    "POWERS": ("DataAsset", "DataColumn"),
}
_RELATIONSHIP_TARGET_KINDS = {
    "COMPILES_TO": ("DataAsset",),
    "ASSET_DERIVES_FROM": ("DataAsset",),
    "COLUMN_DERIVES_FROM": ("DataColumn",),
    "RUNS_QUERY_AGAINST": ("DataAsset",),
    "POWERS": ("DashboardAsset",),
}


def create_all_data_intelligence_links(
    builder_or_session: Any,
    all_file_data: Iterable[dict[str, Any]],
    *,
    info_logger_fn: Any | None = None,
) -> dict[str, int]:
    """Create compiled-analytics lineage edges after indexing completes."""

    file_data_list = [
        file_data for file_data in all_file_data if file_data.get("data_relationships")
    ]
    if not file_data_list:
        return {}

    metrics: dict[str, int] = defaultdict(int)
    if callable(getattr(builder_or_session, "run", None)):
        _materialize_data_relationships(builder_or_session, file_data_list, metrics)
    else:
        driver = getattr(builder_or_session, "driver", None)
        if callable(getattr(driver, "session", None)):
            with driver.session() as session:
                _materialize_data_relationships(session, file_data_list, metrics)
        else:
            _materialize_data_relationships(builder_or_session, file_data_list, metrics)

    if callable(info_logger_fn) and metrics:
        summary = ", ".join(f"{key}={value}" for key, value in sorted(metrics.items()))
        info_logger_fn(f"Data-intelligence relationship materialization: {summary}")
    return dict(metrics)


def _materialize_data_relationships(
    session: Any,
    file_data_list: list[dict[str, Any]],
    metrics: dict[str, int],
) -> None:
    """Materialize data-intelligence lineage edges using one active session."""

    entity_lookup = _build_entity_lookup(session, file_data_list, _CONTENT_ENTITY_BUCKETS)
    rows_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for file_data in file_data_list:
        file_path = str(Path(file_data["path"]).resolve())
        for item in file_data.get("data_relationships", []):
            source_uid = _resolve_uid(
                entity_lookup,
                item.get("source_name"),
                _RELATIONSHIP_SOURCE_KINDS.get(item.get("type", ""), ()),
                file_path=file_path,
            )
            target_uid = _resolve_uid(
                entity_lookup,
                item.get("target_name"),
                _RELATIONSHIP_TARGET_KINDS.get(item.get("type", ""), ()),
                file_path=file_path,
            )
            if source_uid is None or target_uid is None:
                continue
            rows_by_type[str(item["type"])].append(
                {
                    "source_uid": source_uid,
                    "target_uid": target_uid,
                    "line_number": item.get("line_number"),
                }
            )

    for relationship_type, rows in rows_by_type.items():
        _run_uid_relationship_query(session, relationship_type, rows)
        metrics[f"{relationship_type.lower()}_edges"] += len(rows)


__all__ = ["create_all_data_intelligence_links"]
