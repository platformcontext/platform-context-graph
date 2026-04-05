"""Focused rule tests for deployment fact mapping."""

from __future__ import annotations

import pytest

from platform_context_graph.query.story_deployment_mapping import (
    build_deployment_fact_summary,
)
from platform_context_graph.query.story_deployment_mapping import (
    build_deployment_facts,
)


@pytest.mark.parametrize(
    ("delivery_mode", "platform_id", "platform_kind"),
    [
        (
            "cloudformation_eks",
            "platform:eks:aws:cluster/prod-1:prod:us-east-1",
            "eks",
        ),
        (
            "cloudformation_stackset",
            "platform:eks:aws:cluster/prod-2:prod:us-east-1",
            "eks",
        ),
        (
            "cloudformation_kubernetes",
            "platform:kubernetes:aws:cluster/shared:prod:us-east-1",
            "kubernetes",
        ),
        (
            "cloudformation_serverless",
            "platform:lambda:aws:region/us-east-1:prod:none",
            "lambda",
        ),
    ],
)
def test_build_deployment_facts_maps_cloudformation_kubernetes_variants_into_iac_facts(
    delivery_mode: str,
    platform_id: str,
    platform_kind: str,
) -> None:
    """Verify CloudFormation Kubernetes-family inputs emit IAC facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "direct",
                "controller": "cloudformation",
                "delivery_mode": delivery_mode,
                "deployment_sources": ["service-catalog"],
                "config_sources": ["cluster-networking"],
                "platform_kinds": [platform_kind],
                "platforms": [platform_id],
                "environments": ["prod"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": platform_id,
                "kind": platform_kind,
                "provider": "aws",
                "environment": "prod",
                "name": (
                    "prod-1"
                    if delivery_mode == "cloudformation_eks"
                    else "prod-2"
                    if delivery_mode == "cloudformation_stackset"
                    else "shared"
                    if platform_kind == "kubernetes"
                    else "us-east-1"
                ),
            }
        ],
        entrypoints=[
            {
                "hostname": "payments.prod.example.com",
                "environment": "prod",
                "visibility": "public",
            }
        ],
        observed_config_environments=["prod"],
    )

    assert facts == [
        {
            "fact_type": "PROVISIONED_BY_IAC",
            "adapter": "cloudformation",
            "value": "cloudformation",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "cloudformation",
                    "delivery_mode": delivery_mode,
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "cloudformation",
            "value": "service-catalog",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "cloudformation",
                    "delivery_mode": delivery_mode,
                }
            ],
        },
        {
            "fact_type": "DISCOVERS_CONFIG_IN",
            "adapter": "cloudformation",
            "value": "cluster-networking",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "cloudformation",
                    "delivery_mode": delivery_mode,
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "cloudformation",
            "value": platform_kind,
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": platform_kind,
                    "environment": "prod",
                }
            ],
        },
        {
            "fact_type": "OBSERVED_IN_ENVIRONMENT",
            "adapter": "cloudformation",
            "value": "prod",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "cloudformation",
                    "delivery_mode": delivery_mode,
                }
            ],
        },
        {
            "fact_type": "EXPOSES_ENTRYPOINT",
            "adapter": "cloudformation",
            "value": "payments.prod.example.com",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "entrypoint",
                    "hostname": "payments.prod.example.com",
                    "environment": "prod",
                }
            ],
        },
    ]


def test_build_deployment_facts_uses_evidence_only_mode_without_controller() -> None:
    """Verify plain delivery evidence still emits normalized facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "direct",
                "delivery_mode": "plain_kubernetes_manifests",
                "deployment_sources": ["service-manifests"],
                "config_sources": ["env-overlays"],
                "platform_kinds": ["kubernetes"],
                "platforms": ["platform:kubernetes:aws:cluster/shared:stage:none"],
                "environments": ["stage"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:kubernetes:aws:cluster/shared:stage:none",
                "kind": "kubernetes",
                "provider": "aws",
                "environment": "stage",
                "name": "shared",
            }
        ],
        entrypoints=[
            {
                "hostname": "payments.stage.example.com",
                "environment": "stage",
                "visibility": "internal",
            }
        ],
        observed_config_environments=["stage"],
    )

    assert facts == [
        {
            "fact_type": "DELIVERY_PATH_PRESENT",
            "adapter": "evidence_only",
            "value": "plain_kubernetes_manifests",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "delivery_mode": "plain_kubernetes_manifests",
                    "path_kind": "direct",
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "evidence_only",
            "value": "service-manifests",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "delivery_mode": "plain_kubernetes_manifests",
                    "path_kind": "direct",
                }
            ],
        },
        {
            "fact_type": "DISCOVERS_CONFIG_IN",
            "adapter": "evidence_only",
            "value": "env-overlays",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "delivery_mode": "plain_kubernetes_manifests",
                    "path_kind": "direct",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "evidence_only",
            "value": "kubernetes",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "kubernetes",
                    "environment": "stage",
                }
            ],
        },
        {
            "fact_type": "OBSERVED_IN_ENVIRONMENT",
            "adapter": "evidence_only",
            "value": "stage",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "delivery_mode": "plain_kubernetes_manifests",
                    "path_kind": "direct",
                }
            ],
        },
        {
            "fact_type": "EXPOSES_ENTRYPOINT",
            "adapter": "evidence_only",
            "value": "payments.stage.example.com",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "entrypoint",
                    "hostname": "payments.stage.example.com",
                    "environment": "stage",
                }
            ],
        },
    ]


def test_build_deployment_fact_summary_reports_strength_and_limitations() -> None:
    """Verify evidence strength and missing controller limitations are surfaced."""

    summary = build_deployment_fact_summary(
        delivery_paths=[
            {
                "path_kind": "direct",
                "delivery_mode": "plain_kubernetes_manifests",
                "deployment_sources": ["service-manifests"],
                "config_sources": ["env-overlays"],
                "platform_kinds": ["kubernetes"],
                "platforms": ["platform:kubernetes:aws:cluster/shared:stage:none"],
                "environments": ["stage"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:kubernetes:aws:cluster/shared:stage:none",
                "kind": "kubernetes",
                "provider": "aws",
                "environment": "stage",
                "name": "shared",
            }
        ],
        entrypoints=[
            {
                "hostname": "payments.stage.example.com",
                "environment": "stage",
                "visibility": "internal",
            }
        ],
        observed_config_environments=["stage"],
    )

    assert summary == {
        "adapter": "evidence_only",
        "mapping_mode": "evidence_only",
        "overall_confidence": "medium",
        "evidence_sources": ["delivery_path", "platform", "entrypoint"],
        "high_confidence_fact_types": ["RUNS_ON_PLATFORM"],
        "medium_confidence_fact_types": [
            "DELIVERY_PATH_PRESENT",
            "DEPLOYS_FROM",
            "DISCOVERS_CONFIG_IN",
            "OBSERVED_IN_ENVIRONMENT",
            "EXPOSES_ENTRYPOINT",
        ],
        "limitations": ["deployment_controller_unknown"],
    }
