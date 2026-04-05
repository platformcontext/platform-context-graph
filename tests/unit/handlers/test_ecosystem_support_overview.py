"""Tests for MCP deployment overview story shaping."""

from platform_context_graph.mcp.tools.handlers.ecosystem_support_overview import (
    build_deployment_overview,
)


def test_build_deployment_overview_ranks_and_truncates_low_signal_story_lines() -> None:
    overview = build_deployment_overview(
        hostnames=[{"hostname": "api-node-boats.qa.bgrp.io", "visibility": "public"}],
        api_surface={"api_versions": ["v3"], "docs_routes": ["/_specs"]},
        platforms=[],
        delivery_paths=[
            {
                "controller": "github_actions",
                "automation_repositories": ["boatsgroup/core-engineering-automation"],
                "deployment_sources": ["helm-charts"],
                "platform_kinds": ["eks"],
                "environments": ["bg-qa"],
            }
        ],
        deployment_artifacts={
            "config_paths": [
                {"path": "/configd/api-node-boats/*", "source_repo": "helm-charts"},
                {
                    "path": "/configd/api-node-boats/*",
                    "source_repo": "terraform-stack-node10",
                },
                {"path": "/api/api-node-boats/*", "source_repo": "helm-charts"},
                {
                    "path": "/api/api-node-boats/*",
                    "source_repo": "terraform-stack-node10",
                },
                {"path": "/secrets/api-node-boats/*", "source_repo": "helm-charts"},
                {
                    "path": "/secrets/api-node-boats/*",
                    "source_repo": "terraform-stack-node10",
                },
            ],
            "service_ports": [
                {"port": "3081", "source_repo": "helm-charts"},
            ],
            "gateways": [
                {"name": "envoy-internal", "source_repo": "helm-charts"},
            ],
        },
        consumer_repositories=[
            {
                "repository": "automate-yachtworld",
                "evidence_kinds": ["hostname_reference"],
                "sample_paths": ["group_vars/qa/api.yml"],
            },
            {"repository": "broker-ui", "evidence_kinds": ["repository_reference"]},
            {"repository": "boats-admin", "evidence_kinds": ["repository_reference"]},
            {"repository": "boats-mobile", "evidence_kinds": ["repository_reference"]},
        ],
    )

    assert overview["topology_story"] == [
        "Public entrypoints: api-node-boats.qa.bgrp.io.",
        "API surface exposes versions v3 and docs routes /_specs.",
        "GitHub Actions via boatsgroup/core-engineering-automation deploys from helm-charts onto EKS in bg-qa.",
        "Traffic enters through gateways envoy-internal on service ports 3081.",
        "Shared config families span helm-charts, terraform-stack-node10: /api/api-node-boats/*, /configd/api-node-boats/*, and 1 more.",
        "Top consumer-only repository automate-yachtworld references this service via hostname references in group_vars/qa/api.yml. Additional consumers: broker-ui, boats-admin, and 1 more.",
    ]


def test_build_deployment_overview_separates_distinct_shared_config_groups() -> None:
    """Different shared-config repo sets should render as separate ranked groups."""

    overview = build_deployment_overview(
        hostnames=[],
        api_surface={},
        platforms=[],
        delivery_paths=[],
        deployment_artifacts={
            "config_paths": [
                {"path": "/configd/api-node-boats/*", "source_repo": "helm-charts"},
                {
                    "path": "/configd/api-node-boats/*",
                    "source_repo": "terraform-stack-node10",
                },
                {"path": "/api/api-node-boats/*", "source_repo": "helm-charts"},
                {
                    "path": "/api/api-node-boats/*",
                    "source_repo": "terraform-stack-node10",
                },
                {
                    "path": "/secrets/api-node-boats/*",
                    "source_repo": "iac-eks-observability",
                },
                {"path": "/secrets/api-node-boats/*", "source_repo": "helm-charts"},
            ]
        },
    )

    assert overview["topology_story"] == [
        "Shared config families span helm-charts, terraform-stack-node10: /api/api-node-boats/*, /configd/api-node-boats/*; and helm-charts, iac-eks-observability: /secrets/api-node-boats/*."
    ]


