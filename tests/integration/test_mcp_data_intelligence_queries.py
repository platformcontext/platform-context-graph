"""Integration tests for repo context and story data-intelligence surfaces."""

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


def test_analytics_repo_context_surfaces_data_intelligence(indexed_ecosystems) -> None:
    """Repo context should expose compiled analytics coverage for the fixture."""

    result = get_repository_context(
        indexed_ecosystems,
        repo_id="analytics_compiled_comprehensive",
    )

    assert result["data_intelligence"]["analytics_model_count"] == 2
    assert result["data_intelligence"]["data_asset_count"] >= 5
    assert result["data_intelligence"]["relationship_counts"] == {
        "compiles_to": 2,
        "asset_derives_from": 5,
        "column_derives_from": 6,
    }


def test_analytics_repo_story_surfaces_data_intelligence(indexed_ecosystems) -> None:
    """Repo story should include the new data-intelligence section."""

    result = get_repository_story(
        indexed_ecosystems,
        repo_id="analytics_compiled_comprehensive",
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "Compiled analytics covers 2 models" in data_section["summary"]
    assert result["data_intelligence_overview"]["analytics_model_count"] == 2
