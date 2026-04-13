from __future__ import annotations

from pathlib import Path

from platform_context_graph.indexing import coordinator_models
from platform_context_graph.indexing import run_status


def _sample_run_state() -> coordinator_models.IndexRunState:
    repository = coordinator_models.RepositoryRunState(
        repo_path="/tmp/repos/payments",
        status="completed",
        file_count=12,
        started_at="2026-04-13T12:00:00+00:00",
        finished_at="2026-04-13T12:01:00+00:00",
        updated_at="2026-04-13T12:01:00+00:00",
    )
    return coordinator_models.IndexRunState(
        run_id="deadbeefcafebabe",
        root_path="/tmp/repos",
        family="index",
        source="manual",
        discovery_signature="sig-123",
        is_dependency=False,
        status="completed",
        finalization_status="completed",
        created_at="2026-04-13T12:00:00+00:00",
        updated_at="2026-04-13T12:01:00+00:00",
        repositories={repository.repo_path: repository},
    )


def test_describe_latest_index_run_returns_serialized_summary(monkeypatch) -> None:
    """Latest-run lookups should preserve the existing checkpoint payload shape."""

    run_state = _sample_run_state()
    monkeypatch.setattr(
        run_status,
        "_matching_run_states",
        lambda _path: [run_state],
    )

    result = run_status.describe_latest_index_run(Path("/tmp/repos"))

    assert result is not None
    assert result["run_id"] == "deadbeefcafebabe"
    assert result["root_path"] == "/tmp/repos"
    assert result["repository_count"] == 1
    assert result["completed_repositories"] == 1
    assert result["failed_repositories"] == 0
    assert result["pending_repositories"] == 0
    assert result["repositories"][0]["repo_path"] == "/tmp/repos/payments"


def test_describe_index_run_prefers_run_id_lookup(monkeypatch) -> None:
    """Explicit run IDs should load the persisted checkpoint directly."""

    run_state = _sample_run_state()
    monkeypatch.setattr(
        run_status,
        "_load_run_state_by_id",
        lambda run_id: run_state if run_id == "deadbeefcafebabe" else None,
    )
    monkeypatch.setattr(
        run_status,
        "_matching_run_states",
        lambda _path: [],
    )

    result = run_status.describe_index_run("deadbeefcafebabe")

    assert result is not None
    assert result["run_id"] == "deadbeefcafebabe"


def test_describe_index_run_falls_back_to_latest_path_lookup(monkeypatch) -> None:
    """Path targets should resolve through the latest-run matcher."""

    run_state = _sample_run_state()
    captured = {}

    def _matching(path: Path):
        captured["path"] = path
        return [run_state]

    monkeypatch.setattr(run_status, "_matching_run_states", _matching)

    result = run_status.describe_index_run("/tmp/repos")

    assert result is not None
    assert captured["path"] == Path("/tmp/repos").resolve()
    assert result["run_id"] == "deadbeefcafebabe"