def test_build_deployment_overview_falls_back_to_controller_story() -> None:
    """Deployment controllers and variants should shape a story without workflows."""

    overview = build_deployment_overview(
        hostnames=[],
        api_surface={},
        platforms=[
            {
                "id": "platform:ecs:aws:cluster/node10:prod:none",
                "kind": "ecs",
                "provider": "aws",
                "environment": "prod",
                "name": "node10",
            }
        ],
        delivery_paths=[],
        terraform_modules=[
            {
                "name": "api_node_boats",
                "repository": "terraform-stack-node10",
                "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                "version": "~> 3.0",
                "deployment_name": "api-node-boats",
                "repo_name": "api-node-boats",
                "create_deploy": True,
                "cluster_name": "node10",
            },
            {
                "name": "api_node_boats_batch",
                "repository": "terraform-stack-node10",
                "source": "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws",
                "version": "~> 3.0",
                "deployment_name": "api-node-boats-batch",
                "repo_name": "api-node-boats",
                "create_deploy": False,
                "cluster_name": "node10",
            },
        ],
        terraform_resources=[
            {
                "resource_type": "aws_codedeploy_deployment_group",
                "name": "api_node_boats",
                "repository": "terraform-stack-node10",
                "file": "shared/codedeploy.tf",
            }
        ],
    )

    assert overview["deployment_story"] == [
        "Deployment controllers codedeploy and terraform manage variants api_node_boats and api_node_boats_batch on ECS node10 in prod."
    ]
    assert overview["topology_story"] == [
        "Deployment controllers codedeploy and terraform manage variants api_node_boats and api_node_boats_batch on ECS node10 in prod."
    ]


def test_build_deployment_overview_skips_low_signal_terraform_fallback_story() -> None:
    """Large unrelated Terraform module sets should not become the main story."""

    overview = build_deployment_overview(
        hostnames=[],
        api_surface={},
        platforms=[],
        delivery_paths=[],
        terraform_modules=[
            {
                "name": f"module_{index}",
                "repository": repository,
                "source": "boatsgroup.pe.jfrog.io/TF__BG/example/aws",
                "version": "~> 1.0",
            }
            for index, repository in enumerate(
                [
                    "dap-data-framework",
                    "dap-dataplatform-infrastructure",
                    "dap-general-purpose",
                    "dap-sharedservices-infrastructure",
                    "github-settings",
                    "helm-charts",
                    "api-node-template",
                ],
                start=1,
            )
        ],
    )

    assert "deployment_story" not in overview
    assert "topology_story" not in overview


def test_build_deployment_overview_falls_back_to_controller_driven_paths() -> None:
    """Controller-driven automation paths should shape a story before generic fallback."""

    overview = build_deployment_overview(
        hostnames=[],
        api_surface={},
        platforms=[],
        delivery_paths=[],
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
    )

    assert overview["deployment_story"] == [
        "Jenkins invokes Ansible entry points deploy.yml targeting mws and prod for wordpress website fleets with support from terraform-stack-mws."
    ]
    assert overview["topology_story"] == [
        "Jenkins invokes Ansible entry points deploy.yml targeting mws and prod for wordpress website fleets with support from terraform-stack-mws."
    ]


def test_build_deployment_overview_prefers_richer_controller_driven_story_over_generic_jenkins_path() -> (
    None
):
    """Generic Jenkins delivery summaries should yield to richer controller-driven evidence."""

    overview = build_deployment_overview(
        hostnames=[],
        api_surface={},
        platforms=[],
        delivery_paths=[
            {
                "controller": "jenkins",
                "automation_repositories": [],
                "deployment_sources": [],
                "provisioning_repositories": [],
                "platform_kinds": [],
                "environments": [],
            }
        ],
        controller_driven_paths=[
            {
                "controller_kind": "jenkins",
                "automation_kind": "ansible",
                "entry_points": ["deploy.yml", "local.yml"],
                "target_descriptors": ["server-dmmwebsites", "localhost"],
                "runtime_family": "wordpress_website_fleet",
                "supporting_repositories": [],
                "confidence": "high",
            }
        ],
    )

    assert overview["deployment_story"] == [
        "Jenkins invokes Ansible entry points deploy.yml and local.yml targeting server-dmmwebsites and localhost for wordpress website fleets."
    ]
