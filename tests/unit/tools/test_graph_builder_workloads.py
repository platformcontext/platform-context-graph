"""Unit tests for workload graph materialization helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.tools.graph_builder_workloads import materialize_workloads


class _FakeResult:
    def __init__(self, *, records=None):
        self._records = records or []

    def data(self):
        return self._records


def test_materialize_workloads_creates_workload_instance_and_deployment_source() -> None:
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    recorded_calls: list[tuple[str, dict[str, object]]] = []

    def run(query: str, **kwargs: object) -> _FakeResult:
        recorded_calls.append((query, kwargs))
        if "RETURN repo.id as repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_5c50d0d3",
                        "repo_name": "api-node-search",
                        "deployment_repo_id": "repository:r_20871f7f",
                        "deployment_repo_name": "helm-charts",
                        "resource_kinds": ["Deployment"],
                        "source_roots": ["argocd/api-node-search/"],
                    }
                ]
            )
        if "RETURN deployment_repo.id as deployment_repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "deployment_repo_id": "repository:r_20871f7f",
                        "relative_path": "argocd/api-node-search/overlays/bg-qa/config.yaml",
                    }
                ]
            )
        return _FakeResult()

    session.run.side_effect = run
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session))
    )

    stats = materialize_workloads(builder, info_logger_fn=lambda *_args, **_kwargs: None)

    workload_merge = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (w:Workload {id: $workload_id})" in query
    )
    instance_merge = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (i:WorkloadInstance {id: $instance_id})" in query
    )
    deployment_edge = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (i)-[rel:DEPLOYMENT_SOURCE]->(deployment_repo)" in query
    )

    assert workload_merge == {
        "repo_id": "repository:r_5c50d0d3",
        "repo_name": "api-node-search",
        "workload_id": "workload:api-node-search",
        "workload_kind": "service",
        "workload_name": "api-node-search",
    }
    assert instance_merge == {
        "environment": "bg-qa",
        "instance_id": "workload-instance:api-node-search:bg-qa",
        "repo_id": "repository:r_5c50d0d3",
        "workload_id": "workload:api-node-search",
        "workload_kind": "service",
        "workload_name": "api-node-search",
    }
    assert deployment_edge == {
        "deployment_repo_id": "repository:r_20871f7f",
        "environment": "bg-qa",
        "instance_id": "workload-instance:api-node-search:bg-qa",
        "workload_name": "api-node-search",
    }
    assert stats == {"workloads": 1, "instances": 1, "deployment_sources": 1}


def test_materialize_workloads_creates_runtime_dependency_edges(tmp_path) -> None:
    repo_path = tmp_path / "api-node-search"
    repo_path.mkdir()
    entrypoint = repo_path / "api-node-search.ts"
    entrypoint.write_text(
        """\
const main = async ({ api }) => {
  await api.start({
    services: [pkg.name, `/api/${pkg.name}`, 'opensearch/products', 'elasticache', 'api-node-forex'],
  });
};
""",
        encoding="utf-8",
    )

    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    recorded_calls: list[tuple[str, dict[str, object]]] = []

    def run(query: str, **kwargs: object) -> _FakeResult:
        recorded_calls.append((query, kwargs))
        if "RETURN repo.id as repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_5c50d0d3",
                        "repo_name": "api-node-search",
                        "deployment_repo_id": None,
                        "deployment_repo_name": None,
                        "resource_kinds": ["Deployment"],
                        "source_roots": [],
                    }
                ]
            )
        if "RETURN f.path as path" in query:
            return _FakeResult(
                records=[
                    {
                        "path": str(entrypoint),
                        "relative_path": "api-node-search.ts",
                    }
                ]
            )
        if "RETURN target_repo.id as repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_dep12345",
                        "repo_name": "api-node-forex",
                    }
                ]
            )
        return _FakeResult()

    session.run.side_effect = run
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session))
    )

    materialize_workloads(builder, info_logger_fn=lambda *_args, **_kwargs: None)

    repo_dependency = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (source_repo)-[rel:DEPENDS_ON]->(target_repo)" in query
    )
    workload_dependency = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (source)-[rel:DEPENDS_ON]->(target)" in query
    )

    assert repo_dependency == {
        "dependency_name": "api-node-forex",
        "repo_id": "repository:r_5c50d0d3",
        "target_repo_id": "repository:r_dep12345",
    }
    assert workload_dependency == {
        "dependency_name": "api-node-forex",
        "target_repo_id": "repository:r_dep12345",
        "target_workload_id": "workload:api-node-forex",
        "workload_id": "workload:api-node-search",
    }
