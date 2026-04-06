from __future__ import annotations

from platform_context_graph.query.story_deployment_mapping import (
    build_deployment_facts,
)


def test_build_deployment_facts_maps_argocd_evidence_into_normalized_facts() -> None:
    """Verify ArgoCD evidence becomes explicit normalized deployment facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "gitops",
                "controller": "argocd",
                "delivery_mode": "eks_gitops",
                "deployment_sources": ["helm-charts"],
                "platform_kinds": ["eks"],
                "platforms": ["platform:eks:aws:cluster/bg-qa:bg-qa:none"],
                "environments": ["bg-qa"],
            }
        ],
        controller_driven_paths=[
            {
                "controller_kind": "argocd",
                "automation_kind": "helm",
                "entry_points": ["argocd/api-node-boats/overlays/bg-qa/config.yaml"],
                "target_descriptors": ["bg-qa", "api-node"],
                "runtime_family": "kubernetes",
                "supporting_repositories": ["helm-charts"],
                "confidence": "high",
            }
        ],
        platforms=[
            {
                "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                "kind": "eks",
                "provider": "aws",
                "environment": "bg-qa",
                "name": "bg-qa",
            }
        ],
        entrypoints=[
            {
                "hostname": "api-node-boats.qa.bgrp.io",
                "environment": "bg-qa",
                "visibility": "public",
            }
        ],
        observed_config_environments=["bg-qa"],
    )

    assert facts == [
        {
            "fact_type": "MANAGED_BY_CONTROLLER",
            "adapter": "argocd",
            "value": "argocd",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "argocd",
                    "delivery_mode": "eks_gitops",
                },
                {
                    "source": "controller_driven_path",
                    "controller_kind": "argocd",
                    "automation_kind": "helm",
                },
            ],
        },
        {
            "fact_type": "USES_PACKAGING_LAYER",
            "adapter": "argocd",
            "value": "helm",
            "confidence": "high",
            "evidence": [
                {
                    "source": "controller_driven_path",
                    "controller_kind": "argocd",
                    "automation_kind": "helm",
                }
            ],
        },
        {
            "fact_type": "USES_RUNTIME_FAMILY",
            "adapter": "argocd",
            "value": "kubernetes",
            "confidence": "high",
            "evidence": [
                {
                    "source": "controller_driven_path",
                    "controller_kind": "argocd",
                    "runtime_family": "kubernetes",
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "argocd",
            "value": "helm-charts",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "argocd",
                    "delivery_mode": "eks_gitops",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "argocd",
            "value": "eks",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "eks",
                    "environment": "bg-qa",
                }
            ],
        },
        {
            "fact_type": "OBSERVED_IN_ENVIRONMENT",
            "adapter": "argocd",
            "value": "bg-qa",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "argocd",
                    "delivery_mode": "eks_gitops",
                }
            ],
        },
        {
            "fact_type": "EXPOSES_ENTRYPOINT",
            "adapter": "argocd",
            "value": "api-node-boats.qa.bgrp.io",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "entrypoint",
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "bg-qa",
                }
            ],
        },
    ]


def test_build_deployment_facts_maps_terraform_helm_provider_into_iac_facts() -> None:
    """Verify Terraform Helm provider evidence emits IAC-shaped facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "direct",
                "controller": "terraform",
                "delivery_mode": "terraform_helm_provider",
                "deployment_sources": ["helm-charts"],
                "config_sources": ["infra-live"],
                "platform_kinds": ["eks"],
                "platforms": ["platform:eks:aws:cluster/bg-qa:bg-qa:none"],
                "environments": ["bg-qa"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                "kind": "eks",
                "provider": "aws",
                "environment": "bg-qa",
                "name": "bg-qa",
            }
        ],
        entrypoints=[
            {
                "hostname": "api-node-boats.qa.bgrp.io",
                "environment": "bg-qa",
                "visibility": "public",
            }
        ],
        observed_config_environments=["bg-qa"],
    )

    assert facts == [
        {
            "fact_type": "PROVISIONED_BY_IAC",
            "adapter": "terraform",
            "value": "terraform",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_helm_provider",
                }
            ],
        },
        {
            "fact_type": "USES_PACKAGING_LAYER",
            "adapter": "terraform",
            "value": "helm",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_helm_provider",
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "terraform",
            "value": "helm-charts",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_helm_provider",
                }
            ],
        },
        {
            "fact_type": "DISCOVERS_CONFIG_IN",
            "adapter": "terraform",
            "value": "infra-live",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_helm_provider",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "terraform",
            "value": "eks",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "eks",
                    "environment": "bg-qa",
                }
            ],
        },
        {
            "fact_type": "OBSERVED_IN_ENVIRONMENT",
            "adapter": "terraform",
            "value": "bg-qa",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_helm_provider",
                }
            ],
        },
        {
            "fact_type": "EXPOSES_ENTRYPOINT",
            "adapter": "terraform",
            "value": "api-node-boats.qa.bgrp.io",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "entrypoint",
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "bg-qa",
                }
            ],
        },
    ]


