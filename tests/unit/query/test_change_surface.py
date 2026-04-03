from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from platform_context_graph.query.impact import (
    explain_dependency_path,
    find_change_surface,
    trace_resource_to_code,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "shared_infra"
    / "shared_rds_graph.json"
)


def load_shared_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


class MockRecord:
    def __init__(self, data):
        self._data = data

    def __getitem__(self, key):
        return self._data.get(key)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()


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
                if callable(result):
                    return result(query, **kwargs)
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


def test_trace_resource_to_code_handles_shared_rds_cluster():
    fixture = load_shared_fixture()

    result = trace_resource_to_code(
        fixture,
        start="cloud-resource:shared-payments-prod",
        environment="prod",
    )

    assert result["start"]["id"] == "cloud-resource:shared-payments-prod"
    assert result["paths"]
    assert any(
        path["target"]["id"] == "repository:r_5f4f4b74" for path in result["paths"]
    )
    assert any(
        path["target"]["id"] == "repository:r_4741f4fe" for path in result["paths"]
    )

    payment_path = next(
        path
        for path in result["paths"]
        if path["hops"][0]["to"]["id"] == "workload-instance:payments-api:prod"
    )
    assert payment_path["confidence"] > 0
    assert payment_path["reason"]
    assert payment_path["evidence"]
    assert payment_path["hops"][0]["confidence"] > 0


def test_trace_resource_to_code_prefers_environment_specific_instance_path():
    fixture = load_shared_fixture()

    result = trace_resource_to_code(
        fixture,
        start="cloud-resource:shared-payments-prod",
        environment="prod",
    )

    assert (
        result["paths"][0]["hops"][0]["to"]["id"]
        == "workload-instance:payments-api:prod"
    )


def test_explain_dependency_path_prefers_instance_edge_for_environment_lookup():
    fixture = load_shared_fixture()

    result = explain_dependency_path(
        fixture,
        source="workload:payments-api",
        target="cloud-resource:shared-payments-prod",
        environment="prod",
    )

    assert result["path"]["hops"][0]["from"]["id"] == "workload:payments-api"
    assert (
        result["path"]["hops"][0]["to"]["id"] == "workload-instance:payments-api:prod"
    )
    assert (
        result["path"]["hops"][-1]["to"]["id"] == "cloud-resource:shared-payments-prod"
    )
    assert result["path"]["confidence"] > 0
    assert result["path"]["reason"]
    assert result["path"]["evidence"]


def test_find_change_surface_returns_impacted_entities_for_shared_rds_module():
    fixture = load_shared_fixture()

    result = find_change_surface(
        fixture,
        target="terraform-module:shared-rds-module",
        environment="prod",
    )

    impacted_ids = [item["entity"]["id"] for item in result["impacted"]]
    assert "cloud-resource:shared-payments-prod" in impacted_ids
    assert "workload-instance:payments-api:prod" in impacted_ids
    assert "workload-instance:ledger-worker:prod" in impacted_ids
    assert "workload:payments-admin" not in impacted_ids
    assert result["confidence"] > 0
    assert result["reason"]
    assert result["evidence"]

    impacted_resource = next(
        item
        for item in result["impacted"]
        if item["entity"]["id"] == "cloud-resource:shared-payments-prod"
    )
    assert impacted_resource["confidence"] > 0
    assert impacted_resource["reason"]
    assert impacted_resource["evidence"]


