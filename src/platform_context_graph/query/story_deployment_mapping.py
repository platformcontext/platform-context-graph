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


def _is_iac_adapter(adapter: str) -> bool:
    """Return whether the adapter represents infrastructure-as-code provisioning."""

    return adapter in {"cloudformation", "terraform"}


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


def build_deployment_facts(
    *,
    delivery_paths: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    entrypoints: list[dict[str, Any]],
    observed_config_environments: list[str],
) -> list[dict[str, Any]]:
    """Build normalized deployment facts from evidence-backed adapter inputs."""

    facts: list[dict[str, Any]] = []
    controller_rows = [
        row
        for row in controller_driven_paths
        if isinstance(row, dict) and str(row.get("controller_kind") or "").strip()
    ]
    delivery_rows = [
        row
        for row in delivery_paths
        if isinstance(row, dict) and str(row.get("controller") or "").strip()
    ]
    if not delivery_rows and not controller_rows:
        return facts

    adapter = ""
    if controller_rows:
        adapter = str(controller_rows[0].get("controller_kind") or "").strip()
    if not adapter and delivery_rows:
        adapter = str(delivery_rows[0].get("controller") or "").strip()
    if not adapter:
        return facts

    delivery_evidence = None
    if delivery_rows:
        delivery_evidence = {
            "source": "delivery_path",
            "controller": delivery_rows[0].get("controller"),
            "delivery_mode": delivery_rows[0].get("delivery_mode"),
        }
    controller_evidence = None
    if controller_rows:
        controller_evidence = {
            "source": "controller_driven_path",
            "controller_kind": controller_rows[0].get("controller_kind"),
            "automation_kind": controller_rows[0].get("automation_kind"),
        }

    managed_evidence = [
        item for item in [delivery_evidence, controller_evidence] if item is not None
    ]
    delivery_mode = ""
    if delivery_rows:
        delivery_mode = str(delivery_rows[0].get("delivery_mode") or "").strip()
    inferred_packaging_kind = ""
    if delivery_mode.startswith("flux_"):
        if "helmrelease" in delivery_mode:
            inferred_packaging_kind = "helm"
        elif "kustomization" in delivery_mode:
            inferred_packaging_kind = "kustomize"
    if _is_iac_adapter(adapter):
        confidence = "high"
        facts.append(
            {
                "fact_type": "PROVISIONED_BY_IAC",
                "adapter": adapter,
                "value": adapter,
                "confidence": confidence,
                "evidence": [delivery_evidence] if delivery_evidence else [],
            }
        )
    else:
        confidence = (
            "high"
            if controller_evidence is not None or inferred_packaging_kind
            else "medium"
        )
        facts.append(
            {
                "fact_type": "MANAGED_BY_CONTROLLER",
                "adapter": adapter,
                "value": adapter,
                "confidence": confidence,
                "evidence": managed_evidence,
            }
        )

    automation_kind = ""
    if adapter == "terraform":
        if "helm" in delivery_mode:
            automation_kind = "helm"
        elif "kubernetes" in delivery_mode:
            automation_kind = "kubernetes"
    elif inferred_packaging_kind:
        automation_kind = inferred_packaging_kind
    elif controller_rows:
        automation_kind = str(controller_rows[0].get("automation_kind") or "").strip()
    if automation_kind:
        facts.append(
            {
                "fact_type": "USES_PACKAGING_LAYER",
                "adapter": adapter,
                "value": automation_kind,
                "confidence": confidence,
                "evidence": (
                    [controller_evidence]
                    if controller_evidence is not None
                    else [delivery_evidence] if delivery_evidence is not None else []
                ),
            }
        )

    deploy_sources = _unique_strings(
        [
            source
            for row in delivery_rows
            for source in list(row.get("deployment_sources") or [])
        ]
    )
    for source in deploy_sources:
        facts.append(
            {
                "fact_type": "DEPLOYS_FROM",
                "adapter": adapter,
                "value": source,
                "confidence": confidence,
                "evidence": [delivery_evidence] if delivery_evidence else [],
            }
        )
    config_sources = _unique_strings(
        [
            source
            for row in delivery_rows
            for source in list(row.get("config_sources") or [])
        ]
    )
    for source in config_sources:
        facts.append(
            {
                "fact_type": "DISCOVERS_CONFIG_IN",
                "adapter": adapter,
                "value": source,
                "confidence": confidence,
                "evidence": [delivery_evidence] if delivery_evidence else [],
            }
        )

    platform_rows = [
        row
        for row in platforms
        if isinstance(row, dict) and str(row.get("kind") or "").strip()
    ]
    for row in platform_rows:
        facts.append(
            {
                "fact_type": "RUNS_ON_PLATFORM",
                "adapter": adapter,
                "value": str(row.get("kind") or "").strip(),
                "confidence": "high",
                "evidence": [
                    {
                        "source": "platform",
                        "kind": row.get("kind"),
                        "environment": row.get("environment"),
                    }
                ],
            }
        )

    environments = _unique_strings(
        [
            environment
            for row in delivery_rows
            for environment in list(row.get("environments") or [])
        ]
        + observed_config_environments
    )
    for environment in environments:
        facts.append(
            {
                "fact_type": "OBSERVED_IN_ENVIRONMENT",
                "adapter": adapter,
                "value": environment,
                "confidence": confidence,
                "evidence": [delivery_evidence] if delivery_evidence else [],
            }
        )

    for row in entrypoints:
        if not isinstance(row, dict):
            continue
        hostname = str(row.get("hostname") or "").strip()
        if not hostname:
            continue
        facts.append(
            {
                "fact_type": "EXPOSES_ENTRYPOINT",
                "adapter": adapter,
                "value": hostname,
                "confidence": "medium",
                "evidence": [
                    {
                        "source": "entrypoint",
                        "hostname": row.get("hostname"),
                        "environment": row.get("environment"),
                    }
                ],
            }
        )

    return facts


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
