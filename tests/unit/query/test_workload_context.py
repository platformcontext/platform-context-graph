from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from platform_context_graph.query.context import (
    ServiceAliasError,
    get_service_context,
    get_workload_story,
    get_workload_context,
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
                return result
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


def test_get_workload_context_returns_logical_and_instance_views():
    fixture = load_shared_fixture()

    logical = get_workload_context(fixture, workload_id="workload:payments-api")
    instance = get_workload_context(
        fixture,
        workload_id="workload:payments-api",
        environment="prod",
    )

    assert logical["workload"]["id"] == "workload:payments-api"
    assert [item["id"] for item in logical["instances"]] == [
        "workload-instance:payments-api:prod"
    ]
    assert logical["cloud_resources"][0]["id"] == "cloud-resource:shared-payments-prod"

    assert instance["workload"]["id"] == "workload:payments-api"
    assert instance["instance"]["id"] == "workload-instance:payments-api:prod"
    assert (
        instance["shared_resources"][0]["id"] == "cloud-resource:shared-payments-prod"
    )
    assert instance["evidence"]


def test_get_service_context_rejects_non_service_workloads_and_returns_canonical_shape():
    fixture = load_shared_fixture()

    result = get_service_context(fixture, workload_id="workload:payments-api")

    assert result["workload"]["type"] == "workload"
    assert result["requested_as"] == "service"

    with pytest.raises(ServiceAliasError):
        get_service_context(fixture, workload_id="workload:ledger-worker")


def test_get_workload_context_has_minimal_db_backed_fallback():
    db = make_mock_db(
        {
            "RETURN r.id as id, r.name as name, r.path as path": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_ab12cd34",
                        "name": "payments-platform",
                        "path": "/srv/repos/payments-platform",
                        "local_path": "/srv/repos/payments-platform",
                        "remote_url": "https://github.com/platformcontext/payments-platform",
                        "repo_slug": "platformcontext/payments-platform",
                        "has_remote": True,
                    }
                )
            ),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[
                    {
                        "name": "payments-api",
                        "kind": "Deployment",
                        "namespace": "payments",
                    }
                ]
            ),
        }
    )

    logical = get_workload_context(db, workload_id="workload:payments-api")
    instance = get_workload_context(
        db, workload_id="workload:payments-api", environment="prod"
    )

    assert logical["workload"]["id"] == "workload:payments-api"
    assert logical["workload"]["kind"] == "service"
    assert logical["repositories"][0] == {
        "id": "repository:r_ab12cd34",
        "type": "repository",
        "name": "payments-platform",
        "repo_slug": "platformcontext/payments-platform",
        "remote_url": "https://github.com/platformcontext/payments-platform",
        "has_remote": True,
    }
    assert logical["instances"][0]["id"] == "workload-instance:payments-api:payments"

    assert instance["instance"]["id"] == "workload-instance:payments-api:prod"
    assert instance["workload"]["id"] == "workload:payments-api"


def test_get_service_context_has_minimal_db_backed_fallback():
    db = make_mock_db(
        {
            "coalesce(r[$local_path_key], r.path) as local_path": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_ab12cd34",
                        "name": "payments-platform",
                        "path": "/srv/repos/payments-platform",
                        "local_path": "/srv/repos/payments-platform",
                        "remote_url": "https://github.com/platformcontext/payments-platform",
                        "repo_slug": "platformcontext/payments-platform",
                        "has_remote": True,
                    }
                )
            ),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[
                    {"name": "payments-api", "kind": "Service", "namespace": "payments"}
                ]
            ),
        }
    )

    result = get_service_context(
        db, workload_id="workload:payments-api", environment="prod"
    )

    assert result["requested_as"] == "service"
    assert result["repositories"][0] == {
        "id": "repository:r_ab12cd34",
        "type": "repository",
        "name": "payments-platform",
        "repo_slug": "platformcontext/payments-platform",
        "remote_url": "https://github.com/platformcontext/payments-platform",
        "has_remote": True,
    }
    assert result["instance"]["id"] == "workload-instance:payments-api:prod"


