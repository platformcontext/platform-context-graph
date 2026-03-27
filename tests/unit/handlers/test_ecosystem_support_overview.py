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
            ]
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
                {"path": "/configd/api-node-boats/*", "source_repo": "terraform-stack-node10"},
                {"path": "/api/api-node-boats/*", "source_repo": "helm-charts"},
                {"path": "/api/api-node-boats/*", "source_repo": "terraform-stack-node10"},
                {"path": "/secrets/api-node-boats/*", "source_repo": "iac-eks-observability"},
                {"path": "/secrets/api-node-boats/*", "source_repo": "helm-charts"},
            ]
        },
    )

    assert overview["topology_story"] == [
        "Shared config families span helm-charts, terraform-stack-node10: /api/api-node-boats/*, /configd/api-node-boats/*; and helm-charts, iac-eks-observability: /secrets/api-node-boats/*."
    ]
