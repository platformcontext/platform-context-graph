"""Tests for repository projection from stored facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.resolution.projection import project_git_fact_records


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for projection tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


@dataclass
class _FakeResult:
    """Minimal result object that supports eager consumption."""

    def consume(self) -> None:
        """Mimic the Neo4j result API used by write helpers."""


class _FakeSession:
    """Capture write queries issued during projection."""

    def __init__(self) -> None:
        """Initialize an empty write log."""

        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> "_FakeSession":
        """Enter the fake session context."""

        return self

    def __exit__(self, *_args: object) -> bool:
        """Exit the fake session context without suppressing errors."""

        return False

    def execute_write(self, write_fn: Any) -> None:
        """Run one managed write callback."""

        write_fn(self)

    def run(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        """Record a Cypher write call."""

        params = parameters if parameters is not None else kwargs
        self.calls.append((query, params))
        return _FakeResult()


class _FakeDriver:
    """Expose one reusable fake session via the driver interface."""

    def __init__(self, session: _FakeSession) -> None:
        """Bind the fake driver to one captured session."""

        self._session = session

    def session(self) -> _FakeSession:
        """Return the captured fake session."""

        return self._session


def test_project_git_fact_records_merges_repository_nodes() -> None:
    """Repository facts should produce a canonical repository merge."""

    session = _FakeSession()
    builder = type(
        "FakeBuilder",
        (),
        {"driver": _FakeDriver(session)},
    )()
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
    expected_repo_path = str(Path("/tmp/service").resolve())

    project_git_fact_records(builder=builder, fact_records=fact_records)

    assert any(
        "MERGE (r:Repository {id: $repo_id})" in query
        and params["repo_id"] == "github.com/acme/service"
        and params["repo_path"] == expected_repo_path
        and params["name"] == "service"
        for query, params in session.calls
    )
