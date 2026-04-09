"""Tests for infrastructure platform materialization boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from platform_context_graph.resolution.platforms import (
    materialize_infrastructure_platforms,
)
from platform_context_graph.resolution.platforms import (
    materialize_infrastructure_platforms_for_repo_paths,
)


class _FakeResult:
    """Minimal query result wrapper with ``data`` support."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, Any]]:
        """Return the captured result rows."""

        return self._rows


class _FakeSession:
    """Minimal session stub for platform materialization tests."""

    def __init__(
        self,
        *,
        repo_rows: list[dict[str, Any]] | None = None,
        platform_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.repo_rows = repo_rows or []
        self.platform_rows = platform_rows or []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **params: Any) -> _FakeResult:
        """Record the query and return the matching fake row set."""

        self.calls.append((query, params))
        if "RETURN repo.id as repo_id," in query:
            return _FakeResult(self.platform_rows)
        if "RETURN repo.id as repo_id" in query:
            return _FakeResult(self.repo_rows)
        raise AssertionError(f"Unexpected query: {query}")


def test_materialize_infrastructure_platforms_for_repo_paths_skips_global_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repo-scoped projection should not run global orphan platform cleanup."""

    session = _FakeSession(repo_rows=[{"repo_id": "repository:r_123"}])

    monkeypatch.setattr(
        "platform_context_graph.resolution.platforms."
        "retract_infrastructure_platform_rows",
        lambda *_args, **_kwargs: {
            "cleanup_deleted_edges": 0,
            "cleanup_deleted_nodes": 0,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.resolution.platforms."
        "write_infrastructure_platform_rows",
        lambda *_args, **_kwargs: {
            "write_chunk_count": 0,
            "written_row_count": 0,
        },
    )

    def _unexpected_cleanup(*_args: Any, **_kwargs: Any) -> dict[str, int]:
        raise AssertionError(
            "repo-scoped platform projection should not run orphan cleanup"
        )

    monkeypatch.setattr(
        "platform_context_graph.resolution.platforms.cleanup_orphan_platform_state",
        _unexpected_cleanup,
    )

    metrics = materialize_infrastructure_platforms_for_repo_paths(
        session,
        repo_paths=[Path("/tmp/infra")],
    )

    assert metrics == {
        "cleanup_deleted_edges": 0,
        "cleanup_deleted_nodes": 0,
        "infrastructure_platform_edges_projected": 0,
        "write_chunk_count": 0,
    }


def test_materialize_infrastructure_platforms_runs_dedicated_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Global platform materialization should delegate orphan cleanup explicitly."""

    session = _FakeSession()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "platform_context_graph.resolution.platforms."
        "materialize_infrastructure_platforms_for_repo_paths",
        lambda session_arg, *, repo_paths, progress_callback=None: captured.update(
            {
                "materialize_session": session_arg,
                "materialize_repo_paths": repo_paths,
                "progress_callback": progress_callback,
            }
        ),
    )
    monkeypatch.setattr(
        "platform_context_graph.resolution.platforms.cleanup_orphan_platform_state",
        lambda session_arg, *, evidence_source: captured.update(
            {
                "cleanup_session": session_arg,
                "cleanup_evidence_source": evidence_source,
            }
        ),
    )

    materialize_infrastructure_platforms(session)

    assert captured == {
        "cleanup_evidence_source": "finalization/workloads",
        "cleanup_session": session,
        "materialize_repo_paths": None,
        "materialize_session": session,
        "progress_callback": None,
    }
