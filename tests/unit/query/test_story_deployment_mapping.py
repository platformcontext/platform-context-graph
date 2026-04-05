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
