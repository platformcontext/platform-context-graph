from __future__ import annotations

import re
from unittest.mock import MagicMock

from platform_context_graph.query.repositories import (
    _canonical_repository_id,
    get_repository_context,
    get_repository_stats,
)
from platform_context_graph.query.repositories.common import resolve_repository
from platform_context_graph.query.repositories.context_data import _fetch_infrastructure
from platform_context_graph.query.repositories.graph_counts import (
    repository_graph_counts,
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

    def mock_run(query, *args, **kwargs):
        for token in ("dep:Repository", "prov:Repository", "SOURCES_FROM"):
            if token in query:
                token_matches = [
                    (substr, result)
                    for substr, result in query_results.items()
                    if substr in query and token in substr
                ]
                if token_matches:
                    return max(token_matches, key=lambda item: len(item[0]))[1]
        best_match = None
        best_length = -1
        for substr, result in query_results.items():
            if substr in query and len(substr) > best_length:
                best_match = result
                best_length = len(substr)
        if best_match is not None:
            return best_match
        return MockResult()

    session.run = mock_run
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    driver.session.return_value = session
    db.get_driver.return_value = driver
    return db


class FinderLike:
    def __init__(self, db_manager):
        self.db_manager = db_manager


def test_repository_graph_counts_excludes_class_methods_from_top_level_count() -> None:
    """Top-level function counts must exclude functions also contained by classes."""

    recorded_query: dict[str, str] = {}

    class RecordingSession:
        def run(self, query, **kwargs):
            del kwargs
            recorded_query["query"] = query
            return MockResult(
                single_record=MockRecord(
                    {
                        "root_file_count": 2,
                        "root_directory_count": 8,
                        "file_count": 6356,
                        "top_level_function_count": 17908,
                        "class_method_count": 22363,
                        "total_function_count": 40271,
                        "class_count": 3373,
                        "module_count": 0,
                    }
                )
            )

    counts = repository_graph_counts(
        RecordingSession(),
        {
            "id": "repository:r_221a72af",
            "path": "/repos/boatgest-php-youboat",
            "local_path": "/repos/boatgest-php-youboat",
        },
    )

    assert counts["top_level_function_count"] == 17908
    assert counts["class_method_count"] == 22363
    assert counts["total_function_count"] == 40271
    assert "CALL (r) {" in recorded_query["query"]
    assert "WITH r" not in recorded_query["query"]
    assert "NOT EXISTS {" in recorded_query["query"]
    assert "(:Class)-[:CONTAINS]->(fn)" in recorded_query["query"]
    assert (
        "coalesce(r[$local_path_key], r.path) = $repo_path" in recorded_query["query"]
    )
    assert "[:IMPORTS]->(module:Module)" not in recorded_query["query"]
    assert "type(rel) = $imports_rel_type" in recorded_query["query"]


def test_resolve_repository_uses_dynamic_optional_repository_keys() -> None:
    """Repository lookup should avoid sparse-key warnings for optional metadata."""

    recorded: dict[str, object] = {}

    class RecordingSession:
        def run(self, query, **kwargs):
            recorded["query"] = query
            recorded["kwargs"] = kwargs
            return MockResult(
                records=[
                    {
                        "id": "repository:r_1234",
                        "name": "my-api",
                        "path": "/repos/my-api",
                        "local_path": "/repos/my-api",
                        "remote_url": "https://github.com/platformcontext/my-api",
                        "repo_slug": "platformcontext/my-api",
                        "has_remote": True,
                    }
                ]
            )

    resolved = resolve_repository(RecordingSession(), "repository:r_1234")

    assert resolved is not None
    assert "r[$remote_url_key] as remote_url" in recorded["query"]
    assert "r[$repo_slug_key] as repo_slug" in recorded["query"]
    assert "coalesce(r[$has_remote_key], false) as has_remote" in recorded["query"]
    assert recorded["kwargs"] == {
        "local_path_key": "local_path",
        "remote_url_key": "remote_url",
        "repo_slug_key": "repo_slug",
        "has_remote_key": "has_remote",
    }


def test_fetch_infrastructure_uses_dynamic_optional_property_keys() -> None:
    """Repository context infra queries should avoid sparse-key warnings."""

    recorded_queries: list[tuple[str, dict[str, object]]] = []

    class RecordingSession:
        def run(self, query, **kwargs):
            recorded_queries.append((query, kwargs))
            return MockResult(records=[])

    _fetch_infrastructure(
        RecordingSession(),
        {
            "id": "repository:r_1234",
            "path": "/repos/my-api",
            "local_path": "/repos/my-api",
        },
    )

    terraform_variable_query = next(
        query
        for query, _ in recorded_queries
        if "MATCH (r:Repository)-[:CONTAINS*]->(f:File)" in query
        and "TerraformVariable" in query
    )
    argocd_application_query = next(
        query for query, _ in recorded_queries if "ArgoCDApplication" in query
    )
    argocd_appset_query = next(
        query for query, _ in recorded_queries if "ArgoCDApplicationSet" in query
    )
    _, shared_kwargs = recorded_queries[0]

    assert "n[$default_key] as default" in terraform_variable_query
    assert "n[$project_key] as project" in argocd_application_query
    assert "n[$dest_namespace_key] as dest_namespace" in argocd_application_query
    assert "n[$generators_key] as generators" in argocd_appset_query
    assert shared_kwargs["default_key"] == "default"
    assert shared_kwargs["project_key"] == "project"
    assert shared_kwargs["dest_namespace_key"] == "dest_namespace"
    assert shared_kwargs["generators_key"] == "generators"


def test_get_repository_context_returns_current_context_shape(monkeypatch):
    deps_record = MockRecord({"dependencies": []})
    dependents_record = MockRecord({"dependents": []})
    canonical_repo_id = _canonical_repository_id(
        remote_url="https://github.com/platformcontext/my-api",
        local_path="/repos/my-api",
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: {
            "run_id": "run-complete",
            "repo_id": canonical_repo_id,
            "repo_name": "my-api",
            "repo_path": "/repos/my-api",
            "status": "completed",
            "phase": "completed",
            "finalization_status": "completed",
            "graph_available": True,
            "server_content_available": True,
            "discovered_file_count": 3,
            "graph_recursive_file_count": 3,
            "content_file_count": 3,
            "content_entity_count": 0,
            "root_file_count": 1,
            "root_directory_count": 2,
            "top_level_function_count": 7,
            "class_method_count": 3,
            "total_function_count": 10,
            "class_count": 3,
            "last_error": None,
            "updated_at": None,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_infrastructure",
        lambda _session, _repo: {},
    )

    db = make_mock_db(
        {
            "RETURN r.id as id, r.name as name, r.path as path": MockResult(
                records=[
                    {
                        "id": canonical_repo_id,
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
            "RETURN root_file_count,": MockResult(
                single_record=MockRecord(
                    {
                        "root_file_count": 1,
                        "root_directory_count": 2,
                        "file_count": 3,
                        "top_level_function_count": 7,
                        "class_method_count": 3,
                        "total_function_count": 10,
                        "class_count": 3,
                        "module_count": 2,
                    }
                )
            ),
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
            "Tier": MockResult(single_record=None),
            "DEPENDS_ON]->(dep": MockResult(single_record=deps_record),
            "DEPENDS_ON]-(dep": MockResult(single_record=dependents_record),
            "RUNS_ON]->(p:Platform)": MockResult(
                records=[
                    {
                        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": "prod",
                        "workload_instance_id": "workload-instance:r_primary123",
                        "workload_environment": "prod",
                        "relationship_type": "RUNS_ON",
                    }
                ]
            ),
            "<-[:PROVISIONS_PLATFORM]-(prov:Repository)": MockResult(
                records=[
                    {
                        "id": "repository:r_infra123",
                        "name": "infra-stack",
                        "path": "/repos/infra-stack",
                        "local_path": "/repos/infra-stack",
                        "remote_url": "https://github.com/platformcontext/infra-stack",
                        "repo_slug": "platformcontext/infra-stack",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
            "PROVISIONS_PLATFORM]->(p:Platform)": MockResult(
                records=[
                    {
                        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": "prod",
                        "relationship_type": "PROVISIONS_PLATFORM",
                    }
                ]
            ),
            "SOURCES_FROM": MockResult(
                records=[
                    {
                        "app_name": "payments-api",
                        "project": "platformcontext",
                        "namespace": "argocd",
                        "source_path": "argocd/payments-api/overlays/prod",
                        "relationship_type": "DEPLOYS_FROM",
                    }
                ]
            ),
            "ArgoCDApplicationSet": MockResult(
                records=[
                    {
                        "app_name": "payments-api",
                        "project": "platformcontext",
                        "namespace": "argocd",
                        "source_repos": "https://github.com/platformcontext/helm-charts",
                        "source_paths": "argocd/payments-api/overlays/prod",
                        "relationship_type": "DISCOVERS_CONFIG_IN",
                    }
                ]
            ),
            "dep:Repository": MockResult(
                records=[
                    {
                        "id": "repository:r_app123",
                        "name": "payments-api-worker",
                        "path": "/repos/payments-api-worker",
                        "local_path": "/repos/payments-api-worker",
                        "remote_url": "https://github.com/platformcontext/payments-api-worker",
                        "repo_slug": "platformcontext/payments-api-worker",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
            "<-[:RUNS_ON]-(i:WorkloadInstance)": MockResult(
                records=[
                    {
                        "id": "repository:r_app123",
                        "name": "payments-api-worker",
                        "path": "/repos/payments-api-worker",
                        "local_path": "/repos/payments-api-worker",
                        "remote_url": "https://github.com/platformcontext/payments-api-worker",
                        "repo_slug": "platformcontext/payments-api-worker",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
        }
    )

    result = get_repository_context(db, repo_id=canonical_repo_id)

    assert result["repository"]["name"] == "my-api"
    assert result["repository"]["id"] == canonical_repo_id
    assert result["repository"]["local_path"] == "/repos/my-api"
    assert result["repository"]["repo_slug"] == "platformcontext/my-api"
    assert (
        result["repository"]["remote_url"]
        == "https://github.com/platformcontext/my-api"
    )
    assert result["repository"]["file_count"] == 3
    assert result["repository"]["root_file_count"] == 1
    assert result["repository"]["root_directory_count"] == 2
    assert result["repository"]["graph_available"] is True
    assert result["repository"]["server_content_available"] is True
    assert result["repository"]["active_run_id"] == "run-complete"
    assert result["repository"]["index_status"] == "completed"
    assert result["platforms"]
    assert result["deploys_from"]
    assert result["discovers_config_in"]
    assert result["provisioned_by"]
    assert result["provisions_dependencies_for"]
    assert result["iac_relationships"] == []
    assert result["deployment_chain"]
    assert result["environments"] == ["prod"]
    assert result["summary"]["platform_count"] == 1
    assert result["summary"]["environment_count"] == 1
    assert result["limitations"] == []
    assert result["code"]["functions"] == 10
    assert result["code"]["top_level_functions"] == 7
    assert result["code"]["class_methods"] == 3
    assert result["code"]["classes"] == 3
    assert "python" in result["code"]["languages"]
    assert result["coverage"]["completeness_state"] == "complete"
    assert result["infrastructure"] == {}
    assert result["relationships"] == []
    assert result["ecosystem"] is None


def test_get_repository_context_surfaces_partial_coverage_gaps(monkeypatch) -> None:
    """Repo context should surface recursive coverage gaps instead of implying absence."""

    canonical_repo_id = _canonical_repository_id(
        remote_url="https://github.com/platformcontext/api-node-boats",
        local_path="/repos/api-node-boats",
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: {
            "run_id": "run-graph-partial",
            "repo_id": canonical_repo_id,
            "repo_name": "api-node-boats",
            "repo_path": "/repos/api-node-boats",
            "status": "completed",
            "phase": "completed",
            "finalization_status": "completed",
            "graph_available": True,
            "server_content_available": False,
            "discovered_file_count": 196,
            "graph_recursive_file_count": 12,
            "content_file_count": 0,
            "content_entity_count": 0,
            "root_file_count": 12,
            "root_directory_count": 5,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "last_error": None,
            "updated_at": None,
        },
    )

    db = make_mock_db(
        {
            "RETURN r.id as id, r.name as name, r.path as path": MockResult(
                records=[
                    {
                        "id": canonical_repo_id,
                        "name": "api-node-boats",
                        "path": "/repos/api-node-boats",
                        "local_path": "/repos/api-node-boats",
                        "remote_url": "https://github.com/platformcontext/api-node-boats",
                        "repo_slug": "platformcontext/api-node-boats",
                        "has_remote": True,
                    }
                ]
            ),
            "split(f.name": MockResult(
                records=[
                    {"file": "tsconfig.json", "ext": "json"},
                    {"file": "specs/index.yaml", "ext": "yaml"},
                ]
            ),
            "RETURN root_file_count,": MockResult(
                single_record=MockRecord(
                    {
                        "root_file_count": 12,
                        "root_directory_count": 5,
                        "file_count": 12,
                        "top_level_function_count": 0,
                        "class_method_count": 0,
                        "total_function_count": 0,
                        "class_count": 0,
                        "module_count": 0,
                    }
                )
            ),
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
            "Tier": MockResult(single_record=None),
            "DEPENDS_ON]->(dep": MockResult(
                single_record=MockRecord({"dependencies": []})
            ),
            "DEPENDS_ON]-(dep": MockResult(
                single_record=MockRecord({"dependents": []})
            ),
            "RUNS_ON]->(p:Platform)": MockResult(
                records=[
                    {
                        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": "prod",
                        "workload_instance_id": "workload-instance:r_primary123",
                        "workload_environment": "prod",
                        "relationship_type": "RUNS_ON",
                    }
                ]
            ),
            "PROVISIONS_PLATFORM]->(p:Platform)": MockResult(
                records=[
                    {
                        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": "prod",
                        "relationship_type": "PROVISIONS_PLATFORM",
                    }
                ]
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
                        "name": "api-node-boats-worker",
                        "path": "/repos/api-node-boats-worker",
                        "local_path": "/repos/api-node-boats-worker",
                        "remote_url": "https://github.com/platformcontext/api-node-boats-worker",
                        "repo_slug": "platformcontext/api-node-boats-worker",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
            "<-[:PROVISIONS_PLATFORM]-(prov:Repository)": MockResult(
                records=[
                    {
                        "id": "repository:r_infra123",
                        "name": "infra-stack",
                        "path": "/repos/infra-stack",
                        "local_path": "/repos/infra-stack",
                        "remote_url": "https://github.com/platformcontext/infra-stack",
                        "repo_slug": "platformcontext/infra-stack",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
            "<-[:RUNS_ON]-(i:WorkloadInstance)": MockResult(
                records=[
                    {
                        "id": "repository:r_app123",
                        "name": "api-node-boats-worker",
                        "path": "/repos/api-node-boats-worker",
                        "local_path": "/repos/api-node-boats-worker",
                        "remote_url": "https://github.com/platformcontext/api-node-boats-worker",
                        "repo_slug": "platformcontext/api-node-boats-worker",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
        }
    )

    result = get_repository_context(db, repo_id=canonical_repo_id)

    assert result["coverage"]["completeness_state"] == "graph_partial"
    assert result["coverage"]["graph_gap_count"] == 184
    assert result["coverage"]["content_gap_count"] == 12
    assert result["repository"]["discovered_file_count"] == 196
    assert result["repository"]["graph_recursive_file_count"] == 12
    assert result["repository"]["content_file_count"] == 0
    assert result["repository"]["completeness_state"] == "graph_partial"
    assert result["limitations"] == ["graph_partial", "content_partial"]


def test_get_repository_stats_supports_repo_and_overall_modes(monkeypatch):
    canonical_repo_id = _canonical_repository_id(
        remote_url="https://github.com/platformcontext/my-api",
        local_path="/repos/my-api",
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: {
            "run_id": "run-complete",
            "repo_id": canonical_repo_id,
            "repo_name": "my-api",
            "repo_path": "/repos/my-api",
            "status": "completed",
            "phase": "completed",
            "finalization_status": "completed",
            "graph_available": True,
            "server_content_available": True,
            "discovered_file_count": 3,
            "graph_recursive_file_count": 3,
            "content_file_count": 3,
            "content_entity_count": 0,
            "root_file_count": 2,
            "root_directory_count": 4,
            "top_level_function_count": 5,
            "class_method_count": 2,
            "total_function_count": 7,
            "class_count": 2,
            "last_error": None,
            "updated_at": None,
        },
    )
    db = make_mock_db(
        {
            "RETURN r.id as id, r.name as name, r.path as path": MockResult(
                records=[
                    {
                        "id": canonical_repo_id,
                        "name": "my-api",
                        "path": "/repos/my-api",
                        "local_path": "/repos/my-api",
                        "remote_url": "https://github.com/platformcontext/my-api",
                        "repo_slug": "platformcontext/my-api",
                        "has_remote": True,
                    }
                ]
            ),
            "RETURN root_file_count,": MockResult(
                single_record=MockRecord(
                    {
                        "root_file_count": 2,
                        "root_directory_count": 4,
                        "file_count": 3,
                        "top_level_function_count": 5,
                        "class_method_count": 2,
                        "total_function_count": 7,
                        "class_count": 2,
                        "module_count": 5,
                    }
                )
            ),
            "MATCH (r:Repository) RETURN count(r) as c": MockResult(
                single_record=MockRecord({"c": 4})
            ),
            "MATCH (f:File) RETURN count(f) as c": MockResult(
                single_record=MockRecord({"c": 20})
            ),
            "MATCH (func:Function) RETURN count(func) as c": MockResult(
                single_record=MockRecord({"c": 40})
            ),
            "MATCH (cls:Class) RETURN count(cls) as c": MockResult(
                single_record=MockRecord({"c": 8})
            ),
            "MATCH (m:Module) RETURN count(m) as c": MockResult(
                single_record=MockRecord({"c": 12})
            ),
            "RUNS_ON]->(p:Platform)": MockResult(
                records=[
                    {
                        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": "prod",
                        "workload_instance_id": "workload-instance:r_primary123",
                        "workload_environment": "prod",
                        "relationship_type": "RUNS_ON",
                    }
                ]
            ),
            "<-[:PROVISIONS_PLATFORM]-(prov:Repository)": MockResult(
                records=[
                    {
                        "id": "repository:r_infra123",
                        "name": "infra-stack",
                        "path": "/repos/infra-stack",
                        "local_path": "/repos/infra-stack",
                        "remote_url": "https://github.com/platformcontext/infra-stack",
                        "repo_slug": "platformcontext/infra-stack",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
            "PROVISIONS_PLATFORM]->(p:Platform)": MockResult(
                records=[
                    {
                        "id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                        "name": "node10",
                        "kind": "ecs",
                        "provider": "aws",
                        "environment": "prod",
                        "relationship_type": "PROVISIONS_PLATFORM",
                    }
                ]
            ),
            "SOURCES_FROM": MockResult(
                records=[
                    {
                        "app_name": "my-api",
                        "project": "platformcontext",
                        "namespace": "argocd",
                        "source_path": "argocd/my-api/overlays/prod",
                        "relationship_type": "DEPLOYS_FROM",
                    }
                ]
            ),
            "ArgoCDApplicationSet": MockResult(
                records=[
                    {
                        "app_name": "my-api",
                        "project": "platformcontext",
                        "namespace": "argocd",
                        "source_repos": "https://github.com/platformcontext/helm-charts",
                        "source_paths": "argocd/my-api/overlays/prod",
                        "relationship_type": "DISCOVERS_CONFIG_IN",
                    }
                ]
            ),
            "dep:Repository": MockResult(
                records=[
                    {
                        "id": "repository:r_app123",
                        "name": "my-api-worker",
                        "path": "/repos/my-api-worker",
                        "local_path": "/repos/my-api-worker",
                        "remote_url": "https://github.com/platformcontext/my-api-worker",
                        "repo_slug": "platformcontext/my-api-worker",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
            "<-[:RUNS_ON]-(i:WorkloadInstance)": MockResult(
                records=[
                    {
                        "id": "repository:r_app123",
                        "name": "my-api-worker",
                        "path": "/repos/my-api-worker",
                        "local_path": "/repos/my-api-worker",
                        "remote_url": "https://github.com/platformcontext/my-api-worker",
                        "repo_slug": "platformcontext/my-api-worker",
                        "has_remote": True,
                        "platform_id": "platform:ecs:aws:cluster/node10:prod:us-east-1",
                    }
                ]
            ),
        }
    )
    finder = FinderLike(db)

    scoped = get_repository_stats(finder, repo_id=canonical_repo_id)
    overall = get_repository_stats(finder, repo_id=None)

    assert scoped["success"] is True
    assert scoped["repository"]["id"] == canonical_repo_id
    assert scoped["repository"]["local_path"] == "/repos/my-api"
    assert scoped["stats"] == {
        "files": 3,
        "root_files": 2,
        "root_directories": 4,
        "functions": 7,
        "top_level_functions": 5,
        "class_methods": 2,
        "classes": 2,
        "modules": 5,
        "platform_count": 1,
        "deployment_source_count": 1,
        "environment_count": 1,
        "limitations": [],
    }
    assert scoped["coverage"]["completeness_state"] == "complete"
    assert overall["success"] is True
    assert overall["stats"]["repositories"] == 4
    assert overall["stats"]["files"] == 20


def test_fetch_infrastructure_queries_reuse_matched_node_alias():
    class RecordingSession:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def run(self, query, **kwargs):
            self.queries.append(query)
            return MockResult(records=[])

    session = RecordingSession()

    assert (
        _fetch_infrastructure(
            session,
            {
                "id": "repository:r_ab12cd34",
                "path": "/repos/my-api",
                "local_path": "/repos/my-api",
            },
        )
        == {}
    )
    assert session.queries

    infra_label_queries = [
        query for query in session.queries if "-[:CONTAINS]->(" in query
    ]
    assert infra_label_queries

    for query in infra_label_queries:
        alias_match = re.search(r"-\[:CONTAINS\]->\((\w+):", query)
        assert alias_match is not None

        node_alias = alias_match.group(1)
        return_block = query.split("RETURN", 1)[1]
        return_aliases = set(re.findall(r"\b([A-Za-z_]\w*)\.", return_block))

        assert return_aliases <= {node_alias, "f"}


def test_get_repository_context_scopes_follow_up_queries_to_the_resolved_repository(
    monkeypatch,
):
    primary_repo = {
        "id": "repository:r_primary123",
        "name": "payments-api",
        "path": "/repos/payments-api",
        "local_path": "/repos/payments-api",
        "remote_url": "https://github.com/platformcontext/payments-api",
        "repo_slug": "platformcontext/payments-api",
        "has_remote": True,
    }
    sibling_repo = {
        "id": "repository:r_worker456",
        "name": "payments-api-worker",
        "path": "/repos/payments-api-worker",
        "local_path": "/repos/payments-api-worker",
        "remote_url": "https://github.com/platformcontext/payments-api-worker",
        "repo_slug": "platformcontext/payments-api-worker",
        "has_remote": True,
    }
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.relationship_summary.get_runtime_repository_coverage",
        lambda **_kwargs: {
            "run_id": "run-complete",
            "repo_id": "repository:r_primary123",
            "repo_name": "payments-api",
            "repo_path": "/repos/payments-api",
            "status": "completed",
            "phase": "completed",
            "finalization_status": "completed",
            "graph_available": True,
            "server_content_available": True,
            "discovered_file_count": 2,
            "graph_recursive_file_count": 2,
            "content_file_count": 2,
            "content_entity_count": 0,
            "root_file_count": 1,
            "root_directory_count": 1,
            "top_level_function_count": 1,
            "class_method_count": 0,
            "total_function_count": 1,
            "class_count": 0,
            "last_error": None,
            "updated_at": None,
        },
    )

    class ContextSession:
        def run(self, query, **kwargs):
            if "MATCH (r:Repository)" in query and "RETURN r.id as id" in query:
                return MockResult(records=[primary_repo, sibling_repo])
            if "split(f.name" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(records=[{"file": "payments.py", "ext": "py"}])
                return MockResult(
                    records=[
                        {"file": "payments.py", "ext": "py"},
                        {"file": "worker.py", "ext": "py"},
                    ]
                )
            if "RETURN root_file_count," in query:
                if "r.id = $repo_id" in query:
                    return MockResult(
                        single_record=MockRecord(
                            {
                                "root_file_count": 1,
                                "root_directory_count": 1,
                                "file_count": 1,
                                "top_level_function_count": 1,
                                "class_method_count": 0,
                                "total_function_count": 1,
                                "class_count": 0,
                                "module_count": 0,
                            }
                        )
                    )
                return MockResult(
                    single_record=MockRecord(
                        {
                            "root_file_count": 2,
                            "root_directory_count": 2,
                            "file_count": 2,
                            "top_level_function_count": 2,
                            "class_method_count": 0,
                            "total_function_count": 2,
                            "class_count": 0,
                            "module_count": 0,
                        }
                    )
                )
            if "fn.name IN" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(
                        records=[{"name": "main", "file": "payments.py", "line": 1}]
                    )
                return MockResult(
                    records=[
                        {"name": "main", "file": "payments.py", "line": 1},
                        {"name": "main", "file": "worker.py", "line": 1},
                    ]
                )
            if "type(rel) IN" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(records=[])
                return MockResult(
                    records=[
                        {
                            "type": "ROUTES_TO",
                            "from_name": "payments-api",
                            "from_kind": "Service",
                            "to_name": "payments-api-worker",
                            "to_kind": "Workload",
                        }
                    ]
                )
            if "K8sResource" in query:
                if "r.id = $repo_id" in query:
                    return MockResult(records=[])
                return MockResult(
                    records=[
                        {
                            "name": "payments-api-worker",
                            "kind": "Deployment",
                            "namespace": "payments",
                        }
                    ]
                )
            if "TerraformResource" in query:
                return MockResult(records=[])
            if "TerraformModule" in query:
                return MockResult(records=[])
            if "TerraformVariable" in query:
                return MockResult(records=[])
            if "TerraformOutput" in query:
                return MockResult(records=[])
            if "ArgoCDApplication" in query:
                return MockResult(records=[])
            if "ArgoCDApplicationSet" in query:
                return MockResult(records=[])
            if "CrossplaneXRD" in query:
                return MockResult(records=[])
            if "CrossplaneComposition" in query:
                return MockResult(records=[])
            if "CrossplaneClaim" in query:
                return MockResult(records=[])
            if "HelmChart" in query:
                return MockResult(records=[])
            if "HelmValues" in query:
                return MockResult(records=[])
            if "KustomizeOverlay" in query:
                return MockResult(records=[])
            if "TerragruntConfig" in query:
                return MockResult(records=[])
            if "Tier" in query:
                return MockResult(single_record=None)
            if "DEPENDS_ON]->(dep" in query:
                return MockResult(single_record=MockRecord({"dependencies": []}))
            if "DEPENDS_ON]-(dep" in query:
                return MockResult(single_record=MockRecord({"dependents": []}))
            return MockResult(records=[])

    session = ContextSession()
    db = MagicMock()
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    driver.session.return_value.__exit__.return_value = False
    db.get_driver.return_value = driver

    result = get_repository_context(db, repo_id="repository:r_primary123")

    assert result["repository"]["name"] == "payments-api"
    assert result["repository"]["file_count"] == 1
    assert result["repository"]["root_file_count"] == 1
    assert result["repository"]["root_directory_count"] == 1
    assert result["code"]["functions"] == 1
    assert result["code"]["top_level_functions"] == 1
    assert result["code"]["class_methods"] == 0
    assert result["code"]["entry_points"] == [
        {"name": "main", "file": "payments.py", "line": 1}
    ]
    assert result["relationships"] == []
    assert result["infrastructure"] == {}