def test_get_workload_context_prefers_graph_backed_instances_over_namespace_defaults():
    db = make_mock_db(
        {
            "MATCH (w:Workload)": MockResult(
                single_record=MockRecord(
                    {
                        "id": "workload:api-node-search",
                        "name": "api-node-search",
                        "kind": "service",
                        "repo_id": "repository:r_5c50d0d3",
                        "repo_name": "api-node-search",
                        "repo_path": "/data/repos/api-node-search",
                        "repo_local_path": "/data/repos/api-node-search",
                        "repo_slug": "boatsgroup/api-node-search",
                        "repo_remote_url": "https://github.com/boatsgroup/api-node-search",
                        "repo_has_remote": True,
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
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[
                    {
                        "name": "api-node-search",
                        "kind": "Deployment",
                        "namespace": "",
                    }
                ]
            ),
        }
    )

    logical = get_workload_context(db, workload_id="workload:api-node-search")
    instance = get_workload_context(
        db,
        workload_id="workload:api-node-search",
        environment="bg-qa",
    )

    assert [item["id"] for item in logical["instances"]] == [
        "workload-instance:api-node-search:bg-qa"
    ]
    assert instance["instance"]["id"] == "workload-instance:api-node-search:bg-qa"


def test_get_workload_context_surfaces_graph_backed_runtime_dependencies():
    db = make_mock_db(
        {
            "MATCH (w:Workload)-[rel]->(dep:Workload)": MockResult(
                records=[
                    {
                        "id": "workload:api-node-forex",
                        "name": "api-node-forex",
                        "kind": "service",
                        "repo_id": "repository:r_dep12345",
                    }
                ]
            ),
            "MATCH (w:Workload)": MockResult(
                single_record=MockRecord(
                    {
                        "id": "workload:api-node-search",
                        "name": "api-node-search",
                        "kind": "service",
                        "repo_id": "repository:r_5c50d0d3",
                        "repo_name": "api-node-search",
                        "repo_path": "/data/repos/api-node-search",
                        "repo_local_path": "/data/repos/api-node-search",
                        "repo_slug": "boatsgroup/api-node-search",
                        "repo_remote_url": "https://github.com/boatsgroup/api-node-search",
                        "repo_has_remote": True,
                    }
                )
            ),
            "MATCH (i:WorkloadInstance)": MockResult(records=[]),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[]
            ),
        }
    )

    result = get_workload_context(db, workload_id="workload:api-node-search")

    assert [item["id"] for item in result["dependencies"]] == [
        "workload:api-node-forex"
    ]


def test_get_workload_context_enriches_repo_backed_runtime_and_dependency_data(
    monkeypatch,
):
    db = make_mock_db(
        {
            "MATCH (w:Workload)": MockResult(
                single_record=MockRecord(
                    {
                        "id": "workload:api-node-boats",
                        "name": "api-node-boats",
                        "kind": "service",
                        "repo_id": "repository:r_f9600c28",
                        "repo_name": "api-node-boats",
                        "repo_path": "/data/repos/api-node-boats",
                        "repo_local_path": "/data/repos/api-node-boats",
                        "repo_slug": "boatsgroup/api-node-boats",
                        "repo_remote_url": "https://github.com/boatsgroup/api-node-boats",
                        "repo_has_remote": True,
                    }
                )
            ),
            "MATCH (i:WorkloadInstance)": MockResult(records=[]),
            "MATCH (w:Workload)-[rel]->(dep:Workload)": MockResult(records=[]),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[]
            ),
        }
    )

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.get_repository_context",
        lambda *_args, **_kwargs: {
            "platforms": [
                {
                    "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                    "name": "bg-qa",
                    "kind": "eks",
                    "provider": "aws",
                    "environment": "bg-qa",
                }
            ],
            "hostnames": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "qa",
                    "source_repo": "api-node-boats",
                    "relative_path": "config/qa.json",
                    "visibility": "public",
                }
            ],
            "deploys_from": [
                {
                    "id": "repository:r_66cd2d76",
                    "type": "repository",
                    "name": "helm-charts",
                    "repo_slug": "boatsgroup/helm-charts",
                    "remote_url": "https://github.com/boatsgroup/helm-charts",
                    "has_remote": True,
                    "relationship_type": "DEPLOYS_FROM",
                }
            ],
            "discovers_config_in": [],
            "provisioned_by": [],
        },
    )

    logical = get_workload_context(db, workload_id="workload:api-node-boats")
    scoped = get_workload_context(
        db,
        workload_id="workload:api-node-boats",
        environment="bg-qa",
    )
    story = get_workload_story(db, workload_id="workload:api-node-boats")

    assert [item["id"] for item in logical["instances"]] == [
        "workload-instance:api-node-boats:bg-qa"
    ]
    assert [item["id"] for item in logical["dependencies"]] == ["repository:r_66cd2d76"]
    assert logical["entrypoints"] == [
        {
            "hostname": "api-node-boats.qa.bgrp.io",
            "environment": "qa",
            "source_repo": "api-node-boats",
            "relative_path": "config/qa.json",
            "visibility": "public",
        }
    ]
    assert scoped["instance"]["id"] == "workload-instance:api-node-boats:bg-qa"
    assert scoped["instances"] == []
    assert "Public entrypoints: api-node-boats.qa.bgrp.io." in story["story"]
    assert "Depends on helm-charts." in story["story"]


