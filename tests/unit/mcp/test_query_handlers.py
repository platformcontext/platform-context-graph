"""Security-focused unit tests for raw Cypher MCP handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from neo4j import READ_ACCESS

from platform_context_graph.mcp.tools.handlers import query


class _Record:
    """Minimal Neo4j-style record stub used by handler tests."""

    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def data(self) -> dict[str, object]:
        """Return the wrapped record payload."""
        return self._payload


class _Neo4jDBManager:
    """Minimal Neo4j-flavored database manager for handler tests."""

    def __init__(self, driver: MagicMock) -> None:
        self._driver = driver

    def get_driver(self) -> MagicMock:
        """Return the injected driver."""
        return self._driver

    def get_backend_type(self) -> str:
        """Report the active backend type."""
        return "neo4j"


class _FalkorDBManager:
    """Minimal FalkorDB-flavored database manager for handler tests."""

    def __init__(self, driver: MagicMock) -> None:
        self._driver = driver

    def get_driver(self) -> MagicMock:
        """Return the injected driver."""
        return self._driver

    def get_backend_type(self) -> str:
        """Report the active backend type."""
        return "falkordb"


class _GraphRecord:
    """Minimal dict-like record for visualization handler iteration."""

    def __init__(self, *values: object) -> None:
        self._values = values

    def values(self) -> tuple[object, ...]:
        """Return the wrapped graph values."""
        return self._values


class _GraphNode:
    """Minimal graph node object with the Falkor-style surface."""

    def __init__(
        self,
        *,
        node_id: str,
        labels: set[str],
        properties: dict[str, object],
    ) -> None:
        self.id = node_id
        self.labels = labels
        self.properties = properties


def _make_session(*records: dict[str, object]) -> MagicMock:
    """Build a context-managed mocked session returning the provided rows."""

    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.run.return_value = [_Record(record) for record in records]
    return session


@pytest.mark.parametrize(
    "cypher_query",
    [
        "CALL db.labels()",
        "LOAD CSV FROM 'https://example.com/data.csv' AS row RETURN row",
        "FOREACH (_ IN [1] | CREATE (:Danger))",
    ],
)
def test_execute_cypher_query_blocks_unsafe_clauses(cypher_query: str) -> None:
    """Unsafe raw Cypher should be rejected before it reaches the database."""

    driver = MagicMock()
    db_manager = _Neo4jDBManager(driver)

    result = query.execute_cypher_query(db_manager, cypher_query=cypher_query)

    assert result == {
        "error": "This tool only supports read-only queries. Prohibited clauses like CREATE, MERGE, DELETE, CALL, FOREACH, and LOAD CSV are not allowed."
    }
    driver.session.assert_not_called()


def test_visualize_graph_query_escapes_graph_controlled_strings_in_html(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Visualization HTML should escape JSON payloads before embedding them."""

    node = _GraphNode(
        node_id="n-1",
        labels={"Repository"},
        properties={"name": "</script><script>alert(1)</script>"},
    )
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.run.return_value = [_GraphRecord(node)]
    driver = MagicMock()
    driver.session.return_value = session
    db_manager = _FalkorDBManager(driver)
    monkeypatch.chdir(tmp_path)

    result = query.visualize_graph_query(
        db_manager,
        cypher_query="MATCH (n) RETURN n LIMIT 1",
    )

    html_path = tmp_path / "codegraph_viz.html"
    html = html_path.read_text(encoding="utf-8")

    assert result["success"] is True
    assert result["visualization_url"] == f"file://{html_path}"
    assert "</script><script>alert(1)</script>" not in html
    assert r"\u003c/script\u003e\u003cscript\u003ealert(1)\u003c/script\u003e" in html


def test_execute_cypher_query_uses_read_access_for_neo4j() -> None:
    """Read-only Cypher queries should open Neo4j sessions in READ mode."""

    session = _make_session({"name": "repo-a"})
    driver = MagicMock()
    driver.session.return_value = session
    db_manager = _Neo4jDBManager(driver)

    result = query.execute_cypher_query(
        db_manager,
        cypher_query="MATCH (r:Repository) RETURN r.name AS name LIMIT 1",
    )

    assert result == {
        "success": True,
        "query": "MATCH (r:Repository) RETURN r.name AS name LIMIT 1",
        "record_count": 1,
        "results": [{"name": "repo-a"}],
    }
    driver.session.assert_called_once_with(default_access_mode=READ_ACCESS)


def test_visualize_graph_query_blocks_unsafe_clauses_for_neo4j_browser() -> None:
    """Visualization should reject unsafe Cypher instead of emitting a browser URL."""

    driver = MagicMock()
    db_manager = _Neo4jDBManager(driver)

    result = query.visualize_graph_query(
        db_manager,
        cypher_query="CALL db.labels()",
    )

    assert result == {
        "error": "This tool only supports read-only queries. Prohibited clauses like CREATE, MERGE, DELETE, CALL, FOREACH, and LOAD CSV are not allowed."
    }
    driver.session.assert_not_called()


def test_visualize_graph_query_blocks_unsafe_clauses_before_falkordb_execution() -> (
    None
):
    """Visualization should reject unsafe Cypher before FalkorDB receives it."""

    session = _make_session()
    driver = MagicMock()
    driver.session.return_value = session
    db_manager = _FalkorDBManager(driver)

    result = query.visualize_graph_query(
        db_manager,
        cypher_query="LOAD CSV FROM 'https://example.com/data.csv' AS row RETURN row",
    )

    assert result == {
        "error": "This tool only supports read-only queries. Prohibited clauses like CREATE, MERGE, DELETE, CALL, FOREACH, and LOAD CSV are not allowed."
    }
    driver.session.assert_not_called()
