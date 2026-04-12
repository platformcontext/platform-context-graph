"""Quality replay normalization for vendor-neutral data-quality fixtures."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class QualityReplayPlugin:
    """Normalize quality replay payloads into checks and assertion edges."""

    name = "quality-replay"
    category = "quality"
    replay_fixture_groups = ("quality_replay_comprehensive",)

    def normalize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize one quality replay payload into core graph records."""

        quality_checks: list[dict[str, Any]] = []
        relationships: list[dict[str, Any]] = []
        workspace = str(payload.get("metadata", {}).get("workspace") or "default")

        for check in _as_sequence(payload.get("checks")):
            check_record = _quality_check_record(check, workspace=workspace)
            quality_checks.append(check_record)
            for asset_name in _as_string_sequence(check.get("targets_assets")):
                relationships.append(
                    {
                        "type": "ASSERTS_QUALITY_ON",
                        "source_id": check_record["id"],
                        "source_name": check_record["name"],
                        "target_id": f"data-asset:{asset_name}",
                        "target_name": asset_name,
                        "confidence": 1.0,
                    }
                )
            for column_name in _as_string_sequence(check.get("targets_columns")):
                relationships.append(
                    {
                        "type": "ASSERTS_QUALITY_ON",
                        "source_id": check_record["id"],
                        "source_name": check_record["name"],
                        "target_id": f"data-column:{column_name}",
                        "target_name": column_name,
                        "confidence": 1.0,
                    }
                )

        quality_checks.sort(key=lambda item: item["name"])
        relationships.sort(
            key=lambda item: (item["type"], item["source_name"], item["target_name"])
        )
        return {
            "data_quality_checks": quality_checks,
            "relationships": relationships,
            "coverage": {
                "confidence": 1.0,
                "state": "complete",
                "unresolved_references": [],
            },
        }


def _quality_check_record(
    check: Mapping[str, Any],
    *,
    workspace: str,
) -> dict[str, Any]:
    """Return one normalized data-quality check record."""

    check_id = str(check.get("check_id") or "").strip()
    if not check_id:
        check_id = str(check.get("name") or "quality-check").strip().lower()
    return {
        "id": f"data-quality-check:{workspace}:{check_id}",
        "name": str(check.get("name") or check_id).strip(),
        "line_number": 1,
        "path": str(check.get("path") or ""),
        "check_type": str(check.get("check_type") or "assertion"),
        "status": str(check.get("status") or "unknown"),
        "severity": str(check.get("severity") or "medium"),
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


__all__ = ["QualityReplayPlugin"]