def test_trace_resource_to_code_has_minimal_db_backed_fallback():
    db = make_mock_db(
        {
            "MATCH (n) WHERE n.id = $id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "cloud-resource:shared-payments-prod",
                        "name": "shared-payments-prod",
                        "type": "cloud_resource",
                    }
                )
            ),
            "WHERE source.id = $id OR target.id = $id": MockResult(
                records=[
                    {
                        "source": "cloud-resource:shared-payments-prod",
                        "source_type": "cloud_resource",
                        "target": "workload-instance:payments-api:prod",
                        "target_type": "workload_instance",
                        "type": "USES",
                        "confidence": 0.92,
                        "reason": "Payments API config points at the shared production RDS hostname",
                        "evidence": [
                            {
                                "source": "helm-values",
                                "detail": "database.host=db.prod.internal",
                                "weight": 0.92,
                            }
                        ],
                    },
                    {
                        "source": "workload-instance:payments-api:prod",
                        "source_type": "workload_instance",
                        "target": "workload:payments-api",
                        "target_type": "workload",
                        "type": "INSTANCE_OF",
                        "confidence": 1.0,
                        "reason": "Workload instance resolves to the logical workload",
                        "evidence": [
                            {
                                "source": "fixture",
                                "detail": "workload instance identity",
                                "weight": 1.0,
                            }
                        ],
                    },
                    {
                        "source": "workload:payments-api",
                        "source_type": "workload",
                        "target": "repository:r_5f4f4b74",
                        "target_type": "repository",
                        "type": "DEFINES",
                        "confidence": 1.0,
                        "reason": "Repository declares the workload",
                        "evidence": [
                            {
                                "source": "repo-manifest",
                                "detail": "deploy/workloads/payments-api.yaml",
                                "weight": 1.0,
                            }
                        ],
                    },
                ]
            ),
        }
    )

    result = trace_resource_to_code(db, start="cloud-resource:shared-payments-prod")

    assert result["paths"]
    assert result["paths"][0]["confidence"] > 0
    assert result["paths"][0]["reason"]
    assert result["paths"][0]["evidence"]


def test_find_change_surface_ignores_db_edges_without_canonical_endpoints():
    db = make_mock_db(
        {
            "WHERE r.id = $id": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_5c50d0d3",
                        "name": "api-node-search",
                        "path": "/data/repos/api-node-search",
                    }
                )
            ),
            "WHERE source.id = $id OR target.id = $id": MockResult(
                records=[
                    {
                        "source": "repository:r_5c50d0d3",
                        "source_type": "repository",
                        "target": None,
                        "target_type": None,
                        "type": "DEPLOYS",
                    }
                ]
            ),
        }
    )

    result = find_change_surface(db, target="repository:r_5c50d0d3")

    assert result["target"]["id"] == "repository:r_5c50d0d3"
    assert result["impacted"] == []


def test_explain_dependency_path_links_repo_to_deployment_source_via_argocd_name():
    def repository_lookup(_query, **kwargs):
        entity_id = kwargs["id"]
        name = (
            "api-node-search" if entity_id == "repository:r_5c50d0d3" else "helm-charts"
        )
        path = f"/data/repos/{name}"
        return MockResult(
            single_record=MockRecord(
                {
                    "id": entity_id,
                    "name": name,
                    "path": path,
                }
            )
        )

    db = make_mock_db(
        {
            "WHERE r.id = $id": repository_lookup,
            "MATCH (app)-[:SOURCES_FROM]->(source_repo:Repository)": MockResult(
                records=[
                    {
                        "app_name": "api-node-search",
                        "app_kind": "applicationset",
                        "source_paths": "argocd/api-node-search/overlays/{{.environment}}",
                        "source_roots": "argocd/api-node-search/",
                        "target_repo_id": "repository:r_20871f7f",
                        "target_repo_name": "helm-charts",
                    }
                ]
            ),
            "WHERE source.id = $id OR target.id = $id": MockResult(records=[]),
        }
    )

    result = explain_dependency_path(
        db,
        source="repository:r_5c50d0d3",
        target="repository:r_20871f7f",
    )

    assert result["path"] is not None
    assert result["path"]["hops"][0]["from"]["id"] == "repository:r_5c50d0d3"
    assert result["path"]["hops"][-1]["to"]["id"] == "repository:r_20871f7f"
    assert result["confidence"] > 0