def test_get_workload_context_clears_instances_when_resource_instance_is_selected():
    db = make_mock_db(
        {
            "MATCH (w:Workload)": MockResult(
                single_record=MockRecord(
                    {
                        "id": "workload:api-node-boats",
                        "name": "api-node-boats",
                        "kind": "service",
                        "repo_id": None,
                        "repo_name": None,
                        "repo_path": None,
                        "repo_local_path": None,
                        "repo_slug": None,
                        "repo_remote_url": None,
                        "repo_has_remote": False,
                    }
                )
            ),
            "MATCH (i:WorkloadInstance)": MockResult(records=[]),
            "MATCH (w:Workload)-[rel]->(dep:Workload)": MockResult(records=[]),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[
                    {
                        "name": "api-node-boats",
                        "kind": "Deployment",
                        "namespace": "bg-qa",
                    }
                ]
            ),
        }
    )

    scoped = get_workload_context(
        db,
        workload_id="workload:api-node-boats",
        environment="bg-qa",
    )

    assert scoped["instance"]["id"] == "workload-instance:api-node-boats:bg-qa"
    assert scoped["instances"] == []


def test_get_workload_story_enriches_gitops_from_repo_name_fallback(
    monkeypatch,
) -> None:
    """Fallback repo-name matches should still enrich service stories with GitOps."""

    db = make_mock_db(
        {
            "MATCH (w:Workload)": MockResult(single_record=None),
            "RETURN r.id as id, r.name as name, r.path as path": MockResult(
                single_record=MockRecord(
                    {
                        "id": "repository:r_f9600c28",
                        "name": "api-node-boats",
                        "path": "/data/repos/api-node-boats",
                        "local_path": "/data/repos/api-node-boats",
                        "remote_url": "https://github.com/boatsgroup/api-node-boats",
                        "repo_slug": "boatsgroup/api-node-boats",
                        "has_remote": True,
                    }
                )
            ),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[
                    {
                        "name": "api-node-boats",
                        "kind": "Deployment",
                        "namespace": "bg-qa",
                    }
                ]
            ),
        }
    )

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.get_repository_context",
        lambda *_args, **_kwargs: {
            "platforms": [
                {
                    "id": "platform:eks:aws:cluster/bg-qa:bg-qa:none",
                    "name": "bg-qa",
                    "kind": "eks",
                    "provider": "aws",
                    "environment": "bg-qa",
                }
            ],
            "hostnames": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "bg-qa",
                    "source_repo": "helm-charts",
                    "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                    "visibility": "public",
                },
                {
                    "hostname": "api-node-boats.platformcontextgraph.svc.cluster.local",
                    "environment": "bg-qa",
                    "source_repo": "helm-charts",
                    "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                    "visibility": "internal",
                },
            ],
            "api_surface": {
                "docs_routes": ["/_specs"],
                "api_versions": ["v3"],
                "endpoints": [
                    {
                        "path": "/_status",
                        "relative_path": "catalog-specs.yaml",
                    },
                    {
                        "path": "/boats/search",
                        "relative_path": "catalog-specs.yaml",
                    },
                ],
            },
            "deploys_from": [
                {
                    "id": "repository:r_66cd2d76",
                    "type": "repository",
                    "name": "helm-charts",
                    "repo_slug": "boatsgroup/helm-charts",
                    "remote_url": "https://github.com/boatsgroup/helm-charts",
                    "has_remote": True,
                    "relationship_type": "DEPLOYS_FROM",
                }
            ],
            "discovers_config_in": [],
            "provisioned_by": [],
            "delivery_paths": [
                {
                    "path_kind": "gitops",
                    "controller": "argocd",
                    "delivery_mode": "gitops",
                    "deployment_sources": ["helm-charts"],
                    "platform_kinds": ["eks"],
                }
            ],
            "deployment_artifacts": {
                "config_paths": [
                    {
                        "path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                        "source_repo": "helm-charts",
                    }
                ],
                "service_ports": [
                    {
                        "port": 3081,
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/base/values.yaml",
                    }
                ],
                "gateways": [
                    {
                        "name": "envoy-internal",
                        "source_repo": "helm-charts",
                        "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                    }
                ],
            },
            "observed_config_environments": ["bg-qa"],
            "environments": ["bg-qa"],
            "limitations": [],
        },
    )

    story = get_workload_story(db, workload_id="workload:api-node-boats")

    assert story["gitops_overview"] is not None
    assert story["gitops_overview"]["owner"]["delivery_controllers"] == ["argocd"]
    assert story["gitops_overview"]["value_layers"][0]["relative_path"] == (
        "argocd/api-node-boats/overlays/bg-qa/values.yaml"
    )
    assert story["gitops_overview"]["environment"]["selected"] == "bg-qa"
    assert story["deployment_overview"]["internet_entrypoints"][0]["hostname"] == (
        "api-node-boats.qa.bgrp.io"
    )
    assert story["support_overview"]["entrypoints"][0]["hostname"] == (
        "api-node-boats.qa.bgrp.io"
    )
    assert story["support_overview"]["entrypoints"][1]["path"] == "/_status"


