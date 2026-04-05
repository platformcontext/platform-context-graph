"""Helpers for generic deployment controller and runtime story overviews."""

from __future__ import annotations

from typing import Any


def _unique_strings(values: list[Any]) -> list[str]:
    """Return non-empty string values while preserving first-seen order."""

    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        rendered = value.strip()
        if not rendered or rendered in seen:
            continue
        seen.add(rendered)
        normalized.append(rendered)
    return normalized


def build_controller_overview(
    *,
    delivery_paths: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build a controller-agnostic overview from delivery evidence."""

    families = _unique_strings(
        [row.get("controller") for row in delivery_paths]
        + [row.get("controller_kind") for row in controller_driven_paths]
    )
    if not families:
        return None

    controller_rows: dict[str, dict[str, Any]] = {}
    for family in families:
        controller_rows[family] = {
            "family": family,
            "path_kinds": [],
            "delivery_modes": [],
            "automation_kinds": [],
            "entry_points": [],
            "target_descriptors": [],
            "supporting_repositories": [],
            "confidence": None,
        }

    for row in delivery_paths:
        family = str(row.get("controller") or "").strip()
        if not family:
            continue
        controller = controller_rows[family]
        controller["path_kinds"] = _unique_strings(
            controller["path_kinds"] + [row.get("path_kind")]
        )
        controller["delivery_modes"] = _unique_strings(
            controller["delivery_modes"] + [row.get("delivery_mode")]
        )

    for row in controller_driven_paths:
        family = str(row.get("controller_kind") or "").strip()
        if not family:
            continue
        controller = controller_rows[family]
        controller["automation_kinds"] = _unique_strings(
            controller["automation_kinds"] + [row.get("automation_kind")]
        )
        controller["entry_points"] = _unique_strings(
            controller["entry_points"] + list(row.get("entry_points") or [])
        )
        controller["target_descriptors"] = _unique_strings(
            controller["target_descriptors"] + list(row.get("target_descriptors") or [])
        )
        controller["supporting_repositories"] = _unique_strings(
            controller["supporting_repositories"]
            + list(row.get("supporting_repositories") or [])
        )
        if controller["confidence"] is None and row.get("confidence"):
            controller["confidence"] = row.get("confidence")

    return {
        "families": families,
        "delivery_modes": _unique_strings(
            [row.get("delivery_mode") for row in delivery_paths]
        ),
        "controllers": [controller_rows[family] for family in families],
    }


def build_runtime_overview(
    *,
    selected_instance: dict[str, Any] | None,
    instances: list[dict[str, Any]],
    entrypoints: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    observed_config_environments: list[str],
) -> dict[str, Any] | None:
    """Build a runtime-agnostic overview from instance and platform evidence."""

    selected_environment = None
    if isinstance(selected_instance, dict):
        selected_environment = str(selected_instance.get("environment") or "").strip()
    if not selected_environment and len(instances) == 1:
        selected_environment = str(instances[0].get("environment") or "").strip()
    if not selected_environment and len(platforms) == 1:
        selected_environment = str(platforms[0].get("environment") or "").strip()
    platform_kinds = _unique_strings([row.get("kind") for row in platforms])
    observed_environments = _unique_strings(
        observed_config_environments
        + [row.get("environment") for row in platforms]
        + [row.get("environment") for row in instances]
        + [row.get("environment") for row in entrypoints]
    )
    entrypoint_labels = _unique_strings(
        [
            row.get("hostname") or row.get("url") or row.get("path")
            for row in entrypoints
        ]
    )
    if not any(
        [selected_environment, observed_environments, platform_kinds, entrypoint_labels]
    ):
        return None

    return {
        "selected_environment": selected_environment or None,
        "observed_environments": observed_environments,
        "platform_kinds": platform_kinds,
        "platforms": [
            {
                "id": row.get("id"),
                "kind": row.get("kind"),
                "provider": row.get("provider"),
                "environment": row.get("environment"),
                "name": row.get("name"),
            }
            for row in platforms
            if isinstance(row, dict)
        ],
        "entrypoints": entrypoint_labels,
    }
