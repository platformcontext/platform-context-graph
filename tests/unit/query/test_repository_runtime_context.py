from __future__ import annotations

from platform_context_graph.query.repositories.context_data import (
    build_repository_context,
)
from platform_context_graph.query.repositories.relationship_summary import (
    build_relationship_summary,
)
from platform_context_graph.query.repositories.stats_data import build_repository_stats


class MockResult:
    def __init__(self, records=None, single_record=None):
        self._records = records or []
        self._single_record = single_record

    def single(self):
        return self._single_record

    def data(self):
        return self._records


class MockSession:
    def __init__(self, query_results: dict[str, MockResult]):
        self.query_results = query_results
        self.queries: list[str] = []

    def run(self, query, *args, **kwargs):
        del args, kwargs
        self.queries.append(query)
        for token in ("dep:Repository", "prov:Repository", "SOURCES_FROM"):
            if token in query:
                token_matches = [
                    (substr, result)
                    for substr, result in self.query_results.items()
                    if substr in query and token in substr
                ]
                if token_matches:
                    return max(token_matches, key=lambda item: len(item[0]))[1]
        best_match = None
        best_length = -1
        for substr, result in self.query_results.items():
            if substr in query and len(substr) > best_length:
                best_match = result
                best_length = len(substr)
        if best_match is not None:
            return best_match
        return MockResult()


def _repo_row() -> dict[str, object]:
    return {
        "id": "repository:r_api_node_boats",
        "name": "api-node-boats",
        "path": "/repos/api-node-boats",
        "local_path": "/repos/api-node-boats",
        "remote_url": "https://github.com/platformcontext/api-node-boats",
        "repo_slug": "platformcontext/api-node-boats",
        "has_remote": True,
    }


def _coverage_row() -> dict[str, object]:
    return {
        "run_id": "run-graph-complete",
        "repo_id": "repository:r_api_node_boats",
        "repo_name": "api-node-boats",
        "repo_path": "/repos/api-node-boats",
        "status": "completed",
        "phase": "completed",
        "finalization_status": "completed",
        "graph_available": True,
        "server_content_available": True,
        "discovered_file_count": 8,
        "graph_recursive_file_count": 8,
        "content_file_count": 8,
        "content_entity_count": 4,
        "root_file_count": 2,
        "root_directory_count": 3,
        "top_level_function_count": 1,
        "class_method_count": 1,
        "total_function_count": 2,
        "class_count": 1,
        "last_error": None,
        "created_at": None,
        "updated_at": None,
        "commit_finished_at": None,
        "finalization_finished_at": None,
    }


