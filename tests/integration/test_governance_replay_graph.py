"""Integration tests for governance replay graph persistence."""

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


def test_governance_replay_nodes_and_edges_are_created(indexed_ecosystems) -> None:
    """Governance replay fixtures should persist owners, contracts, and edges."""

    assert (
        _count(
            indexed_ecosystems,
            "MATCH (o:DataOwner {name: 'Finance Analytics'}) RETURN count(o) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (c:DataContract {name: 'daily_revenue_contract'}) "
            "RETURN count(c) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataOwner {name: 'Finance Analytics'})-[:OWNS]->"
            "(:DataAsset {name: 'analytics.finance.daily_revenue'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )
    assert (
        _count(
            indexed_ecosystems,
            "MATCH (:DataContract {name: 'daily_revenue_contract'})"
            "-[:DECLARES_CONTRACT_FOR]->"
            "(:DataColumn {name: 'analytics.finance.daily_revenue.customer_email'}) "
            "RETURN count(*) as cnt",
        )
        == 1
    )


def test_governance_replay_annotations_are_applied_to_targets(
    indexed_ecosystems,
) -> None:
    """Governance replay fixtures should stamp sensitivity metadata on columns."""

    driver = indexed_ecosystems.get_driver()
    with driver.session() as session:
        record = session.run(
            """
            MATCH (c:DataColumn {name: 'analytics.finance.daily_revenue.customer_email'})
            RETURN c.sensitivity AS sensitivity,
                   c.is_protected AS is_protected,
                   c.protection_kind AS protection_kind,
                   c.owner_teams AS owner_teams,
                   c.contract_names AS contract_names,
                   c.change_policies AS change_policies
            """
        ).single()

    assert record is not None
    assert record["sensitivity"] == "pii"
    assert record["is_protected"] is True
    assert record["protection_kind"] == "masked"
    assert record["owner_teams"] == ["finance-analytics"]
    assert record["contract_names"] == ["daily_revenue_contract"]
    assert record["change_policies"] == ["breaking"]

