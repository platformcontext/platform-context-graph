"""Unit tests for graph-builder indexing execution helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from platform_context_graph.collectors.git.finalize import finalize_index_batch
from platform_context_graph.collectors.git.execution import build_graph_from_path_async
from platform_context_graph.collectors.git.parse_execution import (
    parse_repository_snapshot_async,
)


class _NullSpan:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeObservability:
    def __init__(self) -> None:
        self.spans: list[tuple[str, dict[str, object]]] = []

    def start_span(self, name: str, *, attributes: dict[str, object] | None = None):
        self.spans.append((name, dict(attributes or {})))
        return _NullSpan()


def test_finalize_index_batch_streams_committed_repo_file_data() -> None:
    """Finalize should stream file data from committed repo paths."""
    recorded: dict[str, object] = {}
    load_calls: list[Path] = []

    def _record_inheritance(file_data: object, imports_map: object) -> None:
        recorded["inheritance"] = (list(file_data), imports_map)

    def _record_function_calls(
        file_data: object, imports_map: object
    ) -> dict[str, float]:
        recorded["function_calls"] = (list(file_data), imports_map)
        return {"total_duration_seconds": 0.5}

    def _record_sql_relationships(file_data: object) -> dict[str, int]:
        recorded["sql_relationships"] = list(file_data)
        return {"has_column_edges": 1}

    def _record_infra_links(file_data: object) -> None:
        recorded["infra_links"] = list(file_data)

    builder = SimpleNamespace(
        _create_all_inheritance_links=_record_inheritance,
        _create_all_function_calls=_record_function_calls,
        _create_all_sql_relationships=_record_sql_relationships,
        _create_all_infra_links=_record_infra_links,
        _materialize_workloads=lambda: recorded.setdefault("workloads", True),
        _resolve_repository_relationships=lambda committed_repo_paths, run_id=None: recorded.setdefault(
            "relationships",
            (list(committed_repo_paths), run_id),
        ),
    )

    finalize_index_batch(
        builder,
        committed_repo_paths=[Path("/tmp/example")],
        iter_snapshot_file_data_fn=lambda repo_path: (
            load_calls.append(repo_path)
            or iter([{"path": "/tmp/example/main.py", "functions": []}])
        ),
        merged_imports_map={"foo": ["bar"]},
        info_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert recorded["inheritance"] == (
        [{"path": "/tmp/example/main.py", "functions": []}],
        {"foo": ["bar"]},
    )
    assert recorded["function_calls"] == (
        [{"path": "/tmp/example/main.py", "functions": []}],
        {"foo": ["bar"]},
    )
    assert recorded["infra_links"] == [
        {"path": "/tmp/example/main.py", "functions": []}
    ]
    assert recorded["sql_relationships"] == [
        {"path": "/tmp/example/main.py", "functions": []}
    ]
    assert recorded["workloads"] is True
    assert recorded["relationships"] == ([Path("/tmp/example")], None)
    assert load_calls == [
        Path("/tmp/example"),
        Path("/tmp/example"),
        Path("/tmp/example"),
        Path("/tmp/example"),
    ]


@pytest.mark.asyncio
async def test_parse_repository_snapshot_falls_back_to_threaded_mode_without_executor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The feature flag alone should not claim multiprocess execution."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "alpha.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    fake_observability = _FakeObservability()
    messages: list[str] = []

    monkeypatch.setenv("PCG_REPO_FILE_PARSE_MULTIPROCESS", "true")
    monkeypatch.setattr(
        "platform_context_graph.collectors.git.parse_execution.get_observability",
        lambda: fake_observability,
    )

    async def _sleep(_seconds: float) -> None:
        return None

    builder = SimpleNamespace(
        _pre_scan_for_imports=lambda _files: {},
        parse_file=lambda *_args, **_kwargs: {
            "path": str(file_path),
            "functions": [],
        },
        job_manager=SimpleNamespace(update_job=lambda *_args, **_kwargs: None),
    )

    snapshot = await parse_repository_snapshot_async(
        builder,
        repo_path,
        [file_path],
        is_dependency=False,
        job_id=None,
        asyncio_module=SimpleNamespace(sleep=_sleep),
        info_logger_fn=messages.append,
        progress_callback=None,
        get_observability_fn=lambda: fake_observability,
    )

    assert snapshot.file_count == 1
    assert snapshot.file_data[0]["path"] == str(file_path)
    assert fake_observability.spans[0][1]["pcg.index.file_parse_strategy"] == "threaded"
    assert any("falling back to the threaded path" in message for message in messages)


@pytest.mark.asyncio
async def test_parse_repository_snapshot_defaults_to_threaded_strategy_when_flag_is_off(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The default parse path should stay in-process when the feature flag is off."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "alpha.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    fake_observability = _FakeObservability()
    messages: list[str] = []

    monkeypatch.delenv("PCG_REPO_FILE_PARSE_MULTIPROCESS", raising=False)
    monkeypatch.setattr(
        "platform_context_graph.collectors.git.parse_execution.get_observability",
        lambda: fake_observability,
    )

    async def _sleep(_seconds: float) -> None:
        return None

    builder = SimpleNamespace(
        _pre_scan_for_imports=lambda _files: {},
        parse_file=lambda *_args, **_kwargs: {
            "path": str(file_path),
            "functions": [],
        },
        job_manager=SimpleNamespace(update_job=lambda *_args, **_kwargs: None),
    )

    snapshot = await parse_repository_snapshot_async(
        builder,
        repo_path,
        [file_path],
        is_dependency=False,
        job_id=None,
        asyncio_module=SimpleNamespace(sleep=_sleep),
        info_logger_fn=messages.append,
        progress_callback=None,
        get_observability_fn=lambda: fake_observability,
    )

    assert snapshot.file_count == 1
    assert snapshot.file_data[0]["path"] == str(file_path)
    assert fake_observability.spans[0][0] == "pcg.index.parse_repository"
    assert fake_observability.spans[0][1]["pcg.index.file_parse_strategy"] == "threaded"
    assert not any("multiprocess parse skeleton" in message for message in messages)


def test_finalize_index_batch_logs_stage_timings(monkeypatch) -> None:
    """Finalize should emit per-stage timing diagnostics for large repos."""

    messages: list[str] = []
    stages: list[str] = []
    monotonic_values = iter(
        [
            10.0,
            10.0,
            11.5,
            11.5,
            14.0,
            14.0,
            14.0,
            14.0,
            14.2,
            14.2,
            15.0,
            15.0,
            15.0,
            15.0,
        ]
    )
    monkeypatch.setattr(
        "platform_context_graph.collectors.git.finalize.time.monotonic",
        lambda: next(monotonic_values),
    )

    builder = SimpleNamespace(
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_function_calls=lambda *_args, **_kwargs: {
            "total_duration_seconds": 0.0
        },
        _create_all_sql_relationships=lambda *_args, **_kwargs: {
            "has_column_edges": 1
        },
        _create_all_infra_links=lambda *_args, **_kwargs: None,
        _materialize_workloads=lambda: None,
        _resolve_repository_relationships=lambda *_args, **_kwargs: {
            "resolved_relationships": 3,
        },
    )

    result = finalize_index_batch(
        builder,
        committed_repo_paths=[Path("/tmp/example")],
        iter_snapshot_file_data_fn=lambda _repo_path: iter(
            [{"path": "/tmp/example/main.py", "functions": []}]
        ),
        merged_imports_map={},
        info_logger_fn=messages.append,
        stage_progress_callback=stages.append,
    )

    assert result.stage_timings == pytest.approx(
        {
            "inheritance": 1.5,
            "function_calls": 2.5,
            "sql_relationships": 0.0,
            "infra_links": 0.2,
            "workloads": 0.8,
            "relationship_resolution": 0.0,
        }
    )
    assert stages == [
        "inheritance",
        "function_calls",
        "sql_relationships",
        "infra_links",
        "workloads",
        "relationship_resolution",
    ]
    assert any("Finalization timings:" in message for message in messages)
    assert result.stage_details == {
        "function_calls": {"total_duration_seconds": 0.0},
        "sql_relationships": {"has_column_edges": 1},
        "relationship_resolution": {"resolved_relationships": 3},
    }


def test_finalize_index_batch_raises_when_committed_repo_file_data_is_missing() -> None:
    """Finalization should fail fast when committed repo file data cannot be loaded."""

    builder = SimpleNamespace(
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_function_calls=lambda *_args, **_kwargs: {},
        _create_all_sql_relationships=lambda *_args, **_kwargs: {},
        _create_all_infra_links=lambda *_args, **_kwargs: None,
        _materialize_workloads=lambda: None,
        _resolve_repository_relationships=lambda *_args, **_kwargs: None,
    )

    with pytest.raises(FileNotFoundError, match="Missing file data snapshot"):
        finalize_index_batch(
            builder,
            committed_repo_paths=[Path("/tmp/example")],
            iter_snapshot_file_data_fn=lambda _repo_path: None,
            merged_imports_map={},
            info_logger_fn=lambda *_args, **_kwargs: None,
        )


@pytest.mark.asyncio
async def test_parse_repository_snapshot_logs_prescan_progress_and_slow_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Repo parsing should emit useful telemetry while preserving parse output."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_paths = [
        repo_path / "alpha.py",
        repo_path / "beta.py",
        repo_path / "gamma.py",
    ]
    for path in file_paths:
        path.write_text("print('ok')\n", encoding="utf-8")

    class _FakeClock:
        def __init__(self) -> None:
            self.current = 0.0

        def monotonic(self) -> float:
            return self.current

        def advance(self, seconds: float) -> None:
            self.current += seconds

    clock = _FakeClock()
    messages: list[str] = []
    progress_files: list[str] = []
    job_updates: list[dict[str, str]] = []
    parse_durations = {
        "alpha.py": 0.2,
        "beta.py": 1.6,
        "gamma.py": 0.3,
    }

    def _pre_scan_for_imports(repo_files: list[Path]) -> dict[str, list[str]]:
        assert repo_files == file_paths
        clock.advance(2.0)
        return {"alpha": ["beta"]}

    def _parse_file(
        repo_root: Path, file_path: Path, is_dependency: bool
    ) -> dict[str, object]:
        assert repo_root == repo_path.resolve()
        assert is_dependency is False
        clock.advance(parse_durations[file_path.name])
        return {"path": str(file_path), "functions": []}

    builder = SimpleNamespace(
        _pre_scan_for_imports=_pre_scan_for_imports,
        parse_file=_parse_file,
        job_manager=SimpleNamespace(
            update_job=lambda _job_id, **kwargs: job_updates.append(kwargs)
        ),
    )

    async def _sleep(_seconds: float) -> None:
        return None

    snapshot = await parse_repository_snapshot_async(
        builder,
        repo_path,
        file_paths,
        is_dependency=False,
        job_id="job-123",
        asyncio_module=SimpleNamespace(sleep=_sleep),
        info_logger_fn=messages.append,
        progress_callback=lambda **kwargs: progress_files.append(
            kwargs["current_file"]
        ),
        repo_parse_progress_min_files=1,
        repo_parse_progress_target_steps=2,
        slow_parse_file_threshold_seconds=1.0,
        time_monotonic_fn=clock.monotonic,
    )

    assert snapshot.file_count == 3
    assert len(snapshot.file_data) == 3
    assert snapshot.imports_map == {"alpha": ["beta"]}
    assert progress_files == [str(path.resolve()) for path in file_paths]
    assert any(
        "Pre-scanning repo repo (3 files) for imports map..." in message
        for message in messages
    )
    assert any("Pre-scan repo repo done in 2.0s" in message for message in messages)
    assert any("Repo repo parse progress: 1/3 files" in message for message in messages)
    assert any(
        "Slow parse file in repo repo: beta.py took 1.6s" in message
        for message in messages
    )
    assert any(
        "Slowest parse files in repo repo: beta.py(1.6s)" in message
        for message in messages
    )
    assert any(
        "Finished repo repo (3 parsed files) in 4.1s" in message for message in messages
    )
    assert job_updates == [
        {"current_file": str(file_paths[0])},
        {"current_file": str(file_paths[1])},
        {"current_file": str(file_paths[2])},
    ]


@pytest.mark.asyncio
async def test_parse_repository_snapshot_does_not_sleep_away_large_repo_time(
    tmp_path: Path,
) -> None:
    """Cooperative yielding should not inject positive delay per parsed file."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_paths = [repo_path / f"file_{index}.py" for index in range(3)]
    for path in file_paths:
        path.write_text("print('ok')\n", encoding="utf-8")

    sleep_calls: list[float] = []

    async def _sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    builder = SimpleNamespace(
        _pre_scan_for_imports=lambda _files: {},
        parse_file=lambda *_args, **_kwargs: {"path": "ok", "functions": []},
        job_manager=SimpleNamespace(update_job=lambda *_args, **_kwargs: None),
    )

    await parse_repository_snapshot_async(
        builder,
        repo_path,
        file_paths,
        is_dependency=False,
        job_id=None,
        asyncio_module=SimpleNamespace(sleep=_sleep),
        info_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert sleep_calls
    assert max(sleep_calls) == 0.0


@pytest.mark.asyncio
async def test_parse_repository_snapshot_can_parse_repo_files_concurrently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Repo parsing should support opt-in file concurrency while keeping order."""

    monkeypatch.setenv("PCG_REPO_FILE_PARSE_CONCURRENCY", "2")
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_paths = [repo_path / f"file_{index}.py" for index in range(3)]
    for path in file_paths:
        path.write_text("print('ok')\n", encoding="utf-8")

    inflight = 0
    max_inflight = 0
    inflight_lock = threading.Lock()
    parse_durations = {
        "file_0.py": 0.08,
        "file_1.py": 0.01,
        "file_2.py": 0.01,
    }

    def _parse_file(
        _repo_root: Path, file_path: Path, _is_dependency: bool
    ) -> dict[str, object]:
        nonlocal inflight, max_inflight
        with inflight_lock:
            inflight += 1
            max_inflight = max(max_inflight, inflight)
        time.sleep(parse_durations[file_path.name])
        with inflight_lock:
            inflight -= 1
        return {"path": str(file_path), "functions": []}

    builder = SimpleNamespace(
        _pre_scan_for_imports=lambda _files: {},
        parse_file=_parse_file,
        job_manager=SimpleNamespace(update_job=lambda *_args, **_kwargs: None),
    )

    snapshot = await parse_repository_snapshot_async(
        builder,
        repo_path,
        file_paths,
        is_dependency=False,
        job_id=None,
        asyncio_module=asyncio,
        info_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert max_inflight >= 2
    assert [Path(item["path"]).name for item in snapshot.file_data] == [
        path.name for path in file_paths
    ]


@pytest.mark.asyncio
async def test_build_graph_from_path_async_caches_repo_display_name_per_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Legacy indexing should compute each repo display name only once per repo."""

    repo_path = tmp_path / "boatsgroup" / "repo"
    repo_path.mkdir(parents=True)
    first_file = repo_path / "alpha.py"
    second_file = repo_path / "beta.py"
    first_file.write_text("print('a')\n", encoding="utf-8")
    second_file.write_text("print('b')\n", encoding="utf-8")

    display_calls: list[Path] = []
    builder = SimpleNamespace(
        driver=SimpleNamespace(),
        job_manager=SimpleNamespace(update_job=lambda *_args, **_kwargs: None),
        add_repository_to_graph=lambda *_args, **_kwargs: None,
        _pre_scan_for_imports=lambda _files: {},
        parse_file=lambda _repo, file_path, _dep: {
            "path": str(file_path),
            "functions": [],
        },
        add_file_to_graph=lambda *_args, **_kwargs: None,
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_function_calls=lambda *_args, **_kwargs: None,
        _create_all_infra_links=lambda *_args, **_kwargs: None,
        _materialize_workloads=lambda: None,
    )

    async def _sleep(_seconds: float) -> None:
        return None

    await build_graph_from_path_async(
        builder,
        repo_path,
        is_dependency=False,
        job_id=None,
        asyncio_module=SimpleNamespace(sleep=_sleep),
        datetime_cls=SimpleNamespace(now=lambda *_args, **_kwargs: None),
        debug_log_fn=lambda *_args, **_kwargs: None,
        error_logger_fn=lambda *_args, **_kwargs: None,
        get_config_value_fn=lambda _key: None,
        info_logger_fn=lambda *_args, **_kwargs: None,
        pathspec_module=SimpleNamespace(),
        warning_logger_fn=lambda *_args, **_kwargs: None,
        job_status_enum=SimpleNamespace(RUNNING="running"),
        repository_display_name_fn=lambda path: display_calls.append(path)
        or "boatsgroup/repo",
        resolve_repository_file_sets_fn=lambda *_args, **_kwargs: {
            repo_path.resolve(): [first_file, second_file]
        },
    )

    assert display_calls == [repo_path.resolve()]
