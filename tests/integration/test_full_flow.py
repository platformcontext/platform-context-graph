"""Integration tests for the full PCG cloud-to-code linking flow.

Requires Neo4j running at bolt://localhost:7687 (neo4j/testpassword).
Start with: docker compose up -d

Run with:
    NEO4J_URI=bolt://localhost:7687 \
    NEO4J_USERNAME=neo4j \
    NEO4J_PASSWORD=testpassword \
    DATABASE_TYPE=neo4j \
    uv run python -m pytest tests/integration/test_full_flow.py -v
"""

import asyncio
import os
from pathlib import Path

import pytest

# Skip entire module if Neo4j env vars not set
pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "sample_projects"
YAML_FIXTURE = FIXTURES / "sample_project_yaml_infra"
TF_FIXTURE = FIXTURES / "sample_project_terraform"


@pytest.fixture(scope="module")
def db():
    """Get a Neo4j database manager."""
    os.environ.setdefault("DATABASE_TYPE", "neo4j")
    from platform_context_graph.core import get_database_manager

    mgr = get_database_manager()
    driver = mgr.get_driver()

    # Clear graph before tests
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")

    yield mgr

    # Cleanup after tests
    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
    mgr.close_driver()


@pytest.fixture(scope="module")
def graph_builder(db):
    """Get a GraphBuilder wired to Neo4j."""
    from platform_context_graph.core.jobs import JobManager
    from platform_context_graph.tools.graph_builder import GraphBuilder

    loop = asyncio.new_event_loop()
    return GraphBuilder(db, JobManager(), loop)


@pytest.fixture(scope="module")
def indexed_yaml(db, graph_builder):
    """Index the YAML infra fixture and return the db manager."""
    asyncio.run(
        graph_builder.build_graph_from_path_async(YAML_FIXTURE, is_dependency=False)
    )
    return db


