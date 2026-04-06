from __future__ import annotations

from platform_context_graph.query.repositories.content_enrichment_delivery_paths import (
    summarize_delivery_paths,
)


def test_summarize_delivery_paths_falls_back_to_context_when_commands_are_missing() -> (
    None
):
    result = summarize_delivery_paths(
        delivery_workflows={
            "github_actions": {
                "workflows": [
                    {
                        "name": "Pull Request: CI Dispatch",
                        "relative_path": ".github/workflows/pr-ci-dispatch.yml",
                    },
                    {
                        "name": "Pull Request: Command Dispatch",
                        "relative_path": ".github/workflows/pr-command-dispatch.yml",
                    },
                ],
                "automation_repositories": [
                    {
                        "repository": "boatsgroup/core-engineering-automation",
                        "owner": "boatsgroup",
                        "name": "core-engineering-automation",
                        "ref": "v2",
                    }
                ],
                "commands": [],
            }
        },
        platforms=[
            {
                "id": "platform:ecs:aws:cluster/node10:none:none",
                "kind": "ecs",
                "provider": "aws",
                "environment": None,
                "name": "node10",
            },
            {
                "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                "kind": "eks",
                "provider": "aws",
                "environment": "bg-qa",
                "name": "bg-qa",
            },
        ],
        deploys_from=[{"name": "helm-charts"}],
        discovers_config_in=[],
        provisioned_by=[{"name": "terraform-stack-node10"}],
    )

    assert result == [
        {
            "path_kind": "gitops",
            "controller": "github_actions",
            "delivery_mode": "eks_gitops",
            "commands": [],
            "supporting_workflows": [
                "pr-ci-dispatch.yml",
                "pr-command-dispatch.yml",
            ],
            "automation_repositories": ["boatsgroup/core-engineering-automation"],
            "platform_kinds": ["eks"],
            "platforms": ["platform:eks:aws:cluster/bg-qa:bg-qa:none"],
            "deployment_sources": ["helm-charts"],
            "config_sources": [],
            "provisioning_repositories": [],
            "environments": ["bg-qa"],
            "summary": (
                "GitHub Actions drives a GitOps deployment path through helm-charts "
                "onto EKS platforms."
            ),
        },
        {
            "path_kind": "direct",
            "controller": "github_actions",
            "delivery_mode": "continuous_deployment",
            "commands": [],
            "supporting_workflows": [
                "pr-ci-dispatch.yml",
                "pr-command-dispatch.yml",
            ],
            "automation_repositories": ["boatsgroup/core-engineering-automation"],
            "platform_kinds": ["ecs"],
            "platforms": ["platform:ecs:aws:cluster/node10:none:none"],
            "deployment_sources": [],
            "config_sources": [],
            "provisioning_repositories": ["terraform-stack-node10"],
            "environments": [],
            "summary": (
                "GitHub Actions drives a direct deployment path through "
                "terraform-stack-node10 onto ECS platforms."
            ),
        },
    ]


def test_summarize_delivery_paths_adds_local_plain_helm_and_manifest_paths() -> None:
    """Local deployment artifacts should surface evidence-only delivery paths."""

    result = summarize_delivery_paths(
        delivery_workflows={},
        controller_driven_paths=[],
        platforms=[
            {
                "id": "platform:kubernetes:aws:cluster/modern:prod:none",
                "kind": "kubernetes",
                "provider": "aws",
                "environment": "prod",
                "name": "modern",
            }
        ],
        deploys_from=[],
        discovers_config_in=[],
        provisioned_by=[],
        deployment_artifacts={
            "charts": [
                {
                    "relative_path": "charts/service-edge-api/Chart.yaml",
                    "environment": "prod",
                }
            ],
            "images": [
                {
                    "relative_path": "charts/service-edge-api/values.yaml",
                    "environment": "prod",
                }
            ],
            "k8s_resources": [
                {
                    "resource_path": "k8s/deployment.yaml",
                    "environment": "modern",
                }
            ],
        },
    )

    assert result == [
        {
            "path_kind": "direct",
            "controller": "",
            "delivery_mode": "plain_helm_release",
            "commands": [],
            "supporting_workflows": [],
            "automation_repositories": [],
            "platform_kinds": ["kubernetes"],
            "platforms": ["platform:kubernetes:aws:cluster/modern:prod:none"],
            "deployment_sources": ["charts/service-edge-api"],
            "config_sources": ["charts/service-edge-api/values.yaml"],
            "provisioning_repositories": [],
            "environments": ["prod"],
            "summary": (
                "Indexed deployment artifacts indicate a direct Helm deployment "
                "path through charts/service-edge-api onto Kubernetes platforms."
            ),
        },
        {
            "path_kind": "direct",
            "controller": "",
            "delivery_mode": "plain_kubernetes_manifests",
            "commands": [],
            "supporting_workflows": [],
            "automation_repositories": [],
            "platform_kinds": ["kubernetes"],
            "platforms": ["platform:kubernetes:aws:cluster/modern:prod:none"],
            "deployment_sources": ["k8s"],
            "config_sources": [],
            "provisioning_repositories": [],
            "environments": ["prod", "modern"],
            "summary": (
                "Indexed deployment artifacts indicate a direct Kubernetes "
                "manifest deployment path through k8s onto Kubernetes platforms."
            ),
        },
    ]
