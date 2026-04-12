"""BI replay normalization for vendor-neutral dashboard fixtures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class BIReplayPlugin:
    """Normalize BI replay payloads into dashboard assets and downstream edges."""

    name = "bi-replay"
    category = "bi"
    replay_fixture_groups = ("bi_replay_comprehensive",)

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize one BI replay payload into vendor-neutral graph records."""

        dashboards: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        workspace = str(payload.get("metadata", {}).get("workspace") or "default")

        for dashboard in _as_sequence(payload.get("dashboards")):
            dashboard_record = _dashboard_asset_record(dashboard, workspace=workspace)
            dashboards.append(dashboard_record)
            for asset_name in _as_string_sequence(dashboard.get("consumes_assets")):
                relationships.append(
                    {
                        "type": "POWERS",
                        "source_id": f"data-asset:{asset_name}",
                        "source_name": asset_name,
                        "target_id": dashboard_record["id"],
                        "target_name": dashboard_record["name"],
                        "confidence": 1.0,
                    }
                )
            for column_name in _as_string_sequence(dashboard.get("consumes_columns")):
                relationships.append(
                    {
                        "type": "POWERS",
                        "source_id": f"data-column:{column_name}",
                        "source_name": column_name,
                        "target_id": dashboard_record["id"],
                        "target_name": dashboard_record["name"],
                        "confidence": 1.0,
                    }
                )

        dashboards.sort(key=lambda item: item["name"])
        relationships.sort(
            key=lambda item: (item["type"], item["source_name"], item["target_name"])
        )
        return {
            "dashboard_assets": dashboards,
            "relationships": relationships,
            "coverage": {
                "confidence": 1.0,
                "state": "complete",
                "unresolved_references": [],
            },
        }


def _dashboard_asset_record(
    dashboard: Mapping[str, Any],
    *,
    workspace: str,
) -> dict[str, Any]:
    """Return one normalized dashboard asset record."""

    dashboard_id = str(dashboard.get("dashboard_id") or "").strip()
    if not dashboard_id:
        dashboard_id = str(dashboard.get("name") or "dashboard").strip().lower()
    return {
        "id": f"dashboard-asset:{workspace}:{dashboard_id}",
        "name": str(dashboard.get("name") or dashboard_id).strip(),
        "line_number": 1,
        "path": str(dashboard.get("path") or ""),
        "workspace": workspace,
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


__all__ = ["BIReplayPlugin"]
