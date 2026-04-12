"""Integration tests for warehouse replay graph persistence."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)


def _count(indexed_ecosystems, query: str, **params: object) -> int:
    """Return an integer count from a simple count-only Cypher query."""

    driver = indexed_ecosystems.get_driver()
    with driver.session() as session:
        record = session.run(query, **params).single()
    assert record is not None
    return int(record["cnt"])


def test_warehouse_replay_nodes_are_created(indexed_ecosystems) -> None:
    """Warehouse replay fixtures should persist assets and query executions."""

    assert (
        _count(
            indexed_ecosystems,
            "MATCH (q:QueryExecution) "
            "WHERE q.path CONTAINS 'warehouse_replay_comprehensive' "
            "RETURN count(q) as cnt",
        )
        == 2
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (a:DataAsset {name: 'analytics.finance.daily_revenue'}) "
            "WHERE a.path CONTAINS 'warehouse_replay_comprehensive' "
            "RETURN count(a) as cnt",
        )
        == 1
    )


def test_warehouse_replay_relationships_are_created(indexed_ecosystems) -> None:
    """Warehouse replay fixtures should persist observed query-to-asset edges."""

    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:QueryExecution {name: 'daily_revenue_build'})"
            "-[:RUNS_QUERY_AGAINST]->"
            "(:DataAsset {name: 'analytics.finance.revenue'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )


def test_bi_replay_nodes_and_dashboard_relationships_are_created(
    indexed_ecosystems,
) -> None:
    """BI replay fixtures should persist dashboards and POWERS edges."""

    assert (
        _count(
            indexed_ecosystems,
            "MATCH (d:DashboardAsset {name: 'Revenue Overview'}) "
            "RETURN count(d) as cnt",
        )
        == 1
    )


def test_semantic_replay_nodes_and_lineage_relationships_are_created(
    indexed_ecosystems,
) -> None:
    """Semantic replay fixtures should persist semantic assets and fields."""

    assert (
        _count(
            indexed_ecosystems,
            "MATCH (a:DataAsset {name: 'semantic.finance.revenue_semantic'}) "
            "RETURN count(a) as cnt",
        )
        == 1
    )


def test_quality_replay_nodes_and_quality_relationships_are_created(
    indexed_ecosystems,
) -> None:
    """Quality replay fixtures should persist checks and ASSERTS_QUALITY_ON edges."""

    assert (
        _count(
            indexed_ecosystems,
            "MATCH (q:DataQualityCheck {name: 'daily_revenue_freshness'}) "
            "RETURN count(q) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataQualityCheck {name: 'daily_revenue_freshness'})"
            "-[:ASSERTS_QUALITY_ON]->"
            "(:DataAsset {name: 'analytics.finance.daily_revenue'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataQualityCheck {name: 'gross_amount_non_negative'})"
            "-[:ASSERTS_QUALITY_ON]->"
            "(:DataColumn {name: 'analytics.finance.daily_revenue.gross_amount'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataAsset {name: 'semantic.finance.revenue_semantic'})"
            "-[:ASSET_DERIVES_FROM]->"
            "(:DataAsset {name: 'analytics.finance.daily_revenue'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataColumn {name: 'semantic.finance.revenue_semantic.gross_amount'})"
            "-[:COLUMN_DERIVES_FROM]->"
            "(:DataColumn {name: 'analytics.finance.daily_revenue.gross_amount'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataColumn {name: 'semantic.finance.revenue_semantic.gross_amount'})"
            "-[:POWERS]->"
            "(:DashboardAsset {name: 'Semantic Revenue Overview'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataAsset {name: 'analytics.finance.daily_revenue'})"
            "-[:POWERS]->"
            "(:DashboardAsset {name: 'Revenue Overview'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataColumn {name: 'analytics.finance.daily_revenue.gross_amount'})"
            "-[:POWERS]->"
            "(:DashboardAsset {name: 'Revenue Overview'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:QueryExecution {name: 'revenue_dashboard_lookup'})"
            "-[:RUNS_QUERY_AGAINST]->"
            "(:DataAsset {name: 'analytics.finance.daily_revenue'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
