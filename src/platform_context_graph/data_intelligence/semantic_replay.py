"""Semantic replay normalization for vendor-neutral semantic-layer fixtures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class SemanticReplayPlugin:
    """Normalize semantic-layer fixtures into generic asset and column lineage."""

    name = "semantic-replay"
    category = "semantic"
    replay_fixture_groups = ("semantic_replay_comprehensive",)

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize one semantic replay payload into core graph records."""

        data_assets: dict[str, dict[str, Any]] = {}
        data_columns: dict[str, dict[str, Any]] = {}
        relationships: list[dict[str, Any]] = []

        for model in _as_sequence(payload.get("models")):
            asset_record = _asset_record(model)
            if not asset_record["name"]:
                continue
            data_assets[asset_record["name"]] = asset_record
            for upstream_asset in _as_string_sequence(model.get("upstream_assets")):
                relationships.append(
                    {
                        "type": "ASSET_DERIVES_FROM",
                        "source_id": asset_record["id"],
                        "source_name": asset_record["name"],
                        "target_id": f"data-asset:{upstream_asset}",
                        "target_name": upstream_asset,
                        "confidence": 1.0,
                    }
                )
            for field in _as_sequence(model.get("fields")):
                column_record = _column_record(
                    asset_name=asset_record["name"],
                    field=field,
                )
                if column_record is None:
                    continue
                data_columns[column_record["name"]] = column_record
                source_column = str(field.get("source_column") or "").strip()
                if not source_column:
                    continue
                relationships.append(
                    {
                        "type": "COLUMN_DERIVES_FROM",
                        "source_id": column_record["id"],
                        "source_name": column_record["name"],
                        "target_id": f"data-column:{source_column}",
                        "target_name": source_column,
                        "confidence": 1.0,
                    }
                )

        relationships.sort(
            key=lambda item: (item["type"], item["source_name"], item["target_name"])
        )
        return {
            "data_assets": [data_assets[name] for name in sorted(data_assets)],
            "data_columns": [data_columns[name] for name in sorted(data_columns)],
            "relationships": relationships,
            "coverage": {
                "confidence": 1.0,
                "state": "complete",
                "unresolved_references": [],
            },
        }


def _asset_record(model: Mapping[str, Any]) -> dict[str, Any]:
    """Return one normalized semantic asset record."""

    asset_name = str(model.get("name") or "").strip()
    model_id = str(model.get("model_id") or asset_name).strip()
    return {
        "id": f"data-asset:{asset_name}",
        "name": asset_name,
        "line_number": 1,
        "path": str(model.get("path") or ""),
        "kind": str(model.get("kind") or "semantic_model"),
        "source_id": model_id,
    }


def _column_record(
    *, asset_name: str, field: Mapping[str, Any]
) -> dict[str, Any] | None:
    """Return one normalized semantic field record when the name is present."""

    field_name = str(field.get("name") or "").strip()
    if not field_name:
        return None
    qualified_name = f"{asset_name}.{field_name}"
    return {
        "id": f"data-column:{qualified_name}",
        "asset_name": asset_name,
        "name": qualified_name,
        "line_number": 1,
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


__all__ = ["SemanticReplayPlugin"]
