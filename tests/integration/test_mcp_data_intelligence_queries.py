"""Integration tests for repo context and story data-intelligence surfaces."""

from __future__ import annotations

import os

import pytest

from platform_context_graph.query.repositories import (
    get_repository_context,
    get_repository_story,
)
from platform_context_graph.query.impact import find_change_surface

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
        "runs_query_against": 0,
        "powers": 0,
        "asserts_quality_on": 0,
        "owns": 0,
        "declares_contract_for": 0,
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


def test_warehouse_replay_repo_context_surfaces_observed_queries(
    indexed_ecosystems,
) -> None:
    """Repo context should expose warehouse replay executions and observed edges."""

    result = get_repository_context(
        indexed_ecosystems,
        repo_id="warehouse_replay_comprehensive",
    )

    assert result["data_intelligence"]["query_execution_count"] == 2
    assert result["data_intelligence"]["relationship_counts"] == {
        "compiles_to": 0,
        "asset_derives_from": 0,
        "column_derives_from": 0,
        "runs_query_against": 4,
        "powers": 0,
        "asserts_quality_on": 0,
        "owns": 0,
        "declares_contract_for": 0,
    }


def test_warehouse_replay_repo_story_mentions_observed_queries(
    indexed_ecosystems,
) -> None:
    """Repo story should summarize replayed warehouse query coverage."""

    result = get_repository_story(
        indexed_ecosystems,
        repo_id="warehouse_replay_comprehensive",
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "2 warehouse queries" in data_section["summary"]


def test_reconciliation_repo_context_surfaces_declared_vs_observed_mismatch(
    indexed_ecosystems,
) -> None:
    """Repo context should distinguish shared, declared-only, and observed-only assets."""

    result = get_repository_context(
        indexed_ecosystems,
        repo_id="analytics_observed_reconciliation",
    )

    assert result["data_intelligence"]["reconciliation"] == {
        "status": "partial_overlap",
        "shared_asset_count": 2,
        "declared_only_asset_count": 1,
        "observed_only_asset_count": 1,
        "shared_assets": [
            "raw.public.customers",
            "raw.public.orders",
        ],
        "declared_only_assets": ["raw.public.payments"],
        "observed_only_assets": ["raw.public.refunds"],
    }


def test_reconciliation_repo_story_summarizes_declared_vs_observed_mismatch(
    indexed_ecosystems,
) -> None:
    """Repo story should summarize reconciliation gaps explicitly."""

    result = get_repository_story(
        indexed_ecosystems,
        repo_id="analytics_observed_reconciliation",
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert (
        "declared and observed lineage overlap on 2 assets, with 1 declared-only and 1 observed-only asset"
        in data_section["summary"]
    )


def test_bi_replay_repo_context_surfaces_dashboard_downstreams(
    indexed_ecosystems,
) -> None:
    """Repo context should expose dashboard counts and POWERS edges."""

    result = get_repository_context(
        indexed_ecosystems,
        repo_id="bi_replay_comprehensive",
    )

    assert result["data_intelligence"]["dashboard_asset_count"] == 1
    assert result["data_intelligence"]["relationship_counts"] == {
        "compiles_to": 0,
        "asset_derives_from": 0,
        "column_derives_from": 0,
        "runs_query_against": 1,
        "powers": 3,
        "asserts_quality_on": 0,
        "owns": 0,
        "declares_contract_for": 0,
    }


def test_bi_replay_repo_story_mentions_dashboard_consumers(indexed_ecosystems) -> None:
    """Repo story should summarize dashboard downstream coverage."""

    result = get_repository_story(
        indexed_ecosystems,
        repo_id="bi_replay_comprehensive",
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "1 dashboard" in data_section["summary"]


def test_semantic_replay_repo_context_surfaces_semantic_lineage(
    indexed_ecosystems,
) -> None:
    """Repo context should expose semantic-layer lineage and dashboards."""

    result = get_repository_context(
        indexed_ecosystems,
        repo_id="semantic_replay_comprehensive",
    )

    assert result["data_intelligence"]["analytics_model_count"] == 0
    assert result["data_intelligence"]["data_asset_count"] == 3
    assert result["data_intelligence"]["data_column_count"] == 5
    assert result["data_intelligence"]["query_execution_count"] == 1
    assert result["data_intelligence"]["dashboard_asset_count"] == 1
    assert result["data_intelligence"]["relationship_counts"] == {
        "compiles_to": 0,
        "asset_derives_from": 1,
        "column_derives_from": 2,
        "runs_query_against": 1,
        "powers": 2,
        "asserts_quality_on": 0,
        "owns": 0,
        "declares_contract_for": 0,
    }


def test_semantic_replay_repo_story_mentions_semantic_dashboard_consumers(
    indexed_ecosystems,
) -> None:
    """Repo story should summarize semantic downstream coverage."""

    result = get_repository_story(
        indexed_ecosystems,
        repo_id="semantic_replay_comprehensive",
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "1 dashboard" in data_section["summary"]
    assert [item["name"] for item in data_section["items"]] == [
        "Semantic Revenue Overview"
    ]


def test_semantic_replay_change_surface_reaches_semantic_field_and_dashboard(
    indexed_ecosystems,
) -> None:
    """Change surface should traverse warehouse columns into semantic consumers."""

    result = find_change_surface(
        indexed_ecosystems,
        target="data-column:analytics.finance.daily_revenue.gross_amount",
    )

    impacted_ids = [item["entity"]["id"] for item in result["impacted"]]

    assert "data-column:semantic.finance.revenue_semantic.gross_amount" in impacted_ids
    assert "dashboard-asset:finance:semantic-revenue-overview" in impacted_ids


def test_quality_replay_repo_context_surfaces_quality_checks(
    indexed_ecosystems,
) -> None:
    """Repo context should expose quality-check counts and relationships."""

    result = get_repository_context(
        indexed_ecosystems,
        repo_id="quality_replay_comprehensive",
    )

    assert result["data_intelligence"]["query_execution_count"] == 1
    assert result["data_intelligence"]["data_quality_check_count"] == 2
    assert result["data_intelligence"]["relationship_counts"] == {
        "compiles_to": 0,
        "asset_derives_from": 0,
        "column_derives_from": 0,
        "runs_query_against": 1,
        "powers": 0,
        "asserts_quality_on": 2,
        "owns": 0,
        "declares_contract_for": 0,
    }


def test_quality_replay_repo_story_mentions_quality_checks(indexed_ecosystems) -> None:
    """Repo story should summarize quality-check coverage."""

    result = get_repository_story(
        indexed_ecosystems,
        repo_id="quality_replay_comprehensive",
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "2 quality checks" in data_section["summary"]
    assert [item["name"] for item in data_section["items"]] == [
        "daily_revenue_freshness",
        "gross_amount_non_negative",
    ]


def test_quality_replay_change_surface_reaches_failing_quality_check(
    indexed_ecosystems,
) -> None:
    """Change surface should traverse data columns into downstream quality checks."""

    result = find_change_surface(
        indexed_ecosystems,
        target="data-column:analytics.finance.daily_revenue.gross_amount",
    )

    impacted_ids = [item["entity"]["id"] for item in result["impacted"]]

    assert "data-quality-check:finance:gross-amount-non-negative" in impacted_ids
