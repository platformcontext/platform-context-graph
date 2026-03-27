"""Unit tests for workload graph materialization helpers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.tools.graph_builder_platforms import (
    infer_gitops_platform_id,
    infer_gitops_platform_kind,
    infer_infrastructure_platform_descriptor,
)
from platform_context_graph.tools.graph_builder_workloads import materialize_workloads


class _FakeResult:
    def __init__(self, *, records=None):
        self._records = records or []

    def data(self):
        return self._records


def test_materialize_workloads_creates_workload_instance_and_deployment_source() -> (
    None
):
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

    stats = materialize_workloads(
        builder, info_logger_fn=lambda *_args, **_kwargs: None
    )

    candidate_query = next(
        query
        for query, _kwargs in recorded_calls
        if "RETURN repo.id as repo_id" in query
    )

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
    assert (
        "OPTIONAL MATCH (app)-[source_rel]->(deployment_repo:Repository)"
        in candidate_query
    )
    assert "type(source_rel) = 'SOURCES_FROM'" in candidate_query
    assert "[:SOURCES_FROM]" not in candidate_query
    assert "app[$source_roots_key]" in candidate_query
    assert "app.source_roots" not in candidate_query
    assert "app.source_path" not in candidate_query
    assert "app.source_paths" not in candidate_query
    assert stats == {"workloads": 1, "instances": 1, "deployment_sources": 1}


def test_materialize_workloads_creates_runtime_platform_relationships() -> None:
    """Workload instances should gain a platform node and RUNS_ON edge."""

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

    materialize_workloads(builder, info_logger_fn=lambda *_args, **_kwargs: None)

    platform_merge = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (p:Platform {id: $platform_id})" in query
        and "RUNS_ON" in query
    )
    runs_on_edge = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (i)-[rel:RUNS_ON]->(p)" in query
    )

    assert platform_merge == {
        "environment": "bg-qa",
        "platform_id": "platform:kubernetes:none:bg-qa:bg-qa:none",
        "platform_kind": "kubernetes",
        "platform_locator": None,
        "platform_name": "bg-qa",
        "platform_provider": None,
        "platform_region": None,
        "instance_id": "workload-instance:api-node-search:bg-qa",
    }
    assert runs_on_edge["environment"] == "bg-qa"
    assert runs_on_edge["instance_id"] == "workload-instance:api-node-search:bg-qa"
    assert runs_on_edge["platform_id"] == "platform:kubernetes:none:bg-qa:bg-qa:none"


def test_materialize_workloads_creates_infrastructure_platform_relationships(
    tmp_path,
) -> None:
    """Terraform platform signals should create PROVISIONS_PLATFORM edges."""

    repo_path = tmp_path / "terraform-stack-ecs"
    repo_path.mkdir()

    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    recorded_calls: list[tuple[str, dict[str, object]]] = []

    def run(query: str, **kwargs: object) -> _FakeResult:
        recorded_calls.append((query, kwargs))
        if "TerraformDataSource" not in query and "RETURN repo.id as repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_9a1b2c3d",
                        "repo_name": "terraform-stack-ecs",
                        "deployment_repo_id": None,
                        "deployment_repo_name": None,
                        "resource_kinds": [],
                        "source_roots": [],
                    }
                ]
            )
        if "RETURN f.path as path" in query:
            return _FakeResult(records=[])
        if "TerraformDataSource" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_9a1b2c3d",
                        "repo_name": "terraform-stack-ecs",
                        "data_types": [],
                        "data_names": [],
                        "module_sources": [],
                        "module_names": [],
                        "resource_types": ["aws_ecs_cluster"],
                        "resource_names": ["node10"],
                    }
                ]
            )
        return _FakeResult()

    session.run.side_effect = run
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session))
    )

    materialize_workloads(builder, info_logger_fn=lambda *_args, **_kwargs: None)

    platform_merge = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (p:Platform {id: $platform_id})" in query
        and "PROVISIONS_PLATFORM" in query
    )
    provisions_edge = next(
        kwargs
        for query, kwargs in recorded_calls
        if "MERGE (repo)-[rel:PROVISIONS_PLATFORM]->(p)" in query
    )

    assert platform_merge == {
        "platform_environment": None,
        "platform_id": "platform:ecs:aws:cluster/node10:none:none",
        "platform_kind": "ecs",
        "platform_locator": "cluster/node10",
        "platform_name": "node10",
        "platform_provider": "aws",
        "platform_region": None,
        "repo_id": "repository:r_9a1b2c3d",
    }
    assert provisions_edge["platform_id"] == "platform:ecs:aws:cluster/node10:none:none"
    assert provisions_edge["repo_id"] == "repository:r_9a1b2c3d"


def test_infer_infrastructure_platform_descriptor_returns_canonical_cluster_locator() -> (
    None
):
    """Explicit cluster resources should yield canonical platform ids."""

    descriptor = infer_infrastructure_platform_descriptor(
        data_types=[],
        data_names=[],
        module_sources=[],
        module_names=[],
        resource_types=["aws_ecs_cluster"],
        resource_names=["node10"],
        repo_name="terraform-stack-ecs",
    )

    assert descriptor == {
        "platform_id": "platform:ecs:aws:cluster/node10:none:none",
        "platform_kind": "ecs",
        "platform_name": "node10",
        "platform_provider": "aws",
        "platform_locator": "cluster/node10",
        "platform_environment": None,
        "platform_region": None,
    }


def test_infer_infrastructure_platform_descriptor_ignores_service_stack_cluster_refs() -> (
    None
):
    """Referencing an existing ECS cluster is not the same as provisioning it."""

    descriptor = infer_infrastructure_platform_descriptor(
        data_types=["aws_ecs_cluster"],
        data_names=["node10"],
        module_sources=["boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws"],
        module_names=["api_node_external_search"],
        resource_types=[],
        resource_names=[],
        repo_name="terraform-stack-external-search",
    )

    assert descriptor is None


def test_infer_infrastructure_platform_descriptor_ignores_eks_support_modules() -> None:
    """Karpenter-style EKS addons should not look like cluster provisioning."""

    descriptor = infer_infrastructure_platform_descriptor(
        data_types=["aws_eks_cluster"],
        data_names=["main"],
        module_sources=["terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"],
        module_names=["karpenter_irsa"],
        resource_types=["aws_eks_access_entry"],
        resource_names=["karpenter_nodes"],
        repo_name="terraform-module-karpenter",
    )

    assert descriptor is None


def test_infer_gitops_platform_kind_uses_runtime_family_registry() -> None:
    """GitOps platform hints should share the runtime-family registry logic."""

    assert infer_gitops_platform_kind(
        repo_name="iac-eks-argocd",
        repo_slug="boatsgroup/iac-eks-argocd",
        content="spec: {}",
    ) == "eks"
    assert infer_gitops_platform_kind(
        repo_name="terraform-stack-ecs",
        repo_slug=None,
        content="spec: {}",
    ) == "ecs"


def test_infer_gitops_platform_id_uses_family_provider() -> None:
    """GitOps platform ids should inherit provider data from the runtime family."""

    assert infer_gitops_platform_id(
        repo_name="iac-eks-argocd",
        repo_slug="boatsgroup/iac-eks-argocd",
        content="spec: {}",
        platform_name="bg-qa",
        environment="bg-qa",
    ) == "platform:eks:aws:bg-qa:bg-qa:none"


def test_materialize_workloads_skips_platform_edges_for_cluster_references_only() -> None:
    """Service stacks that only reference a cluster should not provision it."""

    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    recorded_calls: list[tuple[str, dict[str, object]]] = []

    def run(query: str, **kwargs: object) -> _FakeResult:
        recorded_calls.append((query, kwargs))
        if "TerraformDataSource" not in query and "RETURN repo.id as repo_id" in query:
            return _FakeResult(records=[])
        if "TerraformDataSource" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_ref12345",
                        "repo_name": "terraform-stack-external-search",
                        "data_types": ["aws_ecs_cluster"],
                        "data_names": ["node10"],
                        "module_sources": [
                            "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws"
                        ],
                        "module_names": ["api_node_external_search"],
                        "resource_types": [],
                        "resource_names": [],
                    }
                ]
            )
        return _FakeResult()

    session.run.side_effect = run
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session))
    )

    materialize_workloads(builder, info_logger_fn=lambda *_args, **_kwargs: None)

    assert not any(
        "PROVISIONS_PLATFORM" in query for query, _kwargs in recorded_calls
    )


def test_materialize_workloads_skips_platform_edges_for_eks_addon_modules() -> None:
    """EKS add-on modules should not be treated as provisioning the cluster itself."""

    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    recorded_calls: list[tuple[str, dict[str, object]]] = []

    def run(query: str, **kwargs: object) -> _FakeResult:
        recorded_calls.append((query, kwargs))
        if "TerraformDataSource" not in query and "RETURN repo.id as repo_id" in query:
            return _FakeResult(records=[])
        if "TerraformDataSource" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_addon678",
                        "repo_name": "terraform-module-karpenter",
                        "data_types": ["aws_eks_cluster"],
                        "data_names": ["main"],
                        "module_sources": [
                            "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
                        ],
                        "module_names": ["karpenter_irsa"],
                        "resource_types": ["aws_eks_access_entry"],
                        "resource_names": ["karpenter_nodes"],
                    }
                ]
            )
        return _FakeResult()

    session.run.side_effect = run
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session))
    )

    materialize_workloads(builder, info_logger_fn=lambda *_args, **_kwargs: None)

    assert not any(
        "PROVISIONS_PLATFORM" in query for query, _kwargs in recorded_calls
    )


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
