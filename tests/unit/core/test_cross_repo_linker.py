"""Tests for cross-repo linker ArgoCD coverage."""

from unittest.mock import MagicMock

from platform_context_graph.tools.cross_repo_linker import CrossRepoLinker


class MockResult:
    """Minimal query result stub that exposes ``single``."""

    def __init__(self, count: int):
        self._count = count

    def single(self):
        return {"cnt": self._count}


def _make_linker():
    """Create a linker with a recording Neo4j session."""
    db = MagicMock()
    driver = MagicMock()
    session = MagicMock()
    queries: list[str] = []

    def run(query, **kwargs):
        del kwargs
        queries.append(query)
        return MockResult(1)

    session.run.side_effect = run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return CrossRepoLinker(db), queries


def test_link_argocd_sources_maps_applicationsets() -> None:
    linker, queries = _make_linker()

    count = linker._link_argocd_sources()

    assert count == 2
    assert any(
        "MATCH (app:ArgoCDApplicationSet)" in query and "source_repos" in query
        for query in queries
    )


def test_link_argocd_deploys_maps_applicationsets() -> None:
    linker, queries = _make_linker()

    count = linker._link_argocd_deploys()

    assert count == 2
    assert any(
        "MATCH (app:ArgoCDApplicationSet)-[:SOURCES_FROM]->(repo:Repository)"
        in query
        and "source_roots" in query
        for query in queries
    )
