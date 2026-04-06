"""Focused tests for workload story environment normalization helpers."""

from __future__ import annotations

from platform_context_graph.query.story_workload_support import (
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