def test_get_service_context_selects_config_only_environment_when_runtime_is_missing(
    monkeypatch,
) -> None:
    """GitOps config environments should backfill service selection when needed."""

    db = make_mock_db(
        {
            "MATCH (w:Workload)": MockResult(
                single_record=MockRecord(
                    {
                        "id": "workload:api-node-boats",
                        "name": "api-node-boats",
                        "kind": "service",
                        "repo_id": "repository:r_f9600c28",
                        "repo_name": "api-node-boats",
                        "repo_path": "/data/repos/api-node-boats",
                        "repo_local_path": "/data/repos/api-node-boats",
                        "repo_slug": "boatsgroup/api-node-boats",
                        "repo_remote_url": "https://github.com/boatsgroup/api-node-boats",
                        "repo_has_remote": True,
                    }
                )
            ),
            "MATCH (i:WorkloadInstance)": MockResult(records=[]),
            "MATCH (w:Workload)-[rel]->(dep:Workload)": MockResult(records=[]),
            "MATCH (k:K8sResource)\n            WHERE k.name CONTAINS $name": MockResult(
                records=[]
            ),
        }
    )

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.get_repository_context",
        lambda *_args, **_kwargs: {
            "platforms": [],
            "hostnames": [
                {
                    "hostname": "api-node-boats.qa.bgrp.io",
                    "environment": "bg-qa",
                    "source_repo": "helm-charts",
                    "relative_path": "argocd/api-node-boats/overlays/bg-qa/values.yaml",
                    "visibility": "public",
                }
            ],
            "deploys_from": [],
            "discovers_config_in": [],
            "provisioned_by": [],
            "observed_config_environments": ["bg-qa"],
            "environments": [],
            "limitations": [],
        },
    )

    result = get_service_context(
        db,
        workload_id="workload:api-node-boats",
        environment="bg-qa",
    )

    assert result["instance"]["id"] == "workload-instance:api-node-boats:bg-qa"
    assert result["instance"]["environment"] == "bg-qa"
    assert result["instances"] == []
