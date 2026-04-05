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
                    else (
                        "prod-2"
                        if delivery_mode == "cloudformation_stackset"
                        else "shared" if platform_kind == "kubernetes" else "us-east-1"
                    )
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
    """Verify plain manifest evidence still emits normalized facts."""

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
            "fact_type": "USES_PACKAGING_LAYER",
            "adapter": "evidence_only",
            "value": "kubernetes",
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
        "overall_confidence_reason": "delivery_runtime_evidence_without_named_adapter",
        "evidence_sources": ["delivery_path", "platform", "entrypoint"],
        "high_confidence_fact_types": ["RUNS_ON_PLATFORM"],
        "medium_confidence_fact_types": [
            "DELIVERY_PATH_PRESENT",
            "USES_PACKAGING_LAYER",
            "DEPLOYS_FROM",
            "DISCOVERS_CONFIG_IN",
            "OBSERVED_IN_ENVIRONMENT",
            "EXPOSES_ENTRYPOINT",
        ],
        "fact_thresholds": {
            "DELIVERY_PATH_PRESENT": "delivery_path_present",
            "USES_PACKAGING_LAYER": "explicit_packaging_signal",
            "DEPLOYS_FROM": "named_deployment_source",
            "DISCOVERS_CONFIG_IN": "named_config_source",
            "RUNS_ON_PLATFORM": "explicit_platform_match",
            "OBSERVED_IN_ENVIRONMENT": "explicit_environment_evidence",
            "EXPOSES_ENTRYPOINT": "named_entrypoint",
        },
        "limitations": ["deployment_controller_unknown"],
    }


def test_build_deployment_facts_maps_plain_helm_release_into_evidence_only_facts() -> (
    None
):
    """Verify raw Helm delivery evidence emits packaging facts without a controller."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "direct",
                "delivery_mode": "plain_helm_release",
                "deployment_sources": ["service-chart"],
                "config_sources": ["values-prod"],
                "platform_kinds": ["kubernetes"],
                "platforms": ["platform:kubernetes:aws:cluster/shared:prod:none"],
                "environments": ["prod"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:kubernetes:aws:cluster/shared:prod:none",
                "kind": "kubernetes",
                "provider": "aws",
                "environment": "prod",
                "name": "shared",
            }
        ],
        entrypoints=[],
        observed_config_environments=["prod"],
    )

    assert facts[:4] == [
        {
            "fact_type": "DELIVERY_PATH_PRESENT",
            "adapter": "evidence_only",
            "value": "plain_helm_release",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "delivery_mode": "plain_helm_release",
                    "path_kind": "direct",
                }
            ],
        },
        {
            "fact_type": "USES_PACKAGING_LAYER",
            "adapter": "evidence_only",
            "value": "helm",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "delivery_mode": "plain_helm_release",
                    "path_kind": "direct",
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "evidence_only",
            "value": "service-chart",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "delivery_mode": "plain_helm_release",
                    "path_kind": "direct",
                }
            ],
        },
        {
            "fact_type": "DISCOVERS_CONFIG_IN",
            "adapter": "evidence_only",
            "value": "values-prod",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "delivery_path",
                    "delivery_mode": "plain_helm_release",
                    "path_kind": "direct",
                }
            ],
        },
    ]


def test_build_deployment_facts_maps_jenkins_ansible_into_controller_and_automation_facts() -> (
    None
):
    """Verify Jenkins plus Ansible emits controller and automation facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "direct",
                "controller": "jenkins",
                "delivery_mode": "jenkins_pipeline",
                "platform_kinds": ["vm"],
                "platforms": ["platform:vmware:none:mws:prod:none"],
                "environments": ["prod"],
            }
        ],
        controller_driven_paths=[
            {
                "controller_kind": "jenkins",
                "automation_kind": "ansible",
                "entry_points": ["deploy.yml"],
                "target_descriptors": ["mws", "prod"],
                "runtime_family": "wordpress_website_fleet",
                "supporting_repositories": ["terraform-stack-mws"],
                "confidence": "high",
            }
        ],
        platforms=[
            {
                "id": "platform:vmware:none:mws:prod:none",
                "kind": "vm",
                "provider": "vmware",
                "environment": "prod",
                "name": "mws",
            }
        ],
        entrypoints=[],
        observed_config_environments=["prod"],
    )

    assert facts[:3] == [
        {
            "fact_type": "MANAGED_BY_CONTROLLER",
            "adapter": "jenkins",
            "value": "jenkins",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "jenkins",
                    "delivery_mode": "jenkins_pipeline",
                },
                {
                    "source": "controller_driven_path",
                    "controller_kind": "jenkins",
                    "automation_kind": "ansible",
                },
            ],
        },
        {
            "fact_type": "USES_AUTOMATION_LAYER",
            "adapter": "jenkins",
            "value": "ansible",
            "confidence": "high",
            "evidence": [
                {
                    "source": "controller_driven_path",
                    "controller_kind": "jenkins",
                    "automation_kind": "ansible",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "jenkins",
            "value": "vm",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "vm",
                    "environment": "prod",
                }
            ],
        },
    ]
