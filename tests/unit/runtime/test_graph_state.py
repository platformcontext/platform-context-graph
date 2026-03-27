"""Unit tests for repository graph recovery probes."""

from __future__ import annotations

import importlib
from pathlib import Path
from types import SimpleNamespace


class _FakeResult:
    """Minimal query result stub for graph-state tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, object]]:
        return self._rows


class _FakeSession:
    """Context-managed fake Neo4j session."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, dict[str, object]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query: str, **params):
        self.calls.append((query, params))
        return _FakeResult(self.rows)


def test_graph_missing_repository_paths_marks_drifted_checkout_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A checkout that moved on disk should be reindexed by canonical identity."""

    graph_state = importlib.import_module(
        "platform_context_graph.runtime.ingester.graph_state"
    )

    repo_path = tmp_path / "workspace" / "payments-api"
    repo_path.mkdir(parents=True)
    (repo_path / ".git").mkdir()
    stale_graph_path = tmp_path / "archive" / "payments-api"

    session = _FakeSession(
        [
            {
                "repo_path": str(repo_path.resolve()),
                "repo_id": "repository:r_12345678",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "repo_slug": "platformcontext/payments-api",
                "graph_path": str(stale_graph_path.resolve()),
                "needs_recovery": True,
            }
        ]
    )
    monkeypatch.setattr(
        graph_state,
        "get_database_manager",
        lambda: SimpleNamespace(
            get_driver=lambda: SimpleNamespace(session=lambda: session)
        ),
    )
    monkeypatch.setattr(
        graph_state,
        "repository_metadata",
        lambda **_kwargs: {
            "id": "repository:r_12345678",
            "remote_url": "https://github.com/platformcontext/payments-api",
            "repo_slug": "platformcontext/payments-api",
        },
    )
    monkeypatch.setattr(graph_state, "git_remote_for_path", lambda _path: None)

    missing = graph_state.graph_missing_repository_paths([repo_path])

    assert missing == [repo_path.resolve()]
    assert session.calls[0][1]["repo_probes"][0]["repo_id"] == "repository:r_12345678"
    assert "[:REPO_CONTAINS]->(f:File)" in session.calls[0][0]


def test_graph_missing_repository_paths_marks_foreign_file_subtrees_for_recovery(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Mixed file subtrees under one repo should trigger graph recovery."""

    graph_state = importlib.import_module(
        "platform_context_graph.runtime.ingester.graph_state"
    )

    repo_path = tmp_path / "workspace" / "boatsgroup" / "payments-api"
    repo_path.mkdir(parents=True)
    (repo_path / ".git").mkdir()

    session = _FakeSession(
        [
            {
                "repo_path": str(repo_path.resolve()),
                "repo_id": "repository:r_98765432",
                "remote_url": "https://github.com/platformcontext/payments-api",
                "repo_slug": "platformcontext/payments-api",
                "graph_path": str(repo_path.resolve()),
                "has_foreign_files": True,
                "needs_recovery": True,
            }
        ]
    )
    monkeypatch.setattr(
        graph_state,
        "get_database_manager",
        lambda: SimpleNamespace(
            get_driver=lambda: SimpleNamespace(session=lambda: session)
        ),
    )
    monkeypatch.setattr(
        graph_state,
        "repository_metadata",
        lambda **_kwargs: {
            "id": "repository:r_98765432",
            "remote_url": "https://github.com/platformcontext/payments-api",
            "repo_slug": "platformcontext/payments-api",
        },
    )
    monkeypatch.setattr(graph_state, "git_remote_for_path", lambda _path: None)

    missing = graph_state.graph_missing_repository_paths([repo_path])

    assert missing == [repo_path.resolve()]
    assert "has_foreign_files" in session.calls[0][0]
    assert "[:REPO_CONTAINS]->(f:File)" in session.calls[0][0]
