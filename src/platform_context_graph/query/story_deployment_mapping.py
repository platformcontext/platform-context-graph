"""Helpers for generic deployment controller and runtime story overviews."""

from __future__ import annotations

from typing import Any

from .story_deployment_mapping_support import build_controller_overview
from .story_deployment_mapping_support import build_empty_deployment_fact_summary
from .story_deployment_mapping_support import build_runtime_overview
from .story_deployment_mapping_support import controller_evidence
from .story_deployment_mapping_support import controller_rows
from .story_deployment_mapping_support import delivery_evidence
from .story_deployment_mapping_support import delivery_rows
from .story_deployment_mapping_support import build_mapping_limitations
from .story_deployment_mapping_support import fact_threshold_code
from .story_deployment_mapping_support import infer_packaging_kind
from .story_deployment_mapping_support import mapping_confidence
from .story_deployment_mapping_support import normalize_automation_layer
from .story_deployment_mapping_support import normalize_controller_packaging_kind
from .story_deployment_mapping_support import overall_confidence_reason
from .story_deployment_mapping_support import resolve_mapping_mode
from .story_deployment_mapping_support import unique_strings


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
    platform_kinds = unique_strings(
        [str(row.get("kind") or "").strip() for row in platform_rows]
        + [
            str(kind).strip()
            for row in normalized_delivery_rows
            for kind in list(row.get("platform_kinds") or [])
        ]
    )
    inferred_packaging_kind = infer_packaging_kind(
        adapter=adapter,
        delivery_mode=delivery_mode,
        platform_kinds=platform_kinds,
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
        automation_kind = normalize_controller_packaging_kind(
            str(normalized_controller_rows[0].get("automation_kind") or "")
        )
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
    deployment_automation_kind = ""
    if normalized_controller_rows:
        deployment_automation_kind = normalize_automation_layer(
            str(normalized_controller_rows[0].get("automation_kind") or "")
        )
    if deployment_automation_kind:
        facts.append(
            {
                "fact_type": "USES_AUTOMATION_LAYER",
                "adapter": adapter,
                "value": deployment_automation_kind,
                "confidence": confidence,
                "evidence": (
                    [controller_signal] if controller_signal is not None else []
                ),
            }
        )
    runtime_family = ""
    if normalized_controller_rows:
        runtime_family = str(
            normalized_controller_rows[0].get("runtime_family") or ""
        ).strip()
    if runtime_family:
        facts.append(
            {
                "fact_type": "USES_RUNTIME_FAMILY",
                "adapter": adapter,
                "value": runtime_family,
                "confidence": confidence,
                "evidence": [
                    {
                        "source": "controller_driven_path",
                        "controller_kind": normalized_controller_rows[0].get(
                            "controller_kind"
                        ),
                        "runtime_family": runtime_family,
                    }
                ],
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
        return build_empty_deployment_fact_summary()

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
    delivery_mode = ""
    if normalized_delivery_rows:
        delivery_mode = str(
            normalized_delivery_rows[0].get("delivery_mode") or ""
        ).strip()
    platform_kinds = unique_strings(
        [str(row.get("kind") or "").strip() for row in platform_rows]
        + [
            str(kind).strip()
            for row in normalized_delivery_rows
            for kind in list(row.get("platform_kinds") or [])
        ]
    )
    inferred_packaging_kind = infer_packaging_kind(
        adapter=adapter,
        delivery_mode=delivery_mode,
        platform_kinds=platform_kinds,
    )
    controller_signal = controller_evidence(
        normalized_controller_rows[0] if normalized_controller_rows else None
    )
    limitations = build_mapping_limitations(
        mapping_mode=mapping_mode,
        has_deploy_source=any(row.get("fact_type") == "DEPLOYS_FROM" for row in facts),
        has_config_source=any(
            row.get("fact_type") == "DISCOVERS_CONFIG_IN" for row in facts
        ),
        has_platform=bool(platform_rows),
        has_environment=any(
            row.get("fact_type") == "OBSERVED_IN_ENVIRONMENT" for row in facts
        ),
        has_entrypoint=any(
            row.get("fact_type") == "EXPOSES_ENTRYPOINT" for row in facts
        ),
        saw_delivery_rows=bool(normalized_delivery_rows),
    )

    overall_confidence = "low"
    if mapping_mode == "iac":
        overall_confidence = "high"
    elif mapping_mode in {"controller", "evidence_only"}:
        overall_confidence = "medium"

    return {
        "adapter": adapter,
        "mapping_mode": mapping_mode,
        "overall_confidence": overall_confidence,
        "overall_confidence_reason": overall_confidence_reason(
            mapping_mode=mapping_mode,
            controller_evidence=controller_signal,
            inferred_packaging_kind=inferred_packaging_kind,
        ),
        "evidence_sources": evidence_sources,
        "high_confidence_fact_types": high_confidence_fact_types,
        "medium_confidence_fact_types": medium_confidence_fact_types,
        "fact_thresholds": {
            str(row.get("fact_type") or ""): fact_threshold_code(
                str(row.get("fact_type") or "")
            )
            for row in facts
        },
        "limitations": limitations,
    }
