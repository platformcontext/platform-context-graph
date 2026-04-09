"""Unit tests for repository-subtree reset helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from platform_context_graph.graph.persistence.mutations import (
    reset_repository_subtree_in_graph,
)


class _FakeResult:
    """Minimal query result stub for repository subtree reset tests."""

    def __init__(self, single_result: dict[str, Any] | None = None) -> None:
        self._single_result = single_result

    def single(self) -> dict[str, Any] | None:
        """Return the single-record payload for the fake result."""

        return self._single_result


class _FakeSession:
    """Context-managed fake Neo4j session."""

    def __init__(self, *, repository_count: int = 1) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._repository_count = repository_count

    def __enter__(self) -> _FakeSession:
        """Return the fake session context."""

        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        """Exit the fake session context without suppressing errors."""

        del exc_type, exc, tb
        return False

    def run(self, query: str, **params: Any) -> _FakeResult:
        """Record each query and emulate repository existence lookups."""

        self.calls.append((query, params))
        if "RETURN count(r) as cnt" in query:
            return _FakeResult({"cnt": self._repository_count})
        return _FakeResult()


def test_reset_repository_subtree_preserves_repository_node(
    tmp_path: Path,
) -> None:
    """Repo-local reset should only delete descendants, not the Repository node."""

    repo_path = tmp_path / "orders-api"
    session = _FakeSession()
    builder = SimpleNamespace(driver=SimpleNamespace(session=lambda: session))
    info_logs: list[str] = []
    warning_logs: list[str] = []

    reset = reset_repository_subtree_in_graph(
        builder,
        str(repo_path),
        info_logger_fn=info_logs.append,
        warning_logger_fn=warning_logs.append,
    )

    assert reset is True
    assert warning_logs == []
    assert info_logs == [
        "Reset repository subtree while preserving repository node: "
        f"{repo_path.resolve()}"
    ]
    owned_reset_query = session.calls[1][0]
    relationship_reset_query = session.calls[2][0]
    assert "MATCH (r)-[:CONTAINS|REPO_CONTAINS*1..]->(owned_tree)" in owned_reset_query
    assert "MATCH (r)-[:DEFINES]->(defined_workload:Workload)" in owned_reset_query
    assert "MATCH (owned_workload:Workload {repo_id: r.id})" in owned_reset_query
    assert (
        "MATCH (owned_instance:WorkloadInstance {repo_id: r.id})" in owned_reset_query
    )
    assert "owned_nodes + collect" not in owned_reset_query
    assert "maybe_owned_nodes" not in owned_reset_query
    assert "DETACH DELETE owned" in owned_reset_query
    assert "OPTIONAL MATCH (r)-[rel]-()" in relationship_reset_query
    assert "DELETE rel" in relationship_reset_query
    assert "DETACH DELETE r" not in owned_reset_query
    assert "DELETE r" not in owned_reset_query


def test_reset_repository_subtree_uses_dynamic_local_path_lookup() -> None:
    """Subtree reset queries should avoid sparse-graph warnings for local_path."""

    session = _FakeSession()
    builder = SimpleNamespace(driver=SimpleNamespace(session=lambda: session))

    reset_repository_subtree_in_graph(
        builder,
        "repository:r_12345678",
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    lookup_query = session.calls[0][0]
    reset_query = session.calls[1][0]
    relationship_reset_query = session.calls[2][0]
    assert "r[$local_path_key] IN $lookup_values" in lookup_query
    assert "r.local_path IN $lookup_values" not in lookup_query
    assert "r[$local_path_key] IN $lookup_values" in reset_query
    assert "r.local_path IN $lookup_values" not in reset_query
    assert "r[$local_path_key] IN $lookup_values" in relationship_reset_query
    assert "r.local_path IN $lookup_values" not in relationship_reset_query
