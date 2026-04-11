"""SQL blast-radius regression coverage for ecosystem tools."""

from __future__ import annotations

from unittest.mock import MagicMock

from platform_context_graph.mcp.tools.handlers import ecosystem


class MockResult:
    """Mock Neo4j result wrapper."""

    def __init__(self, records: list[dict[str, object]] | None = None) -> None:
        self._records = records or []

    def data(self) -> list[dict[str, object]]:
        return self._records


def make_mock_db(query_results: dict[str, MockResult]) -> MagicMock:
    """Build a db manager whose queries are keyed by query substrings."""

    db = MagicMock()
    driver = MagicMock()
    session = MagicMock()

    def mock_run(query: str, **_kwargs: object) -> MockResult:
        for needle, result in query_results.items():
            if needle in query:
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


def test_find_blast_radius_supports_sql_table_targets() -> None:
    """SQL-table blast radius should surface normalized affected repositories."""

    db = make_mock_db(
        {
            "MATCH (table:SqlTable)": MockResult(
                records=[
                    {
                        "repo": "warehouse",
                        "repo_id": "repository:r_warehouse",
                        "tier": "tier-1",
                        "risk": "high",
                        "hops": 0,
                    },
                    {
                        "repo": "api-crm-backend",
                        "repo_id": "repository:r_api_crm",
                        "tier": "tier-2",
                        "risk": "medium",
                        "hops": 1,
                    },
                ]
            )
        }
    )

    result = ecosystem.find_blast_radius(db, "public.users", "sql_table")

    assert result["target"] == "public.users"
    assert result["target_type"] == "sql_table"
    assert result["affected"] == [
        {
            "repo": "warehouse",
            "repo_id": "repository:r_warehouse",
            "tier": "tier-1",
            "risk": "high",
            "hops": 0,
            "evidence_source": "graph_dependency",
            "inferred": False,
        },
        {
            "repo": "api-crm-backend",
            "repo_id": "repository:r_api_crm",
            "tier": "tier-2",
            "risk": "medium",
            "hops": 1,
            "evidence_source": "graph_dependency",
            "inferred": False,
        },
    ]
    assert result["affected_count"] == 2


def test_sql_table_blast_radius_query_covers_sql_edge_families() -> None:
    """The SQL-table blast-radius branch should span SQL-specific edge families."""

    recorded_queries: list[str] = []

    class RecordingSession:
        def run(self, query: str, **_kwargs: object) -> MockResult:
            recorded_queries.append(query)
            return MockResult(records=[])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    db = MagicMock()
    db.get_driver.return_value.session.return_value = RecordingSession()

    ecosystem.find_blast_radius(db, "public.users", "sql_table")

    assert any("MATCH (table:SqlTable)" in query for query in recorded_queries)
    assert any("MIGRATES" in query for query in recorded_queries)
    assert any("MAPS_TO_TABLE" in query for query in recorded_queries)
    assert any("QUERIES_TABLE" in query for query in recorded_queries)
    assert any("REFERENCES_TABLE" in query for query in recorded_queries)
    assert any("READS_FROM|TRIGGERS_ON|INDEXES" in query for query in recorded_queries)
