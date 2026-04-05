"""Helpers for generic deployment controller and runtime story overviews."""

from __future__ import annotations

from typing import Any

from .story_deployment_mapping_support import controller_evidence
from .story_deployment_mapping_support import controller_rows
from .story_deployment_mapping_support import delivery_evidence
from .story_deployment_mapping_support import delivery_rows
from .story_deployment_mapping_support import infer_packaging_kind
from .story_deployment_mapping_support import mapping_confidence
from .story_deployment_mapping_support import resolve_mapping_mode
from .story_deployment_mapping_support import unique_strings


def build_controller_overview(
    *,
    delivery_paths: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build a controller-agnostic overview from delivery evidence."""

    families = unique_strings(
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
        controller["path_kinds"] = unique_strings(
            controller["path_kinds"] + [row.get("path_kind")]
        )
        controller["delivery_modes"] = unique_strings(
            controller["delivery_modes"] + [row.get("delivery_mode")]
        )

    for row in controller_driven_paths:
        family = str(row.get("controller_kind") or "").strip()
        if not family:
            continue
        controller = controller_rows[family]
        controller["automation_kinds"] = unique_strings(
            controller["automation_kinds"] + [row.get("automation_kind")]
        )
        controller["entry_points"] = unique_strings(
            controller["entry_points"] + list(row.get("entry_points") or [])
        )
        controller["target_descriptors"] = unique_strings(
            controller["target_descriptors"] + list(row.get("target_descriptors") or [])
        )
        controller["supporting_repositories"] = unique_strings(
            controller["supporting_repositories"]
            + list(row.get("supporting_repositories") or [])
        )
        if controller["confidence"] is None and row.get("confidence"):
            controller["confidence"] = row.get("confidence")

    return {
        "families": families,
        "delivery_modes": unique_strings(
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
    normalized_delivery_rows = delivery_rows(delivery_paths)
    normalized_controller_rows = controller_rows(controller_driven_paths)
    platform_rows = [
        row
        for row in platforms
        if isinstance(row, dict) and str(row.get("kind") or "").strip()
    ]
    if not any(
        [
            normalized_delivery_rows,
            normalized_controller_rows,
            platform_rows,
            entrypoints,
        ]
    ):
        return facts

    adapter, mapping_mode = resolve_mapping_mode(
        delivery_rows=normalized_delivery_rows,
        controller_rows=normalized_controller_rows,
        platforms=platform_rows,
        entrypoints=entrypoints,
        observed_config_environments=observed_config_environments,
    )
    if not adapter:
        return facts

    delivery_signal = delivery_evidence(
        normalized_delivery_rows[0] if normalized_delivery_rows else None
    )
    controller_signal = controller_evidence(
        normalized_controller_rows[0] if normalized_controller_rows else None
    )

    managed_evidence = [
        item for item in [delivery_signal, controller_signal] if item is not None
    ]
    delivery_mode = ""
    if normalized_delivery_rows:
        delivery_mode = str(
            normalized_delivery_rows[0].get("delivery_mode") or ""
        ).strip()
    inferred_packaging_kind = infer_packaging_kind(
        adapter=adapter,
        delivery_mode=delivery_mode,
    )
    confidence = mapping_confidence(
        mapping_mode=mapping_mode,
        controller_evidence=controller_signal,
        inferred_packaging_kind=inferred_packaging_kind,
    )
    if mapping_mode == "iac":
        facts.append(
            {
                "fact_type": "PROVISIONED_BY_IAC",
                "adapter": adapter,
                "value": adapter,
                "confidence": confidence,
                "evidence": [delivery_signal] if delivery_signal else [],
            }
        )
    elif mapping_mode == "controller":
        facts.append(
            {
                "fact_type": "MANAGED_BY_CONTROLLER",
                "adapter": adapter,
                "value": adapter,
                "confidence": confidence,
                "evidence": managed_evidence,
            }
        )
    elif delivery_signal is not None:
        facts.append(
            {
                "fact_type": "DELIVERY_PATH_PRESENT",
                "adapter": adapter,
                "value": delivery_mode
                or str(normalized_delivery_rows[0].get("path_kind") or ""),
                "confidence": confidence,
                "evidence": [delivery_signal],
            }
        )

    automation_kind = ""
    if inferred_packaging_kind:
        automation_kind = inferred_packaging_kind
    elif normalized_controller_rows:
        automation_kind = str(
            normalized_controller_rows[0].get("automation_kind") or ""
        ).strip()
    if automation_kind:
        facts.append(
            {
                "fact_type": "USES_PACKAGING_LAYER",
                "adapter": adapter,
                "value": automation_kind,
                "confidence": confidence,
                "evidence": (
                    [controller_signal]
                    if controller_signal is not None
                    else [delivery_signal] if delivery_signal is not None else []
                ),
            }
        )

    deploy_sources = unique_strings(
        [
            source
            for row in normalized_delivery_rows
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
                "evidence": [delivery_signal] if delivery_signal else [],
            }
        )
    config_sources = unique_strings(
        [
            source
            for row in normalized_delivery_rows
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
                "evidence": [delivery_signal] if delivery_signal else [],
            }
        )

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

    environments = unique_strings(
        [
            environment
            for row in normalized_delivery_rows
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
                "evidence": [delivery_signal] if delivery_signal else [],
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


def build_deployment_fact_summary(
    *,
    delivery_paths: list[dict[str, Any]],
    controller_driven_paths: list[dict[str, Any]],
    platforms: list[dict[str, Any]],
    entrypoints: list[dict[str, Any]],
    observed_config_environments: list[str],
) -> dict[str, Any] | None:
    """Summarize deployment fact strength and truthful limitations."""

    normalized_delivery_rows = delivery_rows(delivery_paths)
    normalized_controller_rows = controller_rows(controller_driven_paths)
    platform_rows = [
        row
        for row in platforms
        if isinstance(row, dict) and str(row.get("kind") or "").strip()
    ]
    adapter, mapping_mode = resolve_mapping_mode(
        delivery_rows=normalized_delivery_rows,
        controller_rows=normalized_controller_rows,
        platforms=platform_rows,
        entrypoints=entrypoints,
        observed_config_environments=observed_config_environments,
    )
    if not adapter:
        return None

    facts = build_deployment_facts(
        delivery_paths=delivery_paths,
        controller_driven_paths=controller_driven_paths,
        platforms=platforms,
        entrypoints=entrypoints,
        observed_config_environments=observed_config_environments,
    )
    high_confidence_fact_types = [
        str(row.get("fact_type") or "")
        for row in facts
        if str(row.get("confidence") or "").strip() == "high"
    ]
    medium_confidence_fact_types = [
        str(row.get("fact_type") or "")
        for row in facts
        if str(row.get("confidence") or "").strip() == "medium"
    ]
    evidence_sources = unique_strings(
        [
            evidence.get("source")
            for row in facts
            for evidence in list(row.get("evidence") or [])
            if isinstance(evidence, dict)
        ]
    )
    limitations: list[str] = []
    if mapping_mode == "evidence_only":
        limitations.append("deployment_controller_unknown")
    if not any(row.get("fact_type") == "DEPLOYS_FROM" for row in facts):
        limitations.append("deployment_source_unknown")
    if normalized_delivery_rows and not any(
        row.get("fact_type") == "DISCOVERS_CONFIG_IN" for row in facts
    ):
        limitations.append("config_source_unknown")
    if not platform_rows:
        limitations.append("runtime_platform_unknown")
    if not any(row.get("fact_type") == "OBSERVED_IN_ENVIRONMENT" for row in facts):
        limitations.append("environment_unknown")
    if not any(row.get("fact_type") == "EXPOSES_ENTRYPOINT" for row in facts):
        limitations.append("entrypoint_unknown")

    overall_confidence = "low"
    if mapping_mode == "iac":
        overall_confidence = "high"
    elif mapping_mode in {"controller", "evidence_only"}:
        overall_confidence = "medium"

    return {
        "adapter": adapter,
        "mapping_mode": mapping_mode,
        "overall_confidence": overall_confidence,
        "evidence_sources": evidence_sources,
        "high_confidence_fact_types": high_confidence_fact_types,
        "medium_confidence_fact_types": medium_confidence_fact_types,
        "limitations": limitations,
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
    platform_kinds = unique_strings([row.get("kind") for row in platforms])
    observed_environments = unique_strings(
        observed_config_environments
        + [row.get("environment") for row in platforms]
        + [row.get("environment") for row in instances]
        + [row.get("environment") for row in entrypoints]
    )
    entrypoint_labels = unique_strings(
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
