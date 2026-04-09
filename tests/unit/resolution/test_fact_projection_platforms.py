"""Tests for platform projection from stored facts."""

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
    """Minimal context-managed fake session."""

    def __enter__(self) -> "_FakeSession":
        """Enter the fake session context."""

        return self

    def __exit__(self, *_args: object) -> bool:
        """Exit the fake session context without suppressing errors."""

        return False


class _FakeDriver:
    """Expose one reusable fake session via the driver interface."""

    def __init__(self, session: _FakeSession) -> None:
        """Bind the fake driver to one captured session."""

        self._session = session

    def session(self) -> _FakeSession:
        """Return the captured fake session."""

        return self._session


def test_project_platform_facts_targets_projected_repositories() -> None:
    """Platform projection should target the same resolved repository paths."""

    captured: dict[str, object] = {}
    fact_records = [
        FactRecordRow(
            fact_id="fact:repo",
            fact_type="RepositoryObserved",
            repository_id="github.com/acme/infra",
            checkout_path="/tmp/infra",
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
    session = _FakeSession()
    builder = type(
        "FakeBuilder",
        (),
        {"driver": _FakeDriver(session)},
    )()

    def _materialize_platforms(
        session_arg: object,
        *,
        repo_paths: list[Path] | None,
        progress_callback: object | None = None,
        projection_context_by_repo_id: dict[str, dict[str, str]] | None = None,
        shared_projection_intent_store: object | None = None,
    ) -> dict[str, int]:
        captured["session"] = session_arg
        captured["repo_paths"] = repo_paths
        captured["progress_callback"] = progress_callback
        captured["projection_context_by_repo_id"] = projection_context_by_repo_id
        captured["shared_projection_intent_store"] = shared_projection_intent_store
        return {"infrastructure_platform_edges_projected": 1}

    metrics = project_platform_facts(
        builder=builder,
        fact_records=fact_records,
        materialize_platforms_fn=_materialize_platforms,
        shared_projection_intent_store="shared-store",
    )

    assert metrics == {"infrastructure_platform_edges_projected": 1}
    assert captured["session"] is session
    assert captured["repo_paths"] == [Path("/tmp/infra").resolve()]
    assert captured["projection_context_by_repo_id"] == {
        "github.com/acme/infra": {
            "generation_id": "snapshot-abc",
            "source_run_id": "run-123",
        }
    }
    assert captured["shared_projection_intent_store"] == "shared-store"
