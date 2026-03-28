"""Integration tests verifying MCP-style queries return correct results.

These tests use the higher-level handler functions and direct Cypher to
verify the query pipeline produces useful answers from the comprehensive
fixture repos.

Requires docker compose up (ingests ecosystems/ fixtures into Neo4j).

Run with:
    NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=testpassword \
    DATABASE_TYPE=neo4j uv run python -m pytest tests/integration/test_mcp_language_queries.py -v
"""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)


class TestFindCodeQueries:
    """Test code search patterns against comprehensive fixtures."""

    def test_find_python_functions_by_name(self, indexed_ecosystems):
        """Searching for 'greet' finds Python function nodes."""
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (f:Function) WHERE f.name = 'greet' "
                "AND f.path CONTAINS 'python_comprehensive' "
                "RETURN f.name as name, f.path as path"
            ).data()
            assert len(results) >= 1

    def test_find_go_functions_by_name(self, indexed_ecosystems):
        """Searching for 'Greet' finds Go function nodes."""
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (f:Function) WHERE f.name = 'Greet' "
                "AND f.path CONTAINS 'go_comprehensive' "
                "RETURN f.name as name, f.path as path"
            ).data()
            assert len(results) >= 1

    def test_find_class_across_languages(self, indexed_ecosystems):
        """Searching for 'Config' finds classes across multiple languages."""
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (c:Class) WHERE c.name = 'Config' "
                "RETURN c.name as name, c.lang as lang"
            ).data()
            assert len(results) >= 2
            langs = {r["lang"] for r in results}
            assert len(langs) >= 2  # Found in at least 2 languages


class TestRepoContextQueries:
    """Test repo context queries for repos with both code and IaC."""

    def test_terraform_repo_has_infra(self, indexed_ecosystems):
        from platform_context_graph.mcp.tools.handlers.ecosystem import (
            get_repo_context,
        )

        result = get_repo_context(indexed_ecosystems, "terraform_comprehensive")
        if "error" in result:
            pytest.skip(f"Repo not found: {result['error']}")

        infra = result.get("infrastructure", {})
        assert len(infra.get("terraform_resources", [])) >= 3

    def test_kubernetes_repo_has_k8s_resources(self, indexed_ecosystems):
        from platform_context_graph.mcp.tools.handlers.ecosystem import (
            get_repo_context,
        )

        result = get_repo_context(indexed_ecosystems, "kubernetes_comprehensive")
        if "error" in result:
            pytest.skip(f"Repo not found: {result['error']}")

        infra = result.get("infrastructure", {})
        assert len(infra.get("k8s_resources", [])) >= 5

    def test_helm_repo_has_charts(self, indexed_ecosystems):
        from platform_context_graph.mcp.tools.handlers.ecosystem import (
            get_repo_context,
        )

        result = get_repo_context(indexed_ecosystems, "helm_comprehensive")
        if "error" in result:
            pytest.skip(f"Repo not found: {result['error']}")

        infra = result.get("infrastructure", {})
        assert len(infra.get("helm_charts", [])) >= 1


class TestEcosystemOverview:
    """Test ecosystem overview with all comprehensive fixtures."""

    def test_repos_exist_in_graph(self, indexed_ecosystems):
        """Verify Repository nodes exist for indexed fixtures."""
        expected_count = len(
            [
                path
                for path in (Path(__file__).parent.parent / "fixtures" / "ecosystems").iterdir()
                if path.is_dir() and not path.name.startswith(".")
            ]
        )
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            result = s.run("MATCH (r:Repository) RETURN count(r) as cnt").single()
            assert result["cnt"] == expected_count

    def test_multiple_languages_indexed(self, indexed_ecosystems):
        """Verify functions from multiple languages exist in the graph."""
        driver = indexed_ecosystems.get_driver()
        with driver.session() as s:
            results = s.run(
                "MATCH (f:Function) "
                "WHERE f.lang IS NOT NULL "
                "RETURN DISTINCT f.lang as lang"
            ).data()
            langs = {r["lang"] for r in results if r["lang"]}
            expected = {"python", "go", "typescript", "rust", "java"}
            assert langs >= expected, f"Missing langs: {expected - langs}"
