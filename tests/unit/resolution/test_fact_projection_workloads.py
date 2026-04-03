"""Tests for workload projection from stored facts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.resolution.projection.workloads import (
    project_workload_facts,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for projection tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_project_workload_facts_targets_projected_repositories() -> None:
    """Workload projection should forward targeted repo paths to the materializer."""

    captured: dict[str, object] = {}
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

    def _materialize_workloads(
        builder: object,
        *,
        info_logger_fn: object,
        committed_repo_paths: list[Path] | None,
        progress_callback: object | None = None,
    ) -> dict[str, int]:
        captured["builder"] = builder
        captured["repo_paths"] = committed_repo_paths
        captured["progress_callback"] = progress_callback
        assert callable(info_logger_fn)
        return {"workloads_projected": 2}

    builder = SimpleNamespace()

    metrics = project_workload_facts(
        builder=builder,
        fact_records=fact_records,
        materialize_workloads_fn=_materialize_workloads,
        info_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert metrics == {"workloads_projected": 2}
    assert captured["builder"] is builder
    assert captured["repo_paths"] == [Path("/tmp/service").resolve()]
