"""Unit tests for durable repository coverage publishing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.indexing import coordinator_coverage


class _NullSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeObservability:
    def __init__(self) -> None:
        self.component = "test"

    def start_span(self, *_args, **_kwargs):
        return _NullSpan()


def test_publish_run_repository_coverage_skips_repos_when_graph_counts_fail(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Coverage publishing should degrade without aborting the whole run."""

    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()

    run_state = SimpleNamespace(
        run_id="run-123",
        finalization_status="pending",
        last_error=None,
        created_at="2026-03-25T00:00:00Z",
        updated_at="2026-03-25T00:01:00Z",
        finalization_finished_at=None,
        repositories={
            str(repo_a.resolve()): SimpleNamespace(
                status="commit_incomplete",
                phase="committing",
                file_count=10,
                error=None,
                commit_finished_at=None,
            ),
            str(repo_b.resolve()): SimpleNamespace(
                status="completed",
                phase="completed",
                file_count=20,
                error=None,
                commit_finished_at="2026-03-25T00:02:00Z",
            ),
        },
    )

    monkeypatch.setattr(
        coordinator_coverage,
        "_coverage_metadata",
        lambda repo_path: {
            "id": f"repository:{repo_path.name}",
            "name": repo_path.name,
            "local_path": str(repo_path.resolve()),
        },
    )

    def _graph_counts(_builder, metadata):
        if metadata["name"] == "repo-a":
            raise RuntimeError("neo4j unavailable")
        return {
            "root_file_count": 1,
            "root_directory_count": 2,
            "file_count": 20,
            "top_level_function_count": 3,
            "class_method_count": 4,
            "total_function_count": 7,
            "class_count": 2,
        }

    monkeypatch.setattr(coordinator_coverage, "_graph_counts", _graph_counts)
    monkeypatch.setattr(
        coordinator_coverage,
        "_content_counts",
        lambda _builder, _repo_id: {
            "content_file_count": 9,
            "content_entity_count": 12,
        },
    )

    upserts: list[dict[str, object]] = []
    monkeypatch.setattr(
        coordinator_coverage,
        "upsert_repository_coverage",
        lambda **kwargs: upserts.append(kwargs),
    )

    coordinator_coverage.publish_run_repository_coverage(
        builder=SimpleNamespace(),
        run_state=run_state,
        repo_paths=[repo_a, repo_b],
        include_graph_counts=True,
        include_content_counts=True,
    )

    assert len(upserts) == 1
    assert upserts[0]["repo_id"] == "repository:repo-b"
    assert upserts[0]["graph_recursive_file_count"] == 20
    assert upserts[0]["content_file_count"] == 9


def test_publish_repository_coverage_reuses_existing_counts_for_lightweight_updates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Lightweight finalization heartbeats should preserve existing durable counts."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    run_state = SimpleNamespace(
        run_id="run-123",
        finalization_status="running",
        last_error=None,
        created_at="2026-03-25T00:00:00Z",
        updated_at="2026-03-25T00:05:00Z",
        finalization_finished_at=None,
    )
    repo_state = SimpleNamespace(
        status="completed",
        phase="completed",
        file_count=20,
        error=None,
        commit_finished_at="2026-03-25T00:04:00Z",
    )

    monkeypatch.setattr(
        coordinator_coverage,
        "_coverage_metadata",
        lambda repo_path: {
            "id": f"repository:{repo_path.name}",
            "name": repo_path.name,
            "local_path": str(repo_path.resolve()),
        },
    )
    monkeypatch.setattr(
        coordinator_coverage,
        "get_repository_coverage",
        lambda **_kwargs: {
            "root_file_count": 2,
            "root_directory_count": 3,
            "graph_recursive_file_count": 20,
            "top_level_function_count": 4,
            "class_method_count": 5,
            "total_function_count": 9,
            "class_count": 2,
            "content_file_count": 18,
            "content_entity_count": 42,
        },
    )

    upserts: list[dict[str, object]] = []
    monkeypatch.setattr(
        coordinator_coverage,
        "upsert_repository_coverage",
        lambda **kwargs: upserts.append(kwargs),
    )

    coordinator_coverage.publish_repository_coverage(
        builder=SimpleNamespace(),
        run_state=run_state,
        repo_state=repo_state,
        repo_path=repo,
        include_graph_counts=False,
        include_content_counts=False,
    )

    assert len(upserts) == 1
    assert upserts[0]["graph_recursive_file_count"] == 20
    assert upserts[0]["content_file_count"] == 18
    assert upserts[0]["content_entity_count"] == 42
    assert upserts[0]["finalization_status"] == "running"


def test_publish_repository_coverage_emits_structured_gap_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Coverage publishing should log the discovered-vs-graph/content gaps."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    run_state = SimpleNamespace(
        run_id="run-123",
        finalization_status="completed",
        last_error=None,
        created_at="2026-03-25T00:00:00Z",
        updated_at="2026-03-25T00:05:00Z",
        finalization_finished_at="2026-03-25T00:06:00Z",
    )
    repo_state = SimpleNamespace(
        status="completed",
        phase="completed",
        file_count=20,
        error=None,
        commit_finished_at="2026-03-25T00:04:00Z",
    )

    monkeypatch.setattr(
        coordinator_coverage,
        "_coverage_metadata",
        lambda repo_path: {
            "id": f"repository:{repo_path.name}",
            "name": repo_path.name,
            "local_path": str(repo_path.resolve()),
        },
    )
    monkeypatch.setattr(
        coordinator_coverage,
        "_graph_counts",
        lambda _builder, _metadata: {
            "root_file_count": 2,
            "root_directory_count": 3,
            "file_count": 12,
            "top_level_function_count": 4,
            "class_method_count": 5,
            "total_function_count": 9,
            "class_count": 2,
        },
    )
    monkeypatch.setattr(
        coordinator_coverage,
        "_content_counts",
        lambda _builder, _repo_id: {
            "content_file_count": 7,
            "content_entity_count": 42,
        },
    )
    monkeypatch.setattr(
        coordinator_coverage,
        "get_observability",
        lambda: _FakeObservability(),
    )

    upserts: list[dict[str, object]] = []
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        coordinator_coverage,
        "upsert_repository_coverage",
        lambda **kwargs: upserts.append(kwargs),
    )
    monkeypatch.setattr(
        coordinator_coverage,
        "emit_log_call",
        lambda _logger_fn, _message, *, event_name=None, extra_keys=None, exc_info=None: events.append(
            {
                "event_name": event_name,
                "extra_keys": extra_keys or {},
                "exc_info": exc_info,
            }
        ),
    )

    coordinator_coverage.publish_repository_coverage(
        builder=SimpleNamespace(),
        run_state=run_state,
        repo_state=repo_state,
        repo_path=repo,
        include_graph_counts=True,
        include_content_counts=True,
    )

    assert len(upserts) == 1
    assert events == [
        {
            "event_name": "indexing.repository_coverage.published",
            "extra_keys": {
                "run_id": "run-123",
                "repo_id": "repository:repo-a",
                "repo_name": "repo-a",
                "discovered_file_count": 20,
                "graph_recursive_file_count": 12,
                "content_file_count": 7,
                "content_entity_count": 42,
                "graph_gap_count": 8,
                "content_gap_count": 5,
                "phase": "completed",
                "status": "completed",
                "finalization_status": "completed",
            },
            "exc_info": None,
        }
    ]