def test_find_change_surface_links_repo_to_deployment_source_via_argocd_name():
    def repository_lookup(_query, **kwargs):
        entity_id = kwargs["id"]
        name = (
            "api-node-search" if entity_id == "repository:r_5c50d0d3" else "helm-charts"
        )
        path = f"/data/repos/{name}"
        return MockResult(
            single_record=MockRecord(
                {
                    "id": entity_id,
                    "name": name,
                    "path": path,
                }
            )
        )

    db = make_mock_db(
        {
            "WHERE r.id = $id": repository_lookup,
            "MATCH (app)-[:SOURCES_FROM]->(source_repo:Repository)": MockResult(
                records=[
                    {
                        "app_name": "api-node-search",
                        "app_kind": "applicationset",
                        "source_paths": "argocd/api-node-search/overlays/{{.environment}}",
                        "source_roots": "argocd/api-node-search/",
                        "target_repo_id": "repository:r_20871f7f",
                        "target_repo_name": "helm-charts",
                    }
                ]
            ),
            "WHERE source.id = $id OR target.id = $id": MockResult(records=[]),
        }
    )

    result = find_change_surface(
        db,
        target="repository:r_5c50d0d3",
    )

    impacted_ids = [item["entity"]["id"] for item in result["impacted"]]
    assert "repository:r_20871f7f" in impacted_ids
    assert result["confidence"] > 0


def test_workload_paths_and_change_surface_expand_through_graph_backed_instances():
    def repository_lookup(_query, **kwargs):
        entity_id = kwargs["id"]
        name = (
            "api-node-search" if entity_id == "repository:r_5c50d0d3" else "helm-charts"
        )
        return MockResult(
            single_record=MockRecord(
                {
                    "id": entity_id,
                    "name": name,
                    "path": f"/data/repos/{name}",
                }
            )
        )

    db = make_mock_db(
        {
            "MATCH (w:Workload)": MockResult(
                single_record=MockRecord(
                    {
                        "id": "workload:api-node-search",
                        "name": "api-node-search",
                        "kind": "service",
                        "repo_id": "repository:r_5c50d0d3",
                    }
                )
            ),
            "MATCH (i:WorkloadInstance)": MockResult(
                records=[
                    {
                        "id": "workload-instance:api-node-search:bg-qa",
                        "name": "api-node-search",
                        "kind": "service",
                        "environment": "bg-qa",
                        "workload_id": "workload:api-node-search",
                        "repo_id": "repository:r_5c50d0d3",
                    }
                ]
            ),
            "WHERE r.id = $id": repository_lookup,
            "WHERE source.id = $id OR target.id = $id": lambda query, **kwargs: (
                MockResult(
                    records=[
                        {
                            "source": "workload-instance:api-node-search:bg-qa",
                            "source_type": "workload_instance",
                            "source_kind": "service",
                            "source_environment": "bg-qa",
                            "source_workload_id": "workload:api-node-search",
                            "source_repo_id": "repository:r_5c50d0d3",
                            "target": "repository:r_20871f7f",
                            "target_type": "repository",
                            "target_name": "helm-charts",
                            "type": "DEPLOYMENT_SOURCE",
                            "confidence": 0.98,
                            "reason": "ApplicationSet sources deployment manifests from helm-charts",
                            "evidence": [
                                {
                                    "source": "argocd",
                                    "detail": "argocd/api-node-search/overlays/bg-qa",
                                    "weight": 0.98,
                                }
                            ],
                        }
                    ]
                )
                if kwargs["id"] == "workload-instance:api-node-search:bg-qa"
                else MockResult(records=[])
            ),
        }
    )

    path_result = explain_dependency_path(
        db,
        source="workload:api-node-search",
        target="repository:r_20871f7f",
        environment="bg-qa",
    )
    surface_result = find_change_surface(db, target="workload:api-node-search")

    assert path_result["path"] is not None
    assert path_result["path"]["hops"][0]["to"]["id"] == (
        "workload-instance:api-node-search:bg-qa"
    )
    assert path_result["path"]["hops"][-1]["to"]["id"] == "repository:r_20871f7f"
    impacted_ids = [item["entity"]["id"] for item in surface_result["impacted"]]
    assert "repository:r_20871f7f" in impacted_ids
