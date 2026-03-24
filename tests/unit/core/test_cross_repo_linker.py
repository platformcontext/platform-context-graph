"""Tests for cross-repo linker ArgoCD coverage."""

from types import SimpleNamespace

from platform_context_graph.tools.cross_repo_linker import CrossRepoLinker


class MockResult:
    """Minimal query result stub that exposes ``data`` and ``single``."""

    def __init__(
        self,
        count: int = 0,
        rows: list[dict[str, object]] | None = None,
    ) -> None:
        self._count = count
        self._rows = rows or []

    def data(self):
        return self._rows

    def single(self):
        return {"cnt": self._count}


class _Session:
    """Context-managed fake Neo4j session for cross-repo linker tests."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **kwargs):
        self.queries.append(query)
        if "RETURN repo.id as id" in query:
            return MockResult(
                rows=[
                    {
                        "id": "repository:r_payments",
                        "name": "payments-api",
                        "remote_url": "https://github.com/platformcontext/payments-api",
                        "repo_slug": "platformcontext/payments-api",
                    }
                ]
            )
        if "RETURN app.source_repo as source_repo" in query:
            return MockResult(
                rows=[
                    {
                        "source_repo": "git@github.com:platformcontext/payments-api.git",
                    }
                ]
            )
        if "RETURN app.source_repos as source_repos" in query:
            return MockResult(
                rows=[
                    {
                        "source_repos": "git@github.com:platformcontext/payments-api.git",
                    }
                ]
            )
        return MockResult(1)


def _make_linker():
    """Create a linker with a recording Neo4j session."""
    session = _Session()
    db = SimpleNamespace(
        get_driver=lambda: SimpleNamespace(session=lambda: session)
    )
    return CrossRepoLinker(db), session.queries


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
