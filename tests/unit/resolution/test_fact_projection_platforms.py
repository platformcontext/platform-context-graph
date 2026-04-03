"""Tests for infrastructure platform materialization from stored facts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.resolution.projection.workloads import (
    project_platform_facts,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for projection tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


class _FakeSession:
    """Simple context-managed session stub."""

    def __enter__(self) -> "_FakeSession":
        """Enter the fake session context."""

        return self

    def __exit__(self, *_args: object) -> bool:
        """Exit the fake session context without suppressing errors."""

        return False


class _FakeDriver:
    """Expose one session via the driver interface."""

    def __init__(self, session: _FakeSession) -> None:
        """Bind the fake driver to a session."""

        self._session = session

    def session(self) -> _FakeSession:
        """Return the bound fake session."""

        return self._session


def test_project_platform_facts_targets_repository_paths_from_facts() -> None:
    """Platform materialization should scope itself to repository facts."""

    session = _FakeSession()
    builder = type("FakeBuilder", (), {"driver": _FakeDriver(session)})()
    fact_records = [
        FactRecordRow(
            fact_id="fact:repo",
            fact_type="RepositoryObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path=None,
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={"is_dependency": False},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]
    captured: dict[str, object] = {}

    def _materialize_platforms(
        graph_session: object,
        *,
        repo_paths: list[Path] | None,
        progress_callback: object | None = None,
    ) -> dict[str, int]:
        captured["session"] = graph_session
        captured["repo_paths"] = repo_paths
        captured["progress_callback"] = progress_callback
        return {"infrastructure_platform_edges_projected": 2}

    metrics = project_platform_facts(
        builder=builder,
        fact_records=fact_records,
        materialize_platforms_fn=_materialize_platforms,
    )

    assert metrics == {"infrastructure_platform_edges_projected": 2}
    assert captured["session"] is session
    assert captured["repo_paths"] == [Path("/tmp/service").resolve()]
