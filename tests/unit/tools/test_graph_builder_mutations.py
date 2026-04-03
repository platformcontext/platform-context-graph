"""Unit tests for graph mutation helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from platform_context_graph.graph.persistence.mutations import (
    delete_repository_from_graph,
)


class _FakeResult:
    """Minimal query result stub for repository delete tests."""

    def __init__(self, single_result=None):
        self._single_result = single_result

    def single(self):
        return self._single_result


class _FakeSession:
    """Context-managed fake Neo4j session."""

    def __init__(self, *, repository_count: int = 1) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._repository_count = repository_count

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query: str, **params):
        self.calls.append((query, params))
        if "RETURN count(r) as cnt" in query:
            return _FakeResult({"cnt": self._repository_count})
        return _FakeResult()


def test_delete_repository_logs_repository_deletion(tmp_path: Path) -> None:
    """Successful deletes should log an explicit repository deletion message."""

    repo_path = tmp_path / "orders-api"
    session = _FakeSession()
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=lambda: session),
    )
    info_logs: list[str] = []
    warning_logs: list[str] = []

    deleted = delete_repository_from_graph(
        builder,
        str(repo_path),
        info_logger_fn=info_logs.append,
        warning_logger_fn=warning_logs.append,
    )

    assert deleted is True
    assert warning_logs == []
    assert info_logs == [
        f"Deleted repository and its contents from graph: {repo_path.resolve()}"
    ]


def test_delete_repository_accepts_canonical_repo_id() -> None:
    """Canonical repository ids should delete without needing a checkout path."""

    session = _FakeSession()
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=lambda: session),
    )
    info_logs: list[str] = []
    warning_logs: list[str] = []

    deleted = delete_repository_from_graph(
        builder,
        "repository:r_12345678",
        info_logger_fn=info_logs.append,
        warning_logger_fn=warning_logs.append,
    )

    assert deleted is True
    assert warning_logs == []
    assert session.calls[0][1]["lookup_values"] == ("repository:r_12345678",)
    assert info_logs == [
        "Deleted repository and its contents from graph: repository:r_12345678"
    ]


def test_delete_repository_rejects_empty_identifier() -> None:
    """Empty identifiers should fail fast with a clear warning."""

    session = _FakeSession()
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=lambda: session),
    )
    info_logs: list[str] = []
    warning_logs: list[str] = []

    deleted = delete_repository_from_graph(
        builder,
        "   ",
        info_logger_fn=info_logs.append,
        warning_logger_fn=warning_logs.append,
    )

    assert deleted is False
    assert info_logs == []
    assert warning_logs == ["Attempted to delete repository with empty identifier"]
    assert session.calls == []


def test_delete_repository_logs_missing_repository_at_debug_only(
    tmp_path: Path,
) -> None:
    """Missing repositories should be treated as a debug-only no-op."""

    repo_path = tmp_path / "orders-api"
    session = _FakeSession(repository_count=0)
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=lambda: session),
    )
    info_logs: list[str] = []
    debug_logs: list[str] = []
    warning_logs: list[str] = []

    deleted = delete_repository_from_graph(
        builder,
        str(repo_path),
        info_logger_fn=info_logs.append,
        debug_logger_fn=debug_logs.append,
        warning_logger_fn=warning_logs.append,
    )

    assert deleted is False
    assert info_logs == []
    assert warning_logs == []
    assert debug_logs == [
        f"Repository already absent from graph; nothing to delete: "
        f"{repo_path.resolve()}"
    ]


def test_delete_repository_uses_dynamic_local_path_lookup() -> None:
    """Delete queries should avoid sparse-graph warnings for missing local_path."""

    session = _FakeSession()
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=lambda: session),
    )

    delete_repository_from_graph(
        builder,
        "repository:r_12345678",
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    lookup_query = session.calls[0][0]
    delete_query = session.calls[1][0]
    assert "r[$local_path_key] IN $lookup_values" in lookup_query
    assert "r.local_path IN $lookup_values" not in lookup_query
    assert "r[$local_path_key] IN $lookup_values" in delete_query
    assert "r.local_path IN $lookup_values" not in delete_query