def _make_session() -> MockSession:
    runtime_platform = {
        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
        "name": "node10",
        "kind": "ecs",
        "provider": "aws",
        "environment": "prod",
        "workload_instance_id": "workload-instance:r_api_node_boats",
        "workload_environment": "prod",
        "relationship_type": "RUNS_ON",
    }
    provisioned_platform = {
        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
        "name": "node10",
        "kind": "ecs",
        "provider": "aws",
        "environment": "prod",
        "relationship_type": "PROVISIONS_PLATFORM",
    }
    helm_repo = {
        "id": "repository:r_helm123",
        "name": "helm-charts",
        "path": "/repos/helm-charts",
        "local_path": "/repos/helm-charts",
        "remote_url": "https://github.com/platformcontext/helm-charts",
        "repo_slug": "platformcontext/helm-charts",
        "has_remote": True,
    }
    infra_repo = {
        "id": "repository:r_infra123",
        "name": "infra-stack",
        "path": "/repos/infra-stack",
        "local_path": "/repos/infra-stack",
        "remote_url": "https://github.com/platformcontext/infra-stack",
        "repo_slug": "platformcontext/infra-stack",
        "has_remote": True,
    }
    return MockSession(
        {
            "MATCH (r:Repository)-[:CONTAINS*]->(f:File)": MockResult(
                records=[{"file": "main.py", "ext": "py"}]
            ),
            "fn.name IN": MockResult(
                records=[{"name": "main", "file": "main.py", "line": 1}]
            ),
            "RUNS_ON]->(p:Platform)": MockResult(records=[runtime_platform]),
            "PROVISIONS_PLATFORM]->(p:Platform)": MockResult(
                records=[provisioned_platform]
            ),
            "MATCH (r:Repository)-[:DEPLOYS_FROM]->(dep:Repository)": MockResult(
                records=[helm_repo]
            ),
            "MATCH (r:Repository)-[:DISCOVERS_CONFIG_IN]->(cfg:Repository)": MockResult(
                records=[]
            ),
            "MATCH (prov:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(r:Repository)": MockResult(
                records=[infra_repo]
            ),
            "MATCH (r:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(dep:Repository)": MockResult(
                records=[]
            ),
            "SOURCES_FROM": MockResult(
                records=[
                    {
                        "app_name": "api-node-boats",
                        "project": "platformcontext",
                        "namespace": "argocd",
                        "source_path": "argocd/api-node-boats/overlays/prod",
                        "relationship_type": "DEPLOYS_FROM",
                    }
                ]
            ),
            "ArgoCDApplicationSet": MockResult(
                records=[
                    {
                        "app_name": "api-node-boats",
                        "project": "platformcontext",
                        "namespace": "argocd",
                        "source_repos": "https://github.com/platformcontext/helm-charts",
                        "source_paths": "argocd/api-node-boats/overlays/prod",
                        "relationship_type": "DISCOVERS_CONFIG_IN",
                    }
                ]
            ),
            "dep:Repository": MockResult(
                records=[
                    {
                        "id": "repository:r_app123",
                        "name": "payments-service",
                        "path": "/repos/payments-service",
                        "local_path": "/repos/payments-service",
                        "remote_url": "https://github.com/platformcontext/payments-service",
                        "repo_slug": "platformcontext/payments-service",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
            "<-[:RUNS_ON]-(i:WorkloadInstance)": MockResult(
                records=[
                    {
                        "id": "repository:r_app123",
                        "name": "payments-service",
                        "path": "/repos/payments-service",
                        "local_path": "/repos/payments-service",
                        "remote_url": "https://github.com/platformcontext/payments-service",
                        "repo_slug": "platformcontext/payments-service",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
            "type(rel) IN": MockResult(
                records=[
                    {
                        "type": "ROUTES_TO",
                        "from_name": "api-node-boats",
                        "from_kind": "Service",
                        "to_name": "api-node-boats-worker",
                        "to_kind": "Deployment",
                    }
                ]
            ),
        }
    )


def test_build_relationship_summary_returns_platforms_deployment_chain_and_limitations(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: _coverage_row(),
    )
    session = _make_session()

    result = build_relationship_summary(session, _repo_row())

    assert result["coverage"]["completeness_state"] == "complete"
    assert result["platforms"][0]["kind"] == "ecs"
    assert result["deploys_from"]
    assert result["provisioned_by"]
    assert result["iac_relationships"]
    assert result["summary"]
    assert result["deployment_chain"][0]["relationship_type"] in {
        "DEPLOYS_FROM",
        "DISCOVERS_CONFIG_IN",
        "RUNS_ON",
    }
    assert result["limitations"] == []
    assert any("[:REPO_CONTAINS]->(f1:File)-[:CONTAINS]->(n1)" in query for query in session.queries)
    assert not any("[:CONTAINS*]->(f1:File)-[:CONTAINS]->(n1)" in query for query in session.queries)


def test_build_relationship_summary_uses_canonical_provisioning_relationship_name(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: _coverage_row(),
    )
    session = MockSession(
        {
            "MATCH (r:Repository)-[:RUNS_ON]->(p:Platform)": MockResult(records=[]),
            "MATCH (r:Repository)-[:PROVISIONS_PLATFORM]->(p:Platform)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:DEPLOYS_FROM]->(dep:Repository)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:DISCOVERS_CONFIG_IN]->(cfg:Repository)": MockResult(
                records=[]
            ),
            "MATCH (prov:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(r:Repository)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(dep:Repository)": MockResult(
                records=[
                    {
                        "id": "repository:r_app123",
                        "name": "payments-service",
                        "path": "/repos/payments-service",
                        "local_path": "/repos/payments-service",
                        "remote_url": "https://github.com/platformcontext/payments-service",
                        "repo_slug": "platformcontext/payments-service",
                        "has_remote": True,
                    }
                ]
            ),
            "type(rel) IN": MockResult(records=[]),
        }
    )

    result = build_relationship_summary(session, _repo_row())

    assert result["provisions_dependencies_for"][0]["relationship_type"] == (
        "PROVISIONS_DEPENDENCY_FOR"
    )


def test_build_relationship_summary_prefers_canonical_repo_edges_for_service_context(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: _coverage_row(),
    )
    session = MockSession(
        {
            "MATCH (r:Repository)-[:CONTAINS*]->(f:File)": MockResult(records=[]),
            "fn.name IN": MockResult(records=[]),
            "MATCH (r:Repository)-[:RUNS_ON]->(p:Platform)": MockResult(records=[]),
            "MATCH (r:Repository)-[:PROVISIONS_PLATFORM]->(p:Platform)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:DEPLOYS_FROM]->(dep:Repository)": MockResult(
                records=[
                    {
                        "id": "repository:r_helm123",
                        "name": "helm-charts",
                        "path": "/repos/helm-charts",
                        "local_path": "/repos/helm-charts",
                        "remote_url": "https://github.com/platformcontext/helm-charts",
                        "repo_slug": "platformcontext/helm-charts",
                        "has_remote": True,
                    }
                ]
            ),
            "MATCH (r:Repository)-[:DISCOVERS_CONFIG_IN]->(cfg:Repository)": MockResult(
                records=[]
            ),
            "MATCH (prov:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(r:Repository)": MockResult(
                records=[
                    {
                        "id": "repository:r_node10",
                        "name": "terraform-stack-node10",
                        "path": "/repos/terraform-stack-node10",
                        "local_path": "/repos/terraform-stack-node10",
                        "remote_url": "https://github.com/platformcontext/terraform-stack-node10",
                        "repo_slug": "platformcontext/terraform-stack-node10",
                        "has_remote": True,
                    }
                ]
            ),
            "MATCH (r:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(dep:Repository)": MockResult(
                records=[]
            ),
            "type(rel) IN": MockResult(records=[]),
            "MATCH (app:ArgoCDApplication)-[:SOURCES_FROM]->(r:Repository)": MockResult(
                records=[
                    {
                        "app_name": "api-node-boats",
                        "project": "should-not-win",
                        "namespace": "argocd",
                        "source_path": "argocd/api-node-boats/overlays/prod",
                    }
                ]
            ),
            "MATCH (app:ArgoCDApplicationSet)": MockResult(
                records=[
                    {
                        "app_name": "api-node-boats",
                        "project": "should-not-win",
                        "namespace": "argocd",
                        "source_repos": "https://github.com/platformcontext/helm-charts",
                        "source_paths": "argocd/api-node-boats/overlays/prod",
                    }
                ]
            ),
        }
    )

    result = build_relationship_summary(session, _repo_row())

    assert len(result["deploys_from"]) == 1
    assert result["deploys_from"][0]["name"] == "helm-charts"
    assert result["deploys_from"][0]["repo_slug"] == "platformcontext/helm-charts"
    assert result["deploys_from"][0]["relationship_type"] == "DEPLOYS_FROM"
    assert result["discovers_config_in"] == []
    assert len(result["provisioned_by"]) == 1
    assert result["provisioned_by"][0]["name"] == "terraform-stack-node10"
    assert (
        result["provisioned_by"][0]["repo_slug"]
        == "platformcontext/terraform-stack-node10"
    )
    assert result["provisioned_by"][0]["relationship_type"] == "PROVISIONED_BY"
    assert result["deployment_chain"][0]["relationship_type"] == "DEPLOYS_FROM"


def test_build_relationship_summary_reads_direct_repository_runtime_platform_edges(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: _coverage_row(),
    )
    session = MockSession(
        {
            "MATCH (r:Repository)-[:RUNS_ON]->(p:Platform)": MockResult(
                records=[
                    {
                        "id": "platform:ecs:aws:cluster/node10:none:none",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": None,
                    }
                ]
            ),
            "MATCH (r:Repository)-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:PROVISIONS_PLATFORM]->(p:Platform)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:DEPLOYS_FROM]->(dep:Repository)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:DISCOVERS_CONFIG_IN]->(cfg:Repository)": MockResult(
                records=[]
            ),
            "MATCH (prov:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(r:Repository)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(dep:Repository)": MockResult(
                records=[]
            ),
            "type(rel) IN": MockResult(records=[]),
        }
    )

    result = build_relationship_summary(session, _repo_row())

    assert result["platforms"] == [
        {
            "id": "platform:ecs:aws:cluster/node10:none:none",
            "name": "node10",
            "kind": "ecs",
            "provider": "aws",
            "environment": None,
            "relationship_type": "RUNS_ON",
            "source": "runtime",
        }
    ]


def test_build_repository_context_returns_platforms_deployment_chain_and_limitations(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.resolve_repository",
        lambda _session, _repo_id: _repo_row(),
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.repository_graph_counts",
        lambda _session, _repo: {
            "root_file_count": 1,
            "root_directory_count": 2,
            "file_count": 8,
            "top_level_function_count": 1,
            "class_method_count": 1,
            "total_function_count": 2,
            "class_count": 1,
            "module_count": 0,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_infrastructure",
        lambda _session, _repo: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_ecosystem",
        lambda _session, _repo: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: _coverage_row(),
    )
    session = _make_session()

    result = build_repository_context(session, "api-node-boats")

    assert result["coverage"]["completeness_state"] == "complete"
    assert result["platforms"][0]["kind"] == "ecs"
    assert result["deploys_from"]
    assert result["provisioned_by"]
    assert result["iac_relationships"]
    assert result["summary"]
    assert result["deployment_chain"][0]["relationship_type"] in {
        "DEPLOYS_FROM",
        "DISCOVERS_CONFIG_IN",
        "RUNS_ON",
    }
    assert result["limitations"] == ["dns_unknown"]


def test_build_repository_context_extends_limitations_for_dns_and_entrypoints(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.resolve_repository",
        lambda _session, _repo_id: _repo_row(),
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.repository_graph_counts",
        lambda _session, _repo: {
            "root_file_count": 1,
            "root_directory_count": 2,
            "file_count": 8,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "module_count": 0,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_infrastructure",
        lambda _session, _repo: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_ecosystem",
        lambda _session, _repo: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_relationship_summary",
        lambda _session, _repo_ref: {
            "coverage": {
                **_coverage_row(),
                "completeness_state": "complete",
                "limitations": [],
            },
            "platforms": [],
            "deploys_from": [],
            "discovers_config_in": [],
            "provisioned_by": [],
            "provisions_dependencies_for": [],
            "iac_relationships": [],
            "deployment_chain": [],
            "environments": [],
            "summary": {},
            "limitations": [
                "runtime_platform_unknown",
                "deployment_chain_incomplete",
            ],
        },
    )
    session = MockSession(
        {
            "MATCH (r:Repository)-[:CONTAINS*]->(f:File)": MockResult(records=[]),
            "fn.name IN": MockResult(records=[]),
        }
    )

    result = build_repository_context(session, "api-node-boats")

    assert result["limitations"] == [
        "runtime_platform_unknown",
        "deployment_chain_incomplete",
        "dns_unknown",
        "entrypoint_unknown",
    ]


def test_build_relationship_summary_skips_legacy_runtime_query_when_instance_of_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: _coverage_row(),
    )
    session = MockSession(
        {
            "CALL db.relationshipTypes()": MockResult(
                records=[{"relationshipType": "RUNS_ON"}]
            ),
            "MATCH (r:Repository)-[:RUNS_ON]->(p:Platform)": MockResult(
                records=[
                    {
                        "id": "platform:ecs:aws:cluster/node10:none:none",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": None,
                        "workload_instance_id": None,
                        "workload_environment": None,
                    }
                ]
            ),
            "MATCH (r:Repository)-[:PROVISIONS_PLATFORM]->(p:Platform)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:DEPLOYS_FROM]->(dep:Repository)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:DISCOVERS_CONFIG_IN]->(cfg:Repository)": MockResult(
                records=[]
            ),
            "MATCH (prov:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(r:Repository)": MockResult(
                records=[]
            ),
            "MATCH (r:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(dep:Repository)": MockResult(
                records=[]
            ),
            "type(rel) IN": MockResult(records=[]),
        }
    )

    result = build_relationship_summary(session, _repo_row())

    assert result["platforms"] == [
        {
            "id": "platform:ecs:aws:cluster/node10:none:none",
            "name": "node10",
            "kind": "ecs",
            "provider": "aws",
            "environment": None,
            "workload_instance_id": None,
            "workload_environment": None,
            "relationship_type": "RUNS_ON",
            "source": "runtime",
        }
    ]
    assert not any("INSTANCE_OF" in query for query in session.queries)


def test_build_repository_stats_surfaces_platform_and_deployment_counts(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.stats_data.resolve_repository",
        lambda _session, _repo_id: _repo_row(),
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.stats_data.repository_graph_counts",
        lambda _session, _repo: {
            "root_file_count": 1,
            "root_directory_count": 2,
            "file_count": 8,
            "top_level_function_count": 1,
            "class_method_count": 1,
            "total_function_count": 2,
            "class_count": 1,
            "module_count": 0,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: _coverage_row(),
    )
    session = _make_session()

    result = build_repository_stats(session, "api-node-boats")

    assert result["stats"]["platform_count"] >= 1
    assert result["stats"]["deployment_source_count"] >= 1
    assert "limitations" in result["stats"]
