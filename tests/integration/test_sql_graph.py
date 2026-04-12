"""Integration tests verifying SQL fixtures persist into graph nodes and edges."""

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


class TestSqlGraph:
    """Verify the SQL fixture ecosystem persists SQL graph entities and edges."""

    def test_sql_nodes_are_created(self, indexed_ecosystems) -> None:
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (t:SqlTable) WHERE t.path CONTAINS 'sql_comprehensive' "
                "RETURN count(t) as cnt",
            )
            >= 2
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (v:SqlView) WHERE v.path CONTAINS 'sql_comprehensive' "
                "RETURN count(v) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (f:SqlFunction) WHERE f.path CONTAINS 'sql_comprehensive' "
                "RETURN count(f) as cnt",
            )
            >= 1
        )

    def test_sql_relationships_are_created(self, indexed_ecosystems) -> None:
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:SqlTable)-[:HAS_COLUMN]->(:SqlColumn) "
                "RETURN count(*) as cnt",
            )
            >= 1
        )

    def test_compiled_analytics_nodes_are_created(self, indexed_ecosystems) -> None:
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (m:AnalyticsModel) "
                "WHERE m.path CONTAINS 'analytics_compiled_comprehensive' "
                "RETURN count(m) as cnt",
            )
            == 2
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (a:DataAsset {name: 'analytics.public.order_metrics'}) "
                "WHERE a.path CONTAINS 'analytics_compiled_comprehensive' "
                "RETURN count(a) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (c:DataColumn {name: 'analytics.public.order_metrics.order_id'}) "
                "WHERE c.path CONTAINS 'analytics_compiled_comprehensive' "
                "RETURN count(c) as cnt",
            )
            == 1
        )

    def test_compiled_analytics_relationships_are_created(
        self, indexed_ecosystems
    ) -> None:
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (m:AnalyticsModel {name: 'order_metrics'})"
                "-[:COMPILES_TO]->"
                "(a:DataAsset {name: 'analytics.public.order_metrics'}) "
                "WHERE m.path CONTAINS 'analytics_compiled_comprehensive' "
                "  AND a.path CONTAINS 'analytics_compiled_comprehensive' "
                "RETURN count(*) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (source:DataAsset {name: 'analytics.public.order_metrics'})"
                "-[:ASSET_DERIVES_FROM]->"
                "(target:DataAsset {name: 'raw.public.orders'}) "
                "WHERE source.path CONTAINS 'analytics_compiled_comprehensive' "
                "  AND target.path CONTAINS 'analytics_compiled_comprehensive' "
                "RETURN count(*) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (source:DataColumn {name: 'analytics.public.order_metrics.order_id'})"
                "-[:COLUMN_DERIVES_FROM]->"
                "(target:DataColumn {name: 'raw.public.orders.id'}) "
                "WHERE source.path CONTAINS 'analytics_compiled_comprehensive' "
                "  AND target.path CONTAINS 'analytics_compiled_comprehensive' "
                "RETURN count(*) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (source:DataColumn {name: 'analytics.public.orders_expanded.id'})"
                "-[:COLUMN_DERIVES_FROM]->"
                "(target:DataColumn {name: 'raw.public.orders.id'}) "
                "WHERE source.path CONTAINS 'analytics_compiled_comprehensive' "
                "  AND target.path CONTAINS 'analytics_compiled_comprehensive' "
                "RETURN count(*) as cnt",
            )
            == 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:SqlView)-[:READS_FROM]->(:SqlTable) "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
        assert (
            _count(
                indexed_ecosystems,
                "MATCH (:File)-[:MIGRATES]->(:SqlTable) "
                "WHERE EXISTS { MATCH (f:File) WHERE f.path CONTAINS 'sql_comprehensive' } "
                "RETURN count(*) as cnt",
            )
            >= 1
        )