def test_build_deployment_facts_maps_terraform_kubernetes_provider_into_iac_facts() -> (
    None
):
    """Verify Terraform Kubernetes provider evidence emits IAC-shaped facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "direct",
                "controller": "terraform",
                "delivery_mode": "terraform_kubernetes_provider",
                "deployment_sources": [],
                "config_sources": ["k8s-manifests"],
                "platform_kinds": ["kubernetes"],
                "platforms": ["platform:kubernetes:aws:cluster/shared:bg-qa:none"],
                "environments": ["bg-qa"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:kubernetes:aws:cluster/shared:bg-qa:none",
                "kind": "kubernetes",
                "provider": "aws",
                "environment": "bg-qa",
                "name": "shared",
            }
        ],
        entrypoints=[],
        observed_config_environments=["bg-qa"],
    )

    assert facts == [
        {
            "fact_type": "PROVISIONED_BY_IAC",
            "adapter": "terraform",
            "value": "terraform",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_kubernetes_provider",
                }
            ],
        },
        {
            "fact_type": "USES_PACKAGING_LAYER",
            "adapter": "terraform",
            "value": "kubernetes",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_kubernetes_provider",
                }
            ],
        },
        {
            "fact_type": "DISCOVERS_CONFIG_IN",
            "adapter": "terraform",
            "value": "k8s-manifests",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_kubernetes_provider",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "terraform",
            "value": "kubernetes",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "kubernetes",
                    "environment": "bg-qa",
                }
            ],
        },
        {
            "fact_type": "OBSERVED_IN_ENVIRONMENT",
            "adapter": "terraform",
            "value": "bg-qa",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "terraform",
                    "delivery_mode": "terraform_kubernetes_provider",
                }
            ],
        },
    ]


def test_build_deployment_facts_maps_flux_helmrelease_into_controller_facts() -> None:
    """Verify Flux HelmRelease evidence emits controller-backed facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "gitops",
                "controller": "flux",
                "delivery_mode": "flux_helmrelease",
                "deployment_sources": ["platform-services"],
                "config_sources": ["clusters-prod"],
                "platform_kinds": ["kubernetes"],
                "platforms": ["platform:kubernetes:aws:cluster/prod:prod:none"],
                "environments": ["prod"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:kubernetes:aws:cluster/prod:prod:none",
                "kind": "kubernetes",
                "provider": "aws",
                "environment": "prod",
                "name": "prod",
            }
        ],
        entrypoints=[],
        observed_config_environments=["prod"],
    )

    assert facts == [
        {
            "fact_type": "MANAGED_BY_CONTROLLER",
            "adapter": "flux",
            "value": "flux",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_helmrelease",
                }
            ],
        },
        {
            "fact_type": "USES_PACKAGING_LAYER",
            "adapter": "flux",
            "value": "helm",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_helmrelease",
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "flux",
            "value": "platform-services",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_helmrelease",
                }
            ],
        },
        {
            "fact_type": "DISCOVERS_CONFIG_IN",
            "adapter": "flux",
            "value": "clusters-prod",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_helmrelease",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "flux",
            "value": "kubernetes",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "kubernetes",
                    "environment": "prod",
                }
            ],
        },
        {
            "fact_type": "OBSERVED_IN_ENVIRONMENT",
            "adapter": "flux",
            "value": "prod",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_helmrelease",
                }
            ],
        },
    ]


