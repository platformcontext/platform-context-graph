"""Tests for MCP indexing handler ownership boundaries."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.core.jobs import JobStatus
from platform_context_graph.mcp.tools.handlers import indexing


def test_add_code_to_graph_launches_go_bootstrap_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Directory indexing should schedule the Go bootstrap runtime, not Python parsing."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    graph_builder = SimpleNamespace(
        estimate_processing_time=lambda path: (12, 3.5),
        build_graph_from_path_async=lambda *_args, **_kwargs: None,
    )
    updates: list[tuple[str, dict[str, object]]] = []
    created_jobs: list[tuple[str, bool]] = []

    class RecordingJobManager:
        def create_job(self, path: str, is_dependency: bool = False) -> str:
            created_jobs.append((path, is_dependency))
            return "job-123"

        def update_job(self, job_id: str, **kwargs) -> None:
            updates.append((job_id, kwargs))

    go_index_calls: list[dict[str, object]] = []

    class InlineThread:
        def __init__(self, *, target, daemon: bool = False) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(indexing.threading, "Thread", InlineThread)
    monkeypatch.setattr(
        indexing,
        "run_go_bootstrap_index",
        lambda *args, **kwargs: go_index_calls.append(
            {"args": args, "kwargs": kwargs}
        ),
    )
    monkeypatch.setattr(
        indexing,
        "debug_log",
        lambda *_args, **_kwargs: None,
    )

    result = indexing.add_code_to_graph(
        graph_builder,
        RecordingJobManager(),
        None,
        lambda: {"repositories": []},
        path=str(repo_path),
    )

    assert result["success"] is True
    assert result["job_id"] == "job-123"
    assert created_jobs == [(str(repo_path.resolve()), False)]
    assert go_index_calls == [
        {
            "args": (repo_path.resolve(),),
            "kwargs": {"force": False},
        }
    ]
    assert updates[0] == (
        "job-123",
        {"total_files": 12, "estimated_duration": 3.5},
    )
    assert updates[1][0] == "job-123"
    assert updates[1][1]["status"] is JobStatus.RUNNING
    assert isinstance(updates[1][1]["start_time"], datetime)
    assert updates[2][0] == "job-123"
    assert updates[2][1]["status"] is JobStatus.COMPLETED
    assert isinstance(updates[2][1]["end_time"], datetime)


def test_add_package_to_graph_launches_go_bootstrap_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Package indexing should schedule the Go bootstrap runtime with dependency metadata."""

    package_path = tmp_path / "node_modules" / "@scope" / "service-lib"
    package_path.mkdir(parents=True)

    graph_builder = SimpleNamespace(
        estimate_processing_time=lambda path: (4, 1.25),
        build_graph_from_path_async=lambda *_args, **_kwargs: None,
    )
    updates: list[tuple[str, dict[str, object]]] = []
    created_jobs: list[tuple[str, bool]] = []

    class RecordingJobManager:
        def create_job(self, path: str, is_dependency: bool = False) -> str:
            created_jobs.append((path, is_dependency))
            return "job-456"

        def update_job(self, job_id: str, **kwargs) -> None:
            updates.append((job_id, kwargs))

    go_index_calls: list[dict[str, object]] = []

    class InlineThread:
        def __init__(self, *, target, daemon: bool = False) -> None:
            self._target = target
            self.daemon = daemon

        def start(self) -> None:
            self._target()

    monkeypatch.setattr(indexing.threading, "Thread", InlineThread)
    monkeypatch.setattr(
        indexing,
        "get_local_package_path",
        lambda package_name, language: str(package_path)
        if (package_name, language) == ("@scope/service-lib", "typescript")
        else None,
    )
    monkeypatch.setattr(indexing.os.path, "exists", lambda path: Path(path).exists())
    monkeypatch.setattr(
        indexing,
        "run_go_bootstrap_index",
        lambda *args, **kwargs: go_index_calls.append(
            {"args": args, "kwargs": kwargs}
        ),
    )
    monkeypatch.setattr(indexing, "debug_log", lambda *_args, **_kwargs: None)

    result = indexing.add_package_to_graph(
        graph_builder,
        RecordingJobManager(),
        None,
        lambda: {"repositories": []},
        package_name="@scope/service-lib",
        language="typescript",
    )

    assert result["success"] is True
    assert result["job_id"] == "job-456"
    assert created_jobs == [(str(package_path), True)]
    assert go_index_calls == [
        {
            "args": (package_path.resolve(),),
            "kwargs": {
                "force": False,
                "is_dependency": True,
                "package_name": "@scope/service-lib",
                "language": "typescript",
            },
        }
    ]
    assert updates[0] == (
        "job-456",
        {"total_files": 4, "estimated_duration": 1.25},
    )
    assert updates[1][0] == "job-456"
    assert updates[1][1]["status"] is JobStatus.RUNNING
    assert isinstance(updates[1][1]["start_time"], datetime)
    assert updates[2][0] == "job-456"
    assert updates[2][1]["status"] is JobStatus.COMPLETED
    assert isinstance(updates[2][1]["end_time"], datetime)
