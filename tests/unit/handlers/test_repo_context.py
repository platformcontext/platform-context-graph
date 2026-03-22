"""Tests for get_repo_context handler and degradation behavior."""

import pytest
from unittest.mock import MagicMock, call

from platform_context_graph.mcp.tools.handlers.ecosystem import (
    find_blast_radius,
    get_ecosystem_overview,
    get_repo_context,
    get_repo_summary,
    trace_deployment_chain,
)


class MockRecord:
    """Mock for a single Neo4j record."""

    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data.get(key)

    def __iter__(self):
        return iter(self._data)

    def keys(self):
        return self._data.keys()

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockResult:
    """Mock for Neo4j query result."""

    def __init__(self, records=None, single_record=None):
        self._records = records or []
        self._single_record = single_record

    def single(self):
        return self._single_record

    def data(self):
        return self._records


def make_mock_db(query_results):
    """Create a mock db_manager where session.run returns based on query content.

    Args:
        query_results: Dict mapping query substring to MockResult.
    """
    db = MagicMock()
    driver = MagicMock()
    session = MagicMock()

    def mock_run(query, **kwargs):
        for substr, result in query_results.items():
            if substr in query:
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


class TestGetRepoContext:
    """Test get_repo_context handler."""

    def test_returns_error_when_repo_not_found(self):
        db = make_mock_db(
            {
                "MATCH (r:Repository)": MockResult(single_record=None),
            }
        )
        result = get_repo_context(db, "nonexistent")
        assert "error" in result
        assert "not found" in result["error"]

    def test_returns_structured_response(self):
        code_record = MockRecord({"functions": 10, "classes": 3})
        tier_record = None
        deps_record = MockRecord({"dependencies": []})
        dependents_record = MockRecord({"dependents": []})

        db = make_mock_db(
            {
                "RETURN r.id as id, r.name as name, r.path as path": MockResult(
                    records=[
                        {
                            "id": "repository:r_ab12cd34",
                            "name": "my-api",
                            "path": "/repos/my-api",
                            "local_path": "/repos/my-api",
                            "remote_url": "https://github.com/platformcontext/my-api",
                            "repo_slug": "platformcontext/my-api",
                            "has_remote": True,
                        }
                    ]
                ),
                "split(f.name": MockResult(
                    records=[
                        {"file": "main.py", "ext": "py"},
                        {"file": "utils.py", "ext": "py"},
                        {"file": "deploy.yaml", "ext": "yaml"},
                    ]
                ),
                "count(DISTINCT fn)": MockResult(single_record=code_record),
                "fn.name IN": MockResult(records=[]),
                "K8sResource": MockResult(records=[]),
                "TerraformResource": MockResult(records=[]),
                "TerraformModule": MockResult(records=[]),
                "TerraformVariable": MockResult(records=[]),
                "TerraformOutput": MockResult(records=[]),
                "ArgoCDApplication": MockResult(records=[]),
                "ArgoCDApplicationSet": MockResult(records=[]),
                "CrossplaneXRD": MockResult(records=[]),
                "CrossplaneComposition": MockResult(records=[]),
                "CrossplaneClaim": MockResult(records=[]),
                "HelmChart": MockResult(records=[]),
                "HelmValues": MockResult(records=[]),
                "KustomizeOverlay": MockResult(records=[]),
                "TerragruntConfig": MockResult(records=[]),
                "type(rel) IN": MockResult(records=[]),
                "Tier": MockResult(single_record=tier_record),
                "DEPENDS_ON]->(dep": MockResult(single_record=deps_record),
                "DEPENDS_ON]-(dep": MockResult(single_record=dependents_record),
            }
        )

        result = get_repo_context(db, "my-api")
        assert "error" not in result
        assert result["repository"]["name"] == "my-api"
        assert result["repository"]["file_count"] == 3
        assert result["code"]["functions"] == 10
        assert result["code"]["classes"] == 3
        assert "python" in result["code"]["languages"]
        assert result["infrastructure"] == {}
        assert result["relationships"] == []
        assert result["ecosystem"] is None


