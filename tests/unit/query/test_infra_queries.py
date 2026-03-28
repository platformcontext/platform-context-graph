from __future__ import annotations

from unittest.mock import MagicMock

from platform_context_graph.query.infra import (
    get_ecosystem_overview,
    get_infra_relationships,
    search_infra_resources,
)


class MockRecord:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data.get(key)

    def get(self, key, default=None):
        return self._data.get(key, default)


class MockResult:
    def __init__(self, records=None, single_record=None):
        self._records = records or []
        self._single_record = single_record

    def single(self):
        return self._single_record

    def data(self):
        return self._records


def make_mock_db(query_results):
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


def test_get_ecosystem_overview_returns_summary_shape():
    db = make_mock_db(
        {
            "OPTIONAL MATCH (e:Ecosystem)": MockResult(
                single_record=MockRecord({"name": None, "org": None})
            ),
            "MATCH (t:Tier)": MockResult(records=[]),
            "MATCH (r:Repository)": MockResult(
                records=[
                    {
                        "name": "my-api",
                        "path": "/repos/my-api",
                        "files": 3,
                        "depends_on": [],
                    }
                ]
            ),
            "OPTIONAL MATCH (k:K8sResource)": MockResult(
                single_record=MockRecord(
                    {"k8s": 1, "argocd": 0, "xrds": 0, "terraform": 0, "helm": 0}
                )
            ),
            "OPTIONAL MATCH ()-[s:SOURCES_FROM]->()": MockResult(
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
    assert result["repos"][0]["name"] == "my-api"
    assert result["infrastructure_counts"]["k8s"] == 1


def test_search_infra_resources_returns_grouped_matches():
    db = make_mock_db(
        {
            "MATCH (k:K8sResource)": MockResult(
                records=[
                    {
                        "name": "api",
                        "kind": "Service",
                        "namespace": "default",
                        "file": "svc.yaml",
                    }
                ]
            ),
            "MATCH (t:TerraformResource)": MockResult(
                records=[{"name": "db", "type": "aws_db_instance", "file": "main.tf"}]
            ),
        }
    )

    result = search_infra_resources(
        db, query="api", types=["k8s", "terraform"], limit=10
    )

    assert result["query"] == "api"
    assert "k8s_resources" in result["results"]
    assert "terraform_resources" in result["results"]


def test_search_infra_resources_includes_argocd_applicationsets() -> None:
    """ArgoCD infra search should surface ApplicationSets as first-class results."""

    db = make_mock_db(
        {
            "MATCH (a:ArgoCDApplication)": MockResult(records=[]),
            "MATCH (a:ArgoCDApplicationSet)": MockResult(
                records=[
                    {
                        "name": "api-node-boats",
                        "project": "default",
                        "namespace": "argocd",
                        "dest_namespace": "boats",
                        "repository": "iac-eks-argocd",
                        "file": "applicationsets/api-node/api-node-boats.yaml",
                    }
                ]
            ),
        }
    )

    result = search_infra_resources(db, query="api-node-boats", types=["argocd"], limit=10)

    assert result["category"] == "argocd"
    assert result["results"]["argocd_applicationsets"] == [
        {
            "name": "api-node-boats",
            "project": "default",
            "namespace": "argocd",
            "dest_namespace": "boats",
            "repository": "iac-eks-argocd",
            "file": "applicationsets/api-node/api-node-boats.yaml",
        }
    ]


def test_search_infra_resources_surfaces_crossplane_claims_from_k8s_fallback() -> None:
    """Crossplane search should surface claim-like K8s resources tied to known XRDs."""

    db = make_mock_db(
        {
            "MATCH (c:CrossplaneClaim)": MockResult(records=[]),
            "MATCH (k:K8sResource)": MockResult(
                records=[
                    {
                        "name": "api-node-boats",
                        "kind": "XIRSARole",
                        "namespace": "",
                        "api_version": "aws.bgrp.io/v1alpha1",
                        "repository": "helm-charts",
                        "file": "argocd/api-node-boats/base/xirsarole.yaml",
                    }
                ]
            ),
            "MATCH (x:CrossplaneXRD)": MockResult(records=[]),
        }
    )

    result = search_infra_resources(
        db,
        query="api-node-boats",
        types=["crossplane"],
        limit=10,
    )

    assert result["results"]["crossplane_claims"] == [
        {
            "name": "api-node-boats",
            "kind": "XIRSARole",
            "namespace": "",
            "api_version": "aws.bgrp.io/v1alpha1",
            "repository": "helm-charts",
            "file": "argocd/api-node-boats/base/xirsarole.yaml",
        }
    ]


def test_get_infra_relationships_preserves_current_shape():
    db = make_mock_db(
        {
            "MATCH (app:ArgoCDApplication)-[:DEPLOYS]->(k:K8sResource)": MockResult(
                records=[
                    {
                        "app_name": "my-api",
                        "resource_name": "my-api",
                        "resource_kind": "Deployment",
                        "namespace": "default",
                    }
                ]
            )
        }
    )

    result = get_infra_relationships(
        db, target="my-api", relationship_type="what_deploys"
    )

    assert result["query_type"] == "what_deploys"
    assert result["target"] == "my-api"
    assert result["count"] == 1


def test_infra_queries_use_repo_contains_for_flat_repo_file_lookups():
    """Infra query helpers should prefer REPO_CONTAINS for repo-to-file scans."""

    recorded_queries: list[str] = []

    class RecordingSession:
        def run(self, query, **kwargs):
            del kwargs
            recorded_queries.append(query)
            if "OPTIONAL MATCH (e:Ecosystem)" in query:
                return MockResult(single_record=MockRecord({"name": None, "org": None}))
            if "MATCH (t:Tier)" in query:
                return MockResult(records=[])
            if "MATCH (r:Repository)" in query:
                return MockResult(records=[])
            if "OPTIONAL MATCH (k:K8sResource)" in query:
                return MockResult(
                    single_record=MockRecord(
                        {"k8s": 0, "argocd": 0, "xrds": 0, "terraform": 0, "helm": 0}
                    )
                )
            if "OPTIONAL MATCH ()-[s:SOURCES_FROM]->()" in query:
                return MockResult(
                    single_record=MockRecord(
                        {
                            "sources_from": 0,
                            "deploys": 0,
                            "satisfied_by": 0,
                            "depends_on": 0,
                        }
                    )
                )
            return MockResult(records=[])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    db = MagicMock()
    db.get_driver.return_value.session.return_value = RecordingSession()

    get_infra_relationships(
        db,
        target="shared-rds",
        relationship_type="who_consumes_xrd",
    )
    get_infra_relationships(
        db,
        target="terraform-aws-vpc",
        relationship_type="module_consumers",
    )
    get_ecosystem_overview(db)

    assert any("[:REPO_CONTAINS]->(f:File)" in q or "[:REPO_CONTAINS]->(f)" in q for q in recorded_queries)
    assert not any(
        "MATCH (repo:Repository)-[:CONTAINS*]->(f:File)" in q
        for q in recorded_queries
    )
    assert any("OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)" in q for q in recorded_queries)
