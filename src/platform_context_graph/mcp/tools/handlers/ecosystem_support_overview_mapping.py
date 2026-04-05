"""Generic controller/runtime/fact mapping helpers for deployment overviews."""

from __future__ import annotations

from typing import Any

from ....query.story_deployment_mapping import build_controller_overview
from ....query.story_deployment_mapping import build_deployment_facts
from ....query.story_deployment_mapping import build_runtime_overview


def build_mapping_overviews(
    *,
    hostnames: list[dict[str, Any]],
    runtime_platforms: list[dict[str, Any]],
    delivery_paths: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build generic controller, runtime, and fact views for deployment traces."""

    result: dict[str, Any] = {}
    controller_overview = build_controller_overview(
        delivery_paths=delivery_paths,
        controller_driven_paths=controller_driven_paths,
    )
    if controller_overview:
        result["controller_overview"] = controller_overview

    observed_config_environments = [
        row.get("environment")
        for row in hostnames
        if isinstance(row, dict) and row.get("environment")
    ]
    runtime_overview = build_runtime_overview(
        selected_instance=None,
        instances=[],
        entrypoints=hostnames,
        platforms=runtime_platforms,
        observed_config_environments=observed_config_environments,
    )
    if runtime_overview:
        result["runtime_overview"] = runtime_overview

    deployment_facts = build_deployment_facts(
        delivery_paths=delivery_paths,
        controller_driven_paths=controller_driven_paths,
        platforms=runtime_platforms,
        entrypoints=hostnames,
        observed_config_environments=observed_config_environments,
    )
    if deployment_facts:
        result["deployment_facts"] = deployment_facts
    return result