class TestGracefulDegradation:
    """Test standalone mode behavior without ecosystem manifest."""

    def test_ecosystem_overview_standalone_mode(self):
        eco_record = MockRecord({"name": None, "org": None})
        db = make_mock_db(
            {
                "Ecosystem": MockResult(single_record=eco_record),
                "Tier": MockResult(records=[]),
                "Repository": MockResult(records=[]),
                "K8sResource": MockResult(
                    single_record=MockRecord(
                        {
                            "k8s": 5,
                            "argocd": 0,
                            "xrds": 0,
                            "terraform": 0,
                            "helm": 0,
                        }
                    )
                ),
                "SOURCES_FROM": MockResult(
                    single_record=MockRecord(
                        {
                            "sources_from": 0,
                            "deploys": 0,
                            "satisfied_by": 0,
                            "depends_on": 0,
                        }
                    )
                ),
            }
        )
        result = get_ecosystem_overview(db)
        assert result["mode"] == "standalone"
        assert "No ecosystem manifest" in result["note"]
        assert "ecosystem" not in result

    def test_ecosystem_overview_with_manifest(self):
        eco_record = MockRecord({"name": "my-platform", "org": "myorg"})
        db = make_mock_db(
            {
                "Ecosystem": MockResult(single_record=eco_record),
                "Tier": MockResult(records=[]),
                "Repository": MockResult(records=[]),
                "K8sResource": MockResult(
                    single_record=MockRecord(
                        {
                            "k8s": 0,
                            "argocd": 0,
                            "xrds": 0,
                            "terraform": 0,
                            "helm": 0,
                        }
                    )
                ),
                "SOURCES_FROM": MockResult(
                    single_record=MockRecord(
                        {
                            "sources_from": 0,
                            "deploys": 0,
                            "satisfied_by": 0,
                            "depends_on": 0,
                        }
                    )
                ),
            }
        )
        result = get_ecosystem_overview(db)
        assert result["ecosystem"]["name"] == "my-platform"
        assert "mode" not in result

    def test_repo_summary_omits_tier_when_null(self):
        repo_record = MockRecord({"name": "my-repo", "path": "/repos/my-repo"})
        db = make_mock_db(
            {
                "RETURN r.name as name, r.path as path": MockResult(
                    single_record=repo_record
                ),
                "split(f.name": MockResult(records=[]),
                "count(DISTINCT fn)": MockResult(
                    single_record=MockRecord({"functions": 0, "classes": 0})
                ),
                "labels(n)": MockResult(records=[]),
                "DEPENDS_ON]->(dep": MockResult(
                    single_record=MockRecord({"dependencies": []})
                ),
                "DEPENDS_ON]-(dep": MockResult(
                    single_record=MockRecord({"dependents": []})
                ),
                "Tier": MockResult(single_record=None),
            }
        )
        result = get_repo_summary(db, "my-repo")
        assert "tier" not in result

    def test_blast_radius_adds_note_when_tier_null(self):
        db = make_mock_db(
            {
                "Repository": MockResult(
                    records=[
                        {"repo": "service-a", "tier": None, "risk": None, "hops": 1},
                    ]
                ),
            }
        )
        result = find_blast_radius(db, "my-lib", "repository")
        assert "note" in result
        assert "ecosystem manifest" in result["note"]


class TestTraceDeploymentChain:
    """Test deployment traces for repository and ApplicationSet-backed services."""

    def test_returns_applicationset_backed_chain(self):
        repo_record = MockRecord({"name": "api-node-search", "path": "/repos/api-node-search"})

        db = make_mock_db(
            {
                "RETURN r.name as name, r.path as path": MockResult(
                    single_record=repo_record
                ),
                "MATCH (app:ArgoCDApplication)-[:SOURCES_FROM]->(r:Repository)": MockResult(
                    records=[]
                ),
                "MATCH (app:ArgoCDApplicationSet)": MockResult(
                    records=[
                        {
                            "app_name": "api-node-search",
                            "project": "{{.argocd.project}}",
                            "namespace": "argocd",
                            "dest_namespace": "{{.helm.namespace}}",
                            "source_repos": "https://github.com/boatsgroup/helm-charts",
                            "source_paths": "argocd/api-node-search/overlays/*/config.yaml",
                            "source_roots": "argocd/api-node-search/",
                        }
                    ]
                ),
                "MATCH (app)-[:DEPLOYS]->(k:K8sResource)": MockResult(
                    records=[
                        {
                            "name": "api-node-search",
                            "kind": "XIRSARole",
                            "namespace": "",
                            "file": "argocd/api-node-search/base/xirsarole.yaml",
                            "repository": "helm-charts",
                            "deployed_by": "api-node-search",
                        }
                    ]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(tf:TerraformResource)": MockResult(
                    records=[]
                ),
                "MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(mod:TerraformModule)": MockResult(
                    records=[]
                ),
            }
        )

        result = trace_deployment_chain(db, "api-node-search")

        assert result["repository"]["name"] == "api-node-search"
        assert result["argocd_applications"] == []
        assert result["argocd_applicationsets"] == [
            {
                "app_name": "api-node-search",
                "project": "{{.argocd.project}}",
                "namespace": "argocd",
                "dest_namespace": "{{.helm.namespace}}",
                "source_repos": "https://github.com/boatsgroup/helm-charts",
                "source_paths": "argocd/api-node-search/overlays/*/config.yaml",
                "source_roots": "argocd/api-node-search/",
            }
        ]
        assert result["k8s_resources"] == [
            {
                "name": "api-node-search",
                "kind": "XIRSARole",
                "namespace": "",
                "file": "argocd/api-node-search/base/xirsarole.yaml",
                "repository": "helm-charts",
                "deployed_by": "api-node-search",
            }
        ]
