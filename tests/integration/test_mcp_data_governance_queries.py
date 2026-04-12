"""Integration tests for governance-aware repo context and story surfaces."""

from __future__ import annotations

import os

import pytest

from platform_context_graph.query.repositories import (
    get_repository_context,
    get_repository_story,
)

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)


def test_governance_replay_repo_context_surfaces_overlay_counts(
    indexed_ecosystems,
) -> None:
    """Repo context should expose ownership, contract, and protected-column counts."""

    result = get_repository_context(
        indexed_ecosystems,
        repo_id="governance_replay_comprehensive",
    )

    assert result["data_intelligence"]["query_execution_count"] == 1
    assert result["data_intelligence"]["data_owner_count"] == 1
    assert result["data_intelligence"]["data_contract_count"] == 1
    assert result["data_intelligence"]["protected_column_count"] == 1
    assert result["data_intelligence"]["relationship_counts"] == {
        "compiles_to": 0,
        "asset_derives_from": 0,
        "column_derives_from": 0,
        "runs_query_against": 1,
        "powers": 0,
        "asserts_quality_on": 0,
        "owns": 2,
        "declares_contract_for": 3,
    }


def test_governance_replay_repo_story_mentions_governance_overlays(
    indexed_ecosystems,
) -> None:
    """Repo story should summarize governance overlay coverage."""

    result = get_repository_story(
        indexed_ecosystems,
        repo_id="governance_replay_comprehensive",
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "1 owner" in data_section["summary"]
    assert "1 contract" in data_section["summary"]
    assert "1 protected column" in data_section["summary"]
    assert [item["name"] for item in data_section["items"]] == [
        "daily_revenue_contract"
    ]