def test_build_deployment_facts_maps_flux_kustomization_into_controller_facts() -> None:
    """Verify Flux Kustomization evidence emits controller-backed facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "gitops",
                "controller": "flux",
                "delivery_mode": "flux_kustomization",
                "deployment_sources": ["service-overlays"],
                "config_sources": ["clusters-stage"],
                "platform_kinds": ["kubernetes"],
                "platforms": ["platform:kubernetes:aws:cluster/stage:stage:none"],
                "environments": ["stage"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:kubernetes:aws:cluster/stage:stage:none",
                "kind": "kubernetes",
                "provider": "aws",
                "environment": "stage",
                "name": "stage",
            }
        ],
        entrypoints=[],
        observed_config_environments=["stage"],
    )

    assert facts[:4] == [
        {
            "fact_type": "MANAGED_BY_CONTROLLER",
            "adapter": "flux",
            "value": "flux",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_kustomization",
                }
            ],
        },
        {
            "fact_type": "USES_PACKAGING_LAYER",
            "adapter": "flux",
            "value": "kustomize",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_kustomization",
                }
            ],
        },
        {
            "fact_type": "DEPLOYS_FROM",
            "adapter": "flux",
            "value": "service-overlays",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_kustomization",
                }
            ],
        },
        {
            "fact_type": "DISCOVERS_CONFIG_IN",
            "adapter": "flux",
            "value": "clusters-stage",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "flux",
                    "delivery_mode": "flux_kustomization",
                }
            ],
        },
    ]


def test_build_deployment_facts_maps_cloudformation_ecs_into_iac_facts() -> None:
    """Verify CloudFormation ECS evidence emits IAC and runtime facts."""

    facts = build_deployment_facts(
        delivery_paths=[
            {
                "path_kind": "direct",
                "controller": "cloudformation",
                "delivery_mode": "cloudformation_ecs",
                "deployment_sources": ["service-catalog"],
                "config_sources": ["network-stack"],
                "platform_kinds": ["ecs"],
                "platforms": ["platform:ecs:aws:cluster/node10:prod:us-east-1"],
                "environments": ["prod"],
            }
        ],
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                "kind": "ecs",
                "provider": "aws",
                "environment": "prod",
                "name": "node10",
            }
        ],
        entrypoints=[
            {
                "hostname": "api-node-boats.prod.bgrp.io",
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
                    "delivery_mode": "cloudformation_ecs",
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
                    "delivery_mode": "cloudformation_ecs",
                }
            ],
        },
        {
            "fact_type": "DISCOVERS_CONFIG_IN",
            "adapter": "cloudformation",
            "value": "network-stack",
            "confidence": "high",
            "evidence": [
                {
                    "source": "delivery_path",
                    "controller": "cloudformation",
                    "delivery_mode": "cloudformation_ecs",
                }
            ],
        },
        {
            "fact_type": "RUNS_ON_PLATFORM",
            "adapter": "cloudformation",
            "value": "ecs",
            "confidence": "high",
            "evidence": [
                {
                    "source": "platform",
                    "kind": "ecs",
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
                    "delivery_mode": "cloudformation_ecs",
                }
            ],
        },
        {
            "fact_type": "EXPOSES_ENTRYPOINT",
            "adapter": "cloudformation",
            "value": "api-node-boats.prod.bgrp.io",
            "confidence": "medium",
            "evidence": [
                {
                    "source": "entrypoint",
                    "hostname": "api-node-boats.prod.bgrp.io",
                    "environment": "prod",
                }
            ],
        },
    ]
