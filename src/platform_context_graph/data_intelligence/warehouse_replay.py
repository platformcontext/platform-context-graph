"""Warehouse replay normalization for vendor-neutral local fixtures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class WarehouseReplayPlugin:
    """Normalize warehouse metadata and query history into core graph entities."""

    name = "warehouse-replay"
    category = "warehouse"
    replay_fixture_groups = ("warehouse_replay_comprehensive",)

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize one replay payload into vendor-neutral graph records."""

        assets_by_name: dict[str, dict[str, Any]] = {}
        data_columns: dict[str, dict[str, Any]] = {}
        query_executions: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []

        for asset in _as_sequence(payload.get("assets")):
            asset_record = _asset_record(asset)
            assets_by_name[asset_record["name"]] = asset_record
            for column in _column_records_for_asset(asset, asset_record["name"]).values():
                data_columns[column["name"]] = column

        for query in _as_sequence(payload.get("query_history")):
            query_record = _query_execution_record(query)
            query_executions.append(query_record)
            for touched_asset in _as_string_sequence(query.get("touched_assets")):
                relationships.append(
                    {
                        "type": "RUNS_QUERY_AGAINST",
                        "source_id": query_record["id"],
                        "source_name": query_record["name"],
                        "target_id": f"data-asset:{touched_asset}",
                        "target_name": touched_asset,
                        "confidence": 1.0,
                    }
                )

        relationships.sort(
            key=lambda item: (item["type"], item["source_name"], item["target_name"])
        )
        query_executions.sort(key=lambda item: item["name"])

        return {
            "data_assets": [assets_by_name[name] for name in sorted(assets_by_name)],
            "data_columns": [data_columns[name] for name in sorted(data_columns)],
            "query_executions": query_executions,
            "relationships": relationships,
            "coverage": {
                "confidence": 1.0,
                "state": "complete",
                "unresolved_references": [],
            },
        }


def _asset_record(asset: Mapping[str, Any]) -> dict[str, Any]:
    """Return one normalized warehouse asset record."""

    asset_name = ".".join(
        part
        for part in (
            str(asset.get("database") or "").strip(),
            str(asset.get("schema") or "").strip(),
            str(asset.get("name") or "").strip(),
        )
        if part
    )
    return {
        "id": f"data-asset:{asset_name}",
        "name": asset_name,
        "line_number": 1,
        "database": str(asset.get("database") or ""),
        "schema": str(asset.get("schema") or ""),
        "kind": str(asset.get("kind") or "table"),
    }


def _column_records_for_asset(
    asset: Mapping[str, Any], asset_name: str
) -> dict[str, dict[str, Any]]:
    """Return normalized column records for one warehouse asset."""

    records: dict[str, dict[str, Any]] = {}
    for column in _as_sequence(asset.get("columns")):
        column_name = str(column.get("name") or "").strip()
        if not column_name:
            continue
        qualified_name = f"{asset_name}.{column_name}"
        records[qualified_name] = {
            "id": f"data-column:{qualified_name}",
            "asset_name": asset_name,
            "name": qualified_name,
            "line_number": 1,
        }
    return records


def _query_execution_record(query: Mapping[str, Any]) -> dict[str, Any]:
    """Return one normalized warehouse query execution record."""

    query_id = str(query.get("query_id") or "").strip()
    query_name = str(query.get("name") or query_id).strip()
    return {
        "id": f"query-execution:{query_id}",
        "name": query_name,
        "line_number": 1,
        "statement": str(query.get("statement") or ""),
        "status": str(query.get("status") or "unknown"),
        "executed_by": str(query.get("executed_by") or ""),
        "started_at": str(query.get("started_at") or ""),
    }


def _as_sequence(value: Any) -> Sequence[Mapping[str, Any]]:
    """Return a normalized sequence of mapping items."""

    if not isinstance(value, list):
        return ()
    return [item for item in value if isinstance(item, Mapping)]


def _as_string_sequence(value: Any) -> list[str]:
    """Return a normalized list of non-empty strings."""

    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


__all__ = ["WarehouseReplayPlugin"]