class TestInfraNodesCreated:
    """Verify infrastructure nodes are created during indexing."""

    def test_k8s_resources_indexed(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run("MATCH (k:K8sResource) RETURN count(k) as cnt").single()
            assert result["cnt"] >= 4  # Deployment, Service, SA, HTTPRoute

    def test_deployment_has_container_images(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (k:K8sResource {kind: 'Deployment'}) "
                "RETURN k.container_images as ci"
            ).single()
            assert result is not None
            assert "myorg/my-api" in result["ci"]

    def test_argocd_application_indexed(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (a:ArgoCDApplication) RETURN count(a) as cnt"
            ).single()
            assert result["cnt"] >= 1

    def test_crossplane_xrd_and_claim(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            xrds = s.run("MATCH (x:CrossplaneXRD) RETURN count(x) as cnt").single()
            claims = s.run("MATCH (c:CrossplaneClaim) RETURN count(c) as cnt").single()
            assert xrds["cnt"] >= 1
            assert claims["cnt"] >= 1

    def test_helm_chart_and_values(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            charts = s.run("MATCH (h:HelmChart) RETURN count(h) as cnt").single()
            values = s.run("MATCH (h:HelmValues) RETURN count(h) as cnt").single()
            assert charts["cnt"] >= 1
            assert values["cnt"] >= 1

    def test_kustomize_overlay(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run("MATCH (k:KustomizeOverlay) RETURN count(k) as cnt").single()
            assert result["cnt"] >= 1


class TestInfraRelationshipsAutoLinked:
    """Verify infra relationships are created during normal indexing."""

    def test_selects_service_to_deployment(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (svc:K8sResource {kind: 'Service'})"
                "-[:SELECTS]->"
                "(deploy:K8sResource {kind: 'Deployment'}) "
                "RETURN svc.name as svc, deploy.name as deploy"
            ).single()
            assert result is not None
            assert result["svc"] == "my-api"

    def test_configures_values_to_chart(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (hv:HelmValues)-[:CONFIGURES]->(hc:HelmChart) "
                "RETURN hv.name as values, hc.name as chart"
            ).single()
            assert result is not None

    def test_satisfied_by_claim_to_xrd(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (c:CrossplaneClaim)-[:SATISFIED_BY]->"
                "(x:CrossplaneXRD) "
                "RETURN c.name as claim, x.kind as xrd_kind"
            ).single()
            assert result is not None

    def test_implemented_by_xrd_to_composition(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (x:CrossplaneXRD)-[:IMPLEMENTED_BY]->"
                "(comp:CrossplaneComposition) "
                "RETURN x.kind as xrd, comp.name as comp"
            ).single()
            assert result is not None

    def test_routes_to_httproute_to_service(self, indexed_yaml):
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run(
                "MATCH (r:K8sResource {kind: 'HTTPRoute'})"
                "-[:ROUTES_TO]->"
                "(svc:K8sResource {kind: 'Service'}) "
                "RETURN r.name as route, svc.name as svc"
            ).single()
            assert result is not None


class TestEcosystemHandlers:
    """Test MCP tool handlers against Neo4j."""

    def test_get_ecosystem_overview_standalone(self, indexed_yaml):
        from platform_context_graph.mcp.tools.handlers.ecosystem import (
            get_ecosystem_overview,
        )

        result = get_ecosystem_overview(indexed_yaml)
        assert result["mode"] == "standalone"
        assert "No ecosystem manifest" in result["note"]
        assert len(result["repos"]) >= 1

    def test_get_repo_summary(self, indexed_yaml):
        from platform_context_graph.mcp.tools.handlers.ecosystem import (
            get_repo_summary,
        )

        result = get_repo_summary(indexed_yaml, "sample_project_yaml_infra")
        assert "error" not in result
        assert result["file_count"] >= 1
        assert "tier" not in result  # no manifest = no tier

    def test_get_repo_context(self, indexed_yaml):
        from platform_context_graph.mcp.tools.handlers.ecosystem import (
            get_repo_context,
        )

        result = get_repo_context(indexed_yaml, "sample_project_yaml_infra")
        assert "error" not in result

        # Repository section
        assert result["repository"]["name"] == "sample_project_yaml_infra"
        assert result["repository"]["file_count"] >= 1

        # Code section (no code files in this fixture)
        assert result["code"]["functions"] == 0

        # Infrastructure section
        infra = result["infrastructure"]
        assert "k8s_resources" in infra
        assert len(infra["k8s_resources"]) >= 4
        assert "helm_charts" in infra
        assert "kustomize_overlays" in infra

        # Relationships section (auto-linked)
        rels = result["relationships"]
        rel_types = {r["type"] for r in rels}
        assert "SELECTS" in rel_types
        assert "CONFIGURES" in rel_types

        # Ecosystem section (no manifest)
        assert result["ecosystem"] is None

    def test_find_blast_radius_standalone(self, indexed_yaml):
        from platform_context_graph.mcp.tools.handlers.ecosystem import (
            find_blast_radius,
        )

        result = find_blast_radius(indexed_yaml, "sample_project_yaml_infra")
        assert "error" not in result


class TestFullChainTraversal:
    """Test the full cloud-to-code chain query pattern."""

    def test_service_to_deployment_to_image(self, indexed_yaml):
        """Verify Service → SELECTS → Deployment → container_images."""
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run("""
                MATCH (svc:K8sResource {kind: 'Service', name: 'my-api'})
                      -[:SELECTS]->
                      (deploy:K8sResource {kind: 'Deployment'})
                RETURN deploy.container_images as images
            """).single()
            assert result is not None
            assert "myorg/my-api" in result["images"]

    def test_crossplane_claim_chain(self, indexed_yaml):
        """Verify Claim → SATISFIED_BY → XRD → IMPLEMENTED_BY → Composition."""
        driver = indexed_yaml.get_driver()
        with driver.session() as s:
            result = s.run("""
                MATCH (claim:CrossplaneClaim)
                      -[:SATISFIED_BY]->(xrd:CrossplaneXRD)
                      -[:IMPLEMENTED_BY]->(comp:CrossplaneComposition)
                RETURN claim.name as claim,
                       xrd.kind as xrd,
                       comp.name as comp
            """).single()
            assert result is not None
            assert result["claim"] is not None
            assert result["comp"] is not None
