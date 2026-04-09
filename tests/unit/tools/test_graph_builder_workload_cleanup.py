"""Regression tests for targeted workload finalization cleanup."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.resolution.workloads.materialization import (
    materialize_workloads,
)


class _FakeResult:
    def __init__(self, *, records=None):
        self._records = records or []

    def data(self):
        return self._records


def _capture_run(
    recorded_calls: list[tuple[str, dict[str, object]]],
    resolver,
):
    """Record `session.run()` calls regardless of positional or keyword params."""

    def run(
        query: str,
        parameters: dict[str, object] | None = None,
        **kwargs: object,
    ) -> _FakeResult:
        merged_kwargs = dict(parameters or {})
        merged_kwargs.update(kwargs)
        recorded_calls.append((query, merged_kwargs))
        return resolver(query, merged_kwargs)

    return run


def _query_kwargs(
    recorded_calls: list[tuple[str, dict[str, object]]],
    query_fragment: str,
) -> dict[str, object]:
    """Return captured kwargs for the first query containing `query_fragment`."""

    return next(kwargs for query, kwargs in recorded_calls if query_fragment in query)


def _query_text(
    recorded_calls: list[tuple[str, dict[str, object]]],
    query_fragment: str,
) -> str:
    """Return the first query containing `query_fragment`."""

    return next(query for query, _kwargs in recorded_calls if query_fragment in query)


def _build_builder(session: MagicMock) -> SimpleNamespace:
    """Create a graph builder wrapper around the fake Neo4j session."""

    return SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session))
    )


def _repo_path(base_dir: Path, name: str) -> Path:
    """Create one targeted repository path for the materialization filter."""

    repo_path = base_dir / name
    repo_path.mkdir()
    return repo_path


def test_materialize_workloads_retracts_targeted_workload_state_before_rebuild(
    tmp_path: Path,
) -> None:
    """Targeted workload finalization should delete stale owned state first."""

    active_repo_path = _repo_path(tmp_path, "api-node-search")
    stale_repo_path = _repo_path(tmp_path, "retired-service")
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    recorded_calls: list[tuple[str, dict[str, object]]] = []

    def resolve(query: str, kwargs: dict[str, object]) -> _FakeResult:
        if "resource_kinds" in query and "RETURN repo.id as repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_active123",
                        "repo_name": "api-node-search",
                        "deployment_repo_id": "repository:r_gitops456",
                        "deployment_repo_name": "helm-charts",
                        "resource_kinds": ["Deployment"],
                        "namespaces": ["bg-qa"],
                        "source_roots": ["argocd/api-node-search/"],
                    }
                ]
            )
        if "RETURN repo.id as target_repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "target_repo_id": "repository:r_active123",
                        "target_repo_name": "api-node-search",
                    },
                    {
                        "target_repo_id": "repository:r_stale789",
                        "target_repo_name": "retired-service",
                    },
                ]
            )
        if "ORDER BY repo.id" in query and "RETURN repo.id as repo_id" in query:
            return _FakeResult(
                records=[
                    {"repo_id": "repository:r_active123"},
                    {"repo_id": "repository:r_stale789"},
                ]
            )
        if "RETURN deployment_repo.id as deployment_repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "deployment_repo_id": "repository:r_gitops456",
                        "relative_path": "argocd/api-node-search/overlays/bg-qa/config.yaml",
                    }
                ]
            )
        if "RETURN f.path as path" in query:
            return _FakeResult(records=[])
        return _FakeResult()

    session.run.side_effect = _capture_run(recorded_calls, resolve)

    materialize_workloads(
        _build_builder(session),
        info_logger_fn=lambda *_args, **_kwargs: None,
        committed_repo_paths=[active_repo_path, stale_repo_path],
    )

    delete_instance_kwargs = _query_kwargs(recorded_calls, "MATCH (i:WorkloadInstance)")
    delete_instance_node_query = _query_text(recorded_calls, "AND NOT (i)--()")
    delete_deployment_source_query = _query_text(
        recorded_calls,
        "DEPLOYMENT_SOURCE",
    )
    delete_runs_on_query = _query_text(recorded_calls, "MATCH (i)-[rel:RUNS_ON]->")
    delete_repo_depends_query = _query_text(
        recorded_calls,
        "MATCH (source_repo:Repository)-[rel:DEPENDS_ON]->",
    )
    delete_workload_depends_query = _query_text(
        recorded_calls,
        "MATCH (source:Workload)-[rel:DEPENDS_ON]->",
    )
    delete_provisions_query = _query_text(
        recorded_calls,
        "MATCH (repo:Repository)-[rel:PROVISIONS_PLATFORM]->",
    )
    merge_instances_index = next(
        index
        for index, (query, _kwargs) in enumerate(recorded_calls)
        if "MERGE (i:WorkloadInstance {id: row.instance_id})" in query
    )
    delete_instances_index = next(
        index
        for index, (query, _kwargs) in enumerate(recorded_calls)
        if "MATCH (i:WorkloadInstance)" in query
    )

    assert delete_instances_index < merge_instances_index
    assert delete_instance_kwargs["repo_ids"] == [
        "repository:r_active123",
        "repository:r_stale789",
    ]
    assert delete_instance_kwargs["evidence_source"] == "finalization/workloads"
    assert "DELETE rel" in delete_deployment_source_query
    assert "DELETE rel" in delete_runs_on_query
    assert "DELETE rel" in delete_repo_depends_query
    assert "DELETE rel" in delete_workload_depends_query
    assert "DELETE rel" in delete_provisions_query
    assert not any("MATCH (p:Platform)" in query for query, _kwargs in recorded_calls)
    assert "DELETE i" in delete_instance_node_query


def test_materialize_workloads_cleanup_keeps_active_workloads_out_of_stale_retraction(
    tmp_path: Path,
) -> None:
    """Active targeted workloads should not be retracted with stale cleanup."""

    active_repo_path = _repo_path(tmp_path, "api-node-search")
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    recorded_calls: list[tuple[str, dict[str, object]]] = []

    def resolve(query: str, kwargs: dict[str, object]) -> _FakeResult:
        if "resource_kinds" in query and "RETURN repo.id as repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_active123",
                        "repo_name": "api-node-search",
                        "deployment_repo_id": None,
                        "deployment_repo_name": None,
                        "resource_kinds": ["Deployment"],
                        "namespaces": ["bg-qa"],
                        "source_roots": [],
                    }
                ]
            )
        if "RETURN repo.id as target_repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "target_repo_id": "repository:r_active123",
                        "target_repo_name": "api-node-search",
                    }
                ]
            )
        if "RETURN f.path as path" in query:
            return _FakeResult(records=[])
        return _FakeResult()

    session.run.side_effect = _capture_run(recorded_calls, resolve)

    materialize_workloads(
        _build_builder(session),
        info_logger_fn=lambda *_args, **_kwargs: None,
        committed_repo_paths=[active_repo_path],
    )

    delete_stale_workloads_query = _query_text(
        recorded_calls,
        "MATCH (repo:Repository)-[rel:DEFINES]->(w:Workload)",
    )
    delete_stale_workloads_kwargs = _query_kwargs(
        recorded_calls,
        "MATCH (repo:Repository)-[rel:DEFINES]->(w:Workload)",
    )
    delete_inbound_workload_deps_query = _query_text(
        recorded_calls,
        "MATCH (target:Workload)",
    )

    assert "NOT w.id IN $active_workload_ids" in delete_stale_workloads_query
    assert delete_stale_workloads_kwargs["active_workload_ids"] == [
        "workload:api-node-search"
    ]
    assert "NOT target.id IN $active_workload_ids" in delete_inbound_workload_deps_query


def test_materialize_workloads_cleanup_only_deletes_workload_owned_dependencies(
    tmp_path: Path,
) -> None:
    """Dependency cleanup must stay scoped to workload-owned evidence."""

    targeted_repo_path = _repo_path(tmp_path, "api-node-search")
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    recorded_calls: list[tuple[str, dict[str, object]]] = []

    def resolve(query: str, kwargs: dict[str, object]) -> _FakeResult:
        if "resource_kinds" in query and "RETURN repo.id as repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "repo_id": "repository:r_active123",
                        "repo_name": "api-node-search",
                        "deployment_repo_id": None,
                        "deployment_repo_name": None,
                        "resource_kinds": ["Deployment"],
                        "namespaces": ["bg-qa"],
                        "source_roots": [],
                    }
                ]
            )
        if "RETURN repo.id as target_repo_id" in query:
            return _FakeResult(
                records=[
                    {
                        "target_repo_id": "repository:r_active123",
                        "target_repo_name": "api-node-search",
                    }
                ]
            )
        if "RETURN f.path as path" in query:
            return _FakeResult(records=[])
        return _FakeResult()

    session.run.side_effect = _capture_run(recorded_calls, resolve)

    materialize_workloads(
        _build_builder(session),
        info_logger_fn=lambda *_args, **_kwargs: None,
        committed_repo_paths=[targeted_repo_path],
    )

    repo_depends_query = _query_text(
        recorded_calls,
        "MATCH (source_repo:Repository)-[rel:DEPENDS_ON]->",
    )
    workload_depends_query = _query_text(
        recorded_calls,
        "MATCH (source:Workload)-[rel:DEPENDS_ON]->",
    )

    assert "rel.evidence_source = $evidence_source" in repo_depends_query
    assert "rel.evidence_source = $evidence_source" in workload_depends_query
    assert "resolver" not in repo_depends_query
    assert "resolver" not in workload_depends_query
