"""Focused tests for workload story environment normalization helpers."""

from __future__ import annotations

from platform_context_graph.query.story_workload_support import (
    build_workload_investigation_hints,
    rank_entrypoints,
    selected_environment_for_story,
)


def test_selected_environment_for_story_prefers_specific_config_alias() -> None:
    """One canonical env family should prefer the most specific config label."""

    assert (
        selected_environment_for_story(
            selected_instance=None,
            context={
                "observed_config_environments": ["bg-qa"],
                "environments": ["qa"],
            },
            entrypoints=[
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "qa",
                    "visibility": "public",
                }
            ],
        )
        == "bg-qa"
    )


def test_rank_entrypoints_treats_environment_aliases_as_equivalent() -> None:
    """Entrypoints should rank alias-matched environments ahead of unrelated ones."""

    ranked = rank_entrypoints(
        [
            {
                "hostname": "api-node-boats.prod.bgrp.io",
                "environment": "prod",
                "visibility": "public",
            },
            {
                "hostname": "api-node-boats.qa.bgrp.io",
                "environment": "qa",
                "visibility": "public",
            },
        ],
        selected_environment="bg-qa",
    )

    assert [row["hostname"] for row in ranked] == [
        "api-node-boats.qa.bgrp.io",
        "api-node-boats.prod.bgrp.io",
    ]


def test_build_workload_investigation_hints_surfaces_related_repositories() -> None:
    """Service stories should surface a lightweight investigation handoff."""

    hints = build_workload_investigation_hints(
        subject={"name": "api-node-boats"},
        selected_environment="bg-qa",
        deploys_from=[{"name": "helm-charts"}],
        provisioned_by=[{"name": "terraform-stack-node10"}],
        delivery_paths=[{"controller": "argocd"}],
        controller_driven_paths=[],
    )

    assert hints == {
        "related_repositories": ["helm-charts", "terraform-stack-node10"],
        "evidence_families": [
            "deployment_controller",
            "gitops_config",
            "iac_infrastructure",
        ],
        "recommended_next_call": {
            "tool": "investigate_service",
            "args": {
                "service_name": "api-node-boats",
                "environment": "bg-qa",
            },
        },
    }
