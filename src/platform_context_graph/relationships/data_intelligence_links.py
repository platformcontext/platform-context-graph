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
    ("data_quality_checks", ("DataQualityCheck",)),
    ("data_owners", ("DataOwner",)),
    ("data_contracts", ("DataContract",)),
)
_RELATIONSHIP_SOURCE_KINDS = {
    "COMPILES_TO": ("AnalyticsModel",),
    "ASSET_DERIVES_FROM": ("DataAsset",),
    "COLUMN_DERIVES_FROM": ("DataColumn",),
    "RUNS_QUERY_AGAINST": ("QueryExecution",),
    "POWERS": ("DataAsset", "DataColumn"),
    "ASSERTS_QUALITY_ON": ("DataQualityCheck",),
    "OWNS": ("DataOwner",),
    "DECLARES_CONTRACT_FOR": ("DataContract",),
    "MASKS": ("DataContract",),
}
_RELATIONSHIP_TARGET_KINDS = {
    "COMPILES_TO": ("DataAsset",),
    "ASSET_DERIVES_FROM": ("DataAsset",),
    "COLUMN_DERIVES_FROM": ("DataColumn",),
    "RUNS_QUERY_AGAINST": ("DataAsset",),
    "POWERS": ("DashboardAsset",),
    "ASSERTS_QUALITY_ON": ("DataAsset", "DataColumn"),
    "OWNS": ("DataAsset", "DataColumn"),
    "DECLARES_CONTRACT_FOR": ("DataAsset", "DataColumn"),
    "MASKS": ("DataColumn",),
}
_RELATIONSHIP_PROPERTY_KEYS = {
    "COLUMN_DERIVES_FROM": (
        "transform_kind",
        "transform_expression",
    ),
    "MASKS": (
        "protection_kind",
        "sensitivity",
    ),
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
        or file_data.get("data_governance_annotations")
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
            relationship_type = str(item["type"])
            row = {
                "source_uid": source_uid,
                "target_uid": target_uid,
                "line_number": item.get("line_number"),
            }
            for property_key in _RELATIONSHIP_PROPERTY_KEYS.get(relationship_type, ()):
                row[property_key] = item.get(property_key)
            rows_by_type[relationship_type].append(row)

    for relationship_type, rows in rows_by_type.items():
        _run_uid_relationship_query(
            session,
            relationship_type,
            rows,
            property_keys=_RELATIONSHIP_PROPERTY_KEYS.get(relationship_type, ()),
        )
        metrics[f"{relationship_type.lower()}_edges"] += len(rows)
    governance_rows = _collect_governance_annotations(file_data_list, entity_lookup)
    _apply_governance_annotations(session, governance_rows)
    if governance_rows:
        metrics["governance_annotations_applied"] += len(governance_rows)


def _collect_governance_annotations(
    file_data_list: list[dict[str, Any]],
    entity_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Resolve governance overlay rows against persisted data-entity UIDs."""

    rows: list[dict[str, Any]] = []
    for file_data in file_data_list:
        file_path = str(Path(file_data["path"]).resolve())
        for item in file_data.get("data_governance_annotations", []):
            target_kind = str(item.get("target_kind") or "").strip()
            target_uid = _resolve_uid(
                entity_lookup,
                item.get("target_name"),
                (target_kind,),
                file_path=file_path,
            )
            if target_uid is None:
                continue
            rows.append(
                {
                    "target_uid": target_uid,
                    "owner_names": list(item.get("owner_names") or []),
                    "owner_teams": list(item.get("owner_teams") or []),
                    "contract_names": list(item.get("contract_names") or []),
                    "contract_levels": list(item.get("contract_levels") or []),
                    "change_policies": list(item.get("change_policies") or []),
                    "sensitivity": item.get("sensitivity"),
                    "is_protected": bool(item.get("is_protected")),
                    "protection_kind": item.get("protection_kind"),
                }
            )
    return rows


def _apply_governance_annotations(session: Any, rows: list[dict[str, Any]]) -> None:
    """Apply governance metadata onto the matched data-asset and data-column nodes."""

    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS row
        MATCH (target {uid: row.target_uid})
        SET target.owner_names = row.owner_names,
            target.owner_teams = row.owner_teams,
            target.contract_names = row.contract_names,
            target.contract_levels = row.contract_levels,
            target.change_policies = row.change_policies,
            target.sensitivity = row.sensitivity,
            target.is_protected = row.is_protected,
            target.protection_kind = row.protection_kind
        """,
        rows=rows,
    )


__all__ = ["create_all_data_intelligence_links"]
