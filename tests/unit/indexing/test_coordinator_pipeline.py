"""Unit tests for pipeline deadlock prevention and failure handling."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "src" / "platform_context_graph"


def _load_module(module_name: str, module_path: Path) -> ModuleType:
    """Load one module from source without importing package side effects."""

    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules.pop(module_name, None)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_pipeline_modules() -> tuple[ModuleType, ModuleType]:
    """Load coordinator modules with a minimal package skeleton."""

    try:
        return (
            importlib.import_module(
                "platform_context_graph.indexing.coordinator_models"
            ),
            importlib.import_module(
                "platform_context_graph.indexing.coordinator_pipeline"
            ),
        )
    except ImportError:
        module_names = (
            "platform_context_graph",
            "platform_context_graph.indexing",
            "platform_context_graph.tools",
            "platform_context_graph.collectors.git.indexing",
            "platform_context_graph.indexing.coordinator_models",
            "platform_context_graph.indexing.coordinator_pipeline",
        )
        original_modules = {
            module_name: sys.modules.get(module_name) for module_name in module_names
        }
        try:
            platform_pkg = ModuleType("platform_context_graph")
            platform_pkg.__path__ = [str(PACKAGE_ROOT)]
            sys.modules["platform_context_graph"] = platform_pkg

            indexing_pkg = ModuleType("platform_context_graph.indexing")
            indexing_pkg.__path__ = [str(PACKAGE_ROOT / "indexing")]
            sys.modules["platform_context_graph.indexing"] = indexing_pkg

            tools_pkg = ModuleType("platform_context_graph.tools")
            tools_pkg.__path__ = [str(PACKAGE_ROOT / "tools")]
            sys.modules["platform_context_graph.tools"] = tools_pkg

            _load_module(
                "platform_context_graph.collectors.git.indexing",
                PACKAGE_ROOT / "collectors" / "git" / "indexing.py",
            )
            models = _load_module(
                "platform_context_graph.indexing.coordinator_models",
                PACKAGE_ROOT / "indexing" / "coordinator_models.py",
            )
            pipeline = _load_module(
                "platform_context_graph.indexing.coordinator_pipeline",
                PACKAGE_ROOT / "indexing" / "coordinator_pipeline.py",
            )
        finally:
            for module_name, original_module in original_modules.items():
                if original_module is None:
                    sys.modules.pop(module_name, None)
                else:
                    sys.modules[module_name] = original_module
        return models, pipeline


MODELS, PIPELINE = _load_pipeline_modules()
IndexRunState = MODELS.IndexRunState
RepositoryRunState = MODELS.RepositoryRunState
RepositorySnapshot = MODELS.RepositorySnapshot
RepositorySnapshotMetadata = MODELS.RepositorySnapshotMetadata
process_repository_snapshots = PIPELINE.process_repository_snapshots
finalize_repository_batch = PIPELINE.finalize_repository_batch


def _make_run_state(repo_paths: list[Path]) -> IndexRunState:
    """Build a minimal IndexRunState with pending repositories."""
    return IndexRunState(
        run_id="test-run",
        root_path=str(repo_paths[0].parent.resolve()) if repo_paths else "/tmp",
        family="index",
        source="manual",
        discovery_signature="sig",
        is_dependency=False,
        status="running",
        finalization_status="pending",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        repositories={
            str(p.resolve()): RepositoryRunState(repo_path=str(p.resolve()))
            for p in repo_paths
        },
    )


@contextmanager
def _span_scope(*_args, **_kwargs):
    yield SimpleNamespace(record_exception=lambda _exc: None)


def _noop(**_kwargs):
    pass


def _publish_coverage(**_kwargs):
    pass


def _telemetry():
    return SimpleNamespace(
        start_span=_span_scope,
        record_index_repositories=_noop,
        record_index_repository_duration=_noop,
    )


async def _run_pipeline(
    repo_paths: list[Path],
    repo_file_sets: dict[Path, list[Path]],
    parse_fn,
    commit_fn=None,
    warning_logger_fn=None,
    parse_worker_count: int = 4,
    telemetry=None,
    asyncio_module=asyncio,
):
    """Drive process_repository_snapshots with minimal stubs."""
    run_state = _make_run_state(repo_paths)
    warnings: list[str] = []

    def _capture_warning(msg):
        warnings.append(msg)

    committed_repo_paths, merged, _ = await process_repository_snapshots(
        builder=SimpleNamespace(),
        run_state=run_state,
        repo_paths=repo_paths,
        repo_file_sets=repo_file_sets,
        resumed=False,
        is_dependency=False,
        job_id=None,
        component="test",
        family="index",
        source="manual",
        asyncio_module=asyncio_module,
        info_logger_fn=lambda *_a, **_kw: None,
        warning_logger_fn=warning_logger_fn or _capture_warning,
        parse_worker_count_fn=lambda: parse_worker_count,
        index_queue_depth_fn=lambda _w: 8,
        parse_repository_snapshot_async_fn=parse_fn,
        commit_repository_snapshot_fn=commit_fn or (lambda *_a, **_kw: None),
        iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
        load_snapshot_metadata_fn=lambda *_a: None,
        snapshot_file_data_exists_fn=lambda *_a: False,
        save_snapshot_metadata_fn=lambda *_a: None,
        save_snapshot_file_data_fn=lambda *_a: None,
        persist_run_state_fn=lambda _s: None,
        record_checkpoint_metric_fn=_noop,
        update_pending_repository_gauge_fn=_noop,
        publish_runtime_progress_fn=_noop,
        publish_run_repository_coverage_fn=_publish_coverage,
        utc_now_fn=lambda: "2026-01-01T00:00:00Z",
        telemetry=telemetry or _telemetry(),
    )
    return committed_repo_paths, merged, run_state, warnings


def test_pipeline_records_repository_stage_telemetry_for_resumed_parse(
    tmp_path: Path,
) -> None:
    """Parse-stage telemetry should expose repository span attrs and lifecycle hooks."""

    repo = tmp_path / "resumed-repo"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    run_state = _make_run_state([repo])
    run_state.repositories[str(repo.resolve())].status = "running"

    parse_repo_spans: list[tuple[str, str | None, dict[str, object]]] = []
    repository_events: list[dict[str, object]] = []
    duration_events: list[dict[str, object]] = []

    @contextmanager
    def _span_scope(name: str, *, component: str | None = None, attributes=None):
        parse_repo_spans.append((name, component, dict(attributes or {})))
        yield SimpleNamespace(record_exception=lambda _exc: None)

    telemetry = SimpleNamespace(
        start_span=_span_scope,
        record_index_repositories=lambda **kwargs: repository_events.append(kwargs),
        record_index_repository_duration=lambda **kwargs: duration_events.append(
            kwargs
        ),
    )

    async def parse_snapshot(_builder, repo_path, repo_files, **_kwargs):
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[{"path": str(repo_files[0].resolve())}],
        )

    asyncio.run(
        process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=run_state,
            repo_paths=[repo],
            repo_file_sets={repo: [file_path]},
            resumed=True,
            is_dependency=False,
            job_id=None,
            component="ingester",
            family="index",
            source="filesystem",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_a, **_kw: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _w: 8,
            parse_repository_snapshot_async_fn=parse_snapshot,
            commit_repository_snapshot_fn=lambda *_a, **_kw: None,
            iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
            load_snapshot_metadata_fn=lambda *_a: None,
            snapshot_file_data_exists_fn=lambda *_a: False,
            save_snapshot_metadata_fn=lambda *_a: None,
            save_snapshot_file_data_fn=lambda *_a: None,
            persist_run_state_fn=lambda _state: None,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=_noop,
            publish_run_repository_coverage_fn=_publish_coverage,
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=telemetry,
        )
    )

    assert parse_repo_spans[0] == (
        "pcg.index.repository",
        "ingester",
        {
            "pcg.index.run_id": "test-run",
            "pcg.index.repo_path": str(repo.resolve()),
            "pcg.index.resume": True,
            "pcg.index.parse_strategy": "threaded",
            "pcg.index.parse_workers": 1,
        },
    )
    assert [name for name, _component, _attrs in parse_repo_spans[1:]] == [
        "pcg.index.repository.queue_wait",
        "pcg.index.repository.parse",
        "pcg.index.repository.commit_wait",
        "pcg.index.repository.commit",
    ]
    assert [event["phase"] for event in repository_events] == [
        "started",
        "resumed",
        "completed",
    ]
    assert [event["count"] for event in repository_events] == [1, 1, 1]
    assert duration_events[-1]["status"] == "completed"
    assert duration_events[-1]["component"] == "ingester"
    assert run_state.repositories[str(repo.resolve())].status == "completed"


def test_pipeline_completes_when_single_repo_fails(tmp_path: Path) -> None:
    """A single failing repo must not deadlock the pipeline."""
    repo = tmp_path / "bad-repo"
    repo.mkdir()
    (repo / "main.py").write_text("x", encoding="utf-8")
    repo_paths = [repo]
    repo_file_sets = {repo: [repo / "main.py"]}

    async def failing_parse(*_a, **_kw):
        raise RuntimeError("corrupt file")

    committed_repo_paths, _, run_state, _ = asyncio.run(
        _run_pipeline(repo_paths, repo_file_sets, failing_parse)
    )
    repo_state = run_state.repositories[str(repo.resolve())]
    assert repo_state.status == "failed"
    assert "corrupt file" in repo_state.error
    assert committed_repo_paths == []


def test_pipeline_continues_after_one_repo_fails(tmp_path: Path) -> None:
    """When one of two repos fails, the other should still be parsed and committed."""
    good_repo = tmp_path / "good-repo"
    bad_repo = tmp_path / "bad-repo"
    good_repo.mkdir()
    bad_repo.mkdir()
    (good_repo / "main.py").write_text("ok", encoding="utf-8")
    (bad_repo / "main.py").write_text("bad", encoding="utf-8")

    repo_paths = [good_repo, bad_repo]
    repo_file_sets = {
        good_repo: [good_repo / "main.py"],
        bad_repo: [bad_repo / "main.py"],
    }
    committed: list[str] = []

    async def mixed_parse(_builder, repo_path, repo_files, **_kw):
        if repo_path.name == "bad-repo":
            raise RuntimeError("parse failure")
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[],
        )

    def track_commit(_builder, snapshot, **_kw):
        committed.append(snapshot.repo_path)

    committed_repo_paths, _, run_state, _ = asyncio.run(
        _run_pipeline(repo_paths, repo_file_sets, mixed_parse, commit_fn=track_commit)
    )

    good_state = run_state.repositories[str(good_repo.resolve())]
    bad_state = run_state.repositories[str(bad_repo.resolve())]
    assert good_state.status == "completed"
    assert bad_state.status == "failed"
    assert committed_repo_paths == [good_repo.resolve()]
    assert committed == [str(good_repo.resolve())]


def test_pipeline_does_not_set_running_before_semaphore(tmp_path: Path) -> None:
    """Repos waiting for the semaphore must not show 'running' in the checkpoint."""
    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "main.py").write_text("a", encoding="utf-8")
    (repo_b / "main.py").write_text("b", encoding="utf-8")

    repo_paths = [repo_a, repo_b]
    repo_file_sets = {
        repo_a: [repo_a / "main.py"],
        repo_b: [repo_b / "main.py"],
    }
    run_state = _make_run_state(repo_paths)

    # Capture status snapshots every time the checkpoint is persisted.
    status_snapshots: list[dict[str, str]] = []

    def capture_persist(_state):
        status_snapshots.append(
            {k: v.status for k, v in run_state.repositories.items()}
        )

    async def simple_parse(_builder, repo_path, repo_files, **_kw):
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[],
        )

    async def run():
        await process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=run_state,
            repo_paths=repo_paths,
            repo_file_sets=repo_file_sets,
            resumed=False,
            is_dependency=False,
            job_id=None,
            component="test",
            family="index",
            source="manual",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_a, **_kw: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            # Only 1 worker so repos must be serialized through the semaphore
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _w: 8,
            parse_repository_snapshot_async_fn=simple_parse,
            commit_repository_snapshot_fn=lambda *_a, **_kw: None,
            iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
            load_snapshot_metadata_fn=lambda *_a: None,
            snapshot_file_data_exists_fn=lambda *_a: False,
            save_snapshot_metadata_fn=lambda *_a: None,
            save_snapshot_file_data_fn=lambda *_a: None,
            persist_run_state_fn=capture_persist,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=_noop,
            publish_run_repository_coverage_fn=_publish_coverage,
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=_telemetry(),
        )

    asyncio.run(run())

    # With semaphore=1, no checkpoint snapshot should ever have both repos "running"
    for snap in status_snapshots:
        running_count = sum(1 for s in snap.values() if s == "running")
        assert (
            running_count <= 1
        ), f"Expected at most 1 repo running at a time, got {running_count}: {snap}"


def test_pipeline_limits_concurrent_repository_parses_to_worker_count(
    tmp_path: Path,
) -> None:
    """Repository parsing must honor the configured parse-worker bound."""

    repos = [tmp_path / f"repo-{idx}" for idx in range(4)]
    for repo in repos:
        repo.mkdir()
        (repo / "main.py").write_text("print('ok')\n", encoding="utf-8")

    repo_file_sets = {repo: [repo / "main.py"] for repo in repos}
    active_parses = 0
    max_active_parses = 0
    enough_started = asyncio.Event()
    release_parses = asyncio.Event()

    async def blocking_parse(_builder, repo_path, repo_files, **_kw):
        nonlocal active_parses
        nonlocal max_active_parses
        active_parses += 1
        max_active_parses = max(max_active_parses, active_parses)
        if active_parses >= 2:
            enough_started.set()
        try:
            await release_parses.wait()
        finally:
            active_parses -= 1
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[],
        )

    async def run() -> None:
        pipeline_task = asyncio.create_task(
            _run_pipeline(
                repos,
                repo_file_sets,
                blocking_parse,
                parse_worker_count=2,
            )
        )
        try:
            await asyncio.wait_for(enough_started.wait(), timeout=1.0)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert max_active_parses <= 2
        finally:
            release_parses.set()
            await pipeline_task

    asyncio.run(run())


def test_pipeline_marks_repo_failed_when_span_setup_raises(tmp_path: Path) -> None:
    """Escaped setup errors should be attributed to the repository as failures."""

    repo = tmp_path / "span-failure-repo"
    repo.mkdir()
    (repo / "main.py").write_text("x", encoding="utf-8")

    @contextmanager
    def raising_span(*_args, **_kwargs):
        raise RuntimeError("span enter failed")
        yield

    telemetry = SimpleNamespace(
        start_span=raising_span,
        record_index_repositories=_noop,
        record_index_repository_duration=_noop,
    )

    async def should_not_parse(*_a, **_kw):
        raise AssertionError("parse should not run when span setup fails")

    committed_repo_paths, _, run_state, warnings = asyncio.run(
        _run_pipeline(
            [repo],
            {repo: [repo / "main.py"]},
            should_not_parse,
            telemetry=telemetry,
        )
    )

    repo_state = run_state.repositories[str(repo.resolve())]
    assert committed_repo_paths == []
    assert repo_state.status == "failed"
    assert repo_state.error == "span enter failed"
    assert run_state.failed_repositories() == 1
    assert any("span enter failed" in warning for warning in warnings)


def test_pipeline_duration_excludes_time_waiting_for_parse_semaphore(
    tmp_path: Path, monkeypatch
) -> None:
    """Duration metrics should begin when the repo actually starts running."""

    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "main.py").write_text("a", encoding="utf-8")
    (repo_b / "main.py").write_text("b", encoding="utf-8")

    current_time = {"value": 0.0}
    durations: list[float] = []

    def fake_perf_counter() -> float:
        return current_time["value"]

    monkeypatch.setattr(PIPELINE.time, "perf_counter", fake_perf_counter)

    class TimingSemaphore:
        """Semaphore that advances the synthetic clock when the second repo starts."""

        def __init__(self, value: int) -> None:
            self._semaphore = asyncio.Semaphore(value)
            self._acquire_count = 0

        async def acquire(self) -> None:
            await self._semaphore.acquire()
            self._acquire_count += 1
            if self._acquire_count == 2:
                current_time["value"] += 5.0

        def release(self) -> None:
            self._semaphore.release()

        async def __aenter__(self):
            await self.acquire()
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self.release()

    telemetry = SimpleNamespace(
        start_span=_span_scope,
        record_index_repositories=_noop,
        record_index_repository_duration=lambda **kwargs: durations.append(
            kwargs["duration_seconds"]
        ),
    )

    timing_asyncio = SimpleNamespace(
        Queue=asyncio.Queue,
        create_task=asyncio.create_task,
        gather=asyncio.gather,
        sleep=asyncio.sleep,
        Semaphore=TimingSemaphore,
    )

    async def parse_snapshot(_builder, repo_path, repo_files, **_kw):
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[],
        )

    asyncio.run(
        _run_pipeline(
            [repo_a, repo_b],
            {
                repo_a: [repo_a / "main.py"],
                repo_b: [repo_b / "main.py"],
            },
            parse_snapshot,
            parse_worker_count=1,
            telemetry=telemetry,
            asyncio_module=timing_asyncio,
        )
    )

    assert durations == [5.0, 0.0]


def test_pipeline_sentinel_delivered_on_all_tasks_failing(tmp_path: Path) -> None:
    """Even if every parse task fails, the pipeline must not hang."""
    repos = [tmp_path / f"repo-{i}" for i in range(3)]
    for r in repos:
        r.mkdir()
        (r / "f.py").write_text("x", encoding="utf-8")

    repo_file_sets = {r: [r / "f.py"] for r in repos}

    async def all_fail(*_a, **_kw):
        raise RuntimeError("boom")

    committed_repo_paths, _, run_state, _ = asyncio.run(
        _run_pipeline(repos, repo_file_sets, all_fail)
    )

    assert committed_repo_paths == []
    assert run_state.failed_repositories() == 3
    assert run_state.completed_repositories() == 0


def test_pipeline_tracks_repository_phase_transitions(tmp_path: Path) -> None:
    """Checkpoint state should show parsing and committing progress for a repo."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('a')\n", encoding="utf-8")
    repo_paths = [repo]
    repo_file_sets = {repo: [file_path]}
    run_state = _make_run_state(repo_paths)
    phase_snapshots: list[tuple[str | None, str | None, str | None, str | None]] = []

    def capture_persist(_state) -> None:
        repo_state = run_state.repositories[str(repo.resolve())]
        phase_snapshots.append(
            (
                repo_state.status,
                repo_state.phase,
                repo_state.current_file,
                repo_state.last_progress_at,
            )
        )

    async def parse_snapshot(_builder, repo_path, repo_files, **_kw):
        del repo_path
        progress_callback = _kw["progress_callback"]
        progress_callback(current_file=str(repo_files[0].resolve()))
        return RepositorySnapshot(
            repo_path=str(repo.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[],
        )

    asyncio.run(
        process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=run_state,
            repo_paths=repo_paths,
            repo_file_sets=repo_file_sets,
            resumed=False,
            is_dependency=False,
            job_id=None,
            component="test",
            family="index",
            source="manual",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_a, **_kw: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _w: 8,
            parse_repository_snapshot_async_fn=parse_snapshot,
            commit_repository_snapshot_fn=lambda *_a, **_kw: None,
            iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
            load_snapshot_metadata_fn=lambda *_a: None,
            snapshot_file_data_exists_fn=lambda *_a: False,
            save_snapshot_metadata_fn=lambda *_a: None,
            save_snapshot_file_data_fn=lambda *_a: None,
            persist_run_state_fn=capture_persist,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=_noop,
            publish_run_repository_coverage_fn=_publish_coverage,
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=_telemetry(),
        )
    )

    assert ("running", "parsing", None, "2026-01-01T00:00:00Z") in phase_snapshots
    assert (
        "running",
        "parsing",
        str(file_path.resolve()),
        "2026-01-01T00:00:00Z",
    ) in phase_snapshots
    assert (
        "commit_incomplete",
        "committing",
        None,
        "2026-01-01T00:00:00Z",
    ) in phase_snapshots

    repo_state = run_state.repositories[str(repo.resolve())]
    assert repo_state.phase == "completed"
    assert repo_state.current_file is None
    assert repo_state.last_progress_at == "2026-01-01T00:00:00Z"


def test_pipeline_tracks_commit_current_file_during_batch_heartbeats(
    tmp_path: Path,
) -> None:
    """Long commit batches should refresh current-file progress before commit ends."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('a')\n", encoding="utf-8")
    run_state = _make_run_state([repo])
    phase_snapshots: list[tuple[str | None, str | None, str | None]] = []

    def capture_persist(_state) -> None:
        repo_state = run_state.repositories[str(repo.resolve())]
        phase_snapshots.append(
            (
                repo_state.status,
                repo_state.phase,
                repo_state.current_file,
            )
        )

    async def parse_snapshot(_builder, repo_path, repo_files, **_kw):
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[
                {"path": str((repo_path / "a.py").resolve())},
                {"path": str((repo_path / "b.py").resolve())},
            ],
        )

    def commit_snapshot(_builder, _snapshot, **kwargs) -> None:
        progress_callback = kwargs["progress_callback"]
        progress_callback(
            processed_files=1,
            total_files=2,
            current_file=str((repo / "a.py").resolve()),
            committed=False,
        )
        progress_callback(
            processed_files=2,
            total_files=2,
            current_file=str((repo / "b.py").resolve()),
            committed=True,
        )

    asyncio.run(
        process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=run_state,
            repo_paths=[repo],
            repo_file_sets={repo: [file_path]},
            resumed=False,
            is_dependency=False,
            job_id=None,
            component="test",
            family="index",
            source="manual",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_a, **_kw: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _w: 8,
            parse_repository_snapshot_async_fn=parse_snapshot,
            commit_repository_snapshot_fn=commit_snapshot,
            iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
            load_snapshot_metadata_fn=lambda *_a: None,
            snapshot_file_data_exists_fn=lambda *_a: False,
            save_snapshot_metadata_fn=lambda *_a: None,
            save_snapshot_file_data_fn=lambda *_a: None,
            persist_run_state_fn=capture_persist,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=_noop,
            publish_run_repository_coverage_fn=_publish_coverage,
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=_telemetry(),
        )
    )

    assert (
        "commit_incomplete",
        "committing",
        str((repo / "a.py").resolve()),
    ) in phase_snapshots
    assert (
        "commit_incomplete",
        "committing",
        str((repo / "b.py").resolve()),
    ) in phase_snapshots


def test_pipeline_progress_heartbeats_do_not_overwrite_partial_coverage(
    tmp_path: Path, monkeypatch
) -> None:
    """Frequent runtime heartbeats must not publish zero-count coverage rows."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('a')\n", encoding="utf-8")
    run_state = _make_run_state([repo])

    runtime_statuses: list[str] = []
    coverage_calls: list[tuple[tuple[str, ...], bool, bool]] = []

    async def parse_snapshot(_builder, repo_path, _repo_files, **kwargs):
        progress_callback = kwargs["progress_callback"]
        progress_callback(current_file=str((repo_path / "main.py").resolve()))
        progress_callback(
            current_file=str((repo_path / "main.py").resolve()),
            force=True,
        )
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=2,
            imports_map={},
            file_data=[
                {"path": str((repo_path / "a.py").resolve())},
                {"path": str((repo_path / "b.py").resolve())},
            ],
        )

    def commit_snapshot(_builder, _snapshot, **kwargs) -> None:
        progress_callback = kwargs["progress_callback"]
        progress_callback(
            processed_files=1,
            total_files=2,
            current_file=str((repo / "a.py").resolve()),
            committed=False,
        )
        progress_callback(
            processed_files=2,
            total_files=2,
            current_file=str((repo / "b.py").resolve()),
            committed=True,
        )

    asyncio.run(
        process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=run_state,
            repo_paths=[repo],
            repo_file_sets={repo: [file_path]},
            resumed=False,
            is_dependency=False,
            job_id=None,
            component="test",
            family="index",
            source="manual",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_a, **_kw: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _w: 8,
            parse_repository_snapshot_async_fn=parse_snapshot,
            commit_repository_snapshot_fn=commit_snapshot,
            iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
            load_snapshot_metadata_fn=lambda *_a: None,
            snapshot_file_data_exists_fn=lambda *_a: False,
            save_snapshot_metadata_fn=lambda *_a, **_kw: None,
            save_snapshot_file_data_fn=lambda *_a, **_kw: None,
            persist_run_state_fn=lambda _state: None,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=lambda **kwargs: runtime_statuses.append(
                kwargs["status"]
            ),
            publish_run_repository_coverage_fn=lambda **kwargs: coverage_calls.append(
                (
                    tuple(str(path.resolve()) for path in kwargs["repo_paths"]),
                    kwargs["include_graph_counts"],
                    kwargs["include_content_counts"],
                )
            ),
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=_telemetry(),
        )
    )

    assert len(runtime_statuses) > len(coverage_calls)
    assert coverage_calls[:2] == [
        ((str(repo.resolve()),), False, False),
        ((str(repo.resolve()),), False, False),
    ]
    assert coverage_calls[2:] == [
        ((str(repo.resolve()),), True, True),
        ((str(repo.resolve()),), True, True),
    ]


def test_pipeline_commit_duration_tracks_commit_only(
    tmp_path: Path, monkeypatch
) -> None:
    """Commit timing should exclude parse time for hotspot diagnosis."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('a')\n", encoding="utf-8")
    current_time = {"value": 100.0}

    def fake_perf_counter() -> float:
        return current_time["value"]

    monkeypatch.setattr(PIPELINE.time, "perf_counter", fake_perf_counter)

    async def parse_snapshot(_builder, repo_path, repo_files, **_kw):
        current_time["value"] += 5.0
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[],
        )

    def commit_snapshot(_builder, _snapshot, **_kw) -> None:
        current_time["value"] += 0.25

    _, _, run_state, _ = asyncio.run(
        _run_pipeline(
            [repo],
            {repo: [file_path]},
            parse_snapshot,
            commit_fn=commit_snapshot,
        )
    )

    repo_state = run_state.repositories[str(repo.resolve())]
    assert repo_state.commit_duration_seconds == 0.25


def test_finalize_repository_batch_records_stage_timings(monkeypatch) -> None:
    """Successful finalization should persist stage timings for hotspot ranking."""

    repo_path = Path("/tmp/repo-a")
    run_state = _make_run_state([repo_path])
    run_state.repositories[str(repo_path.resolve())].status = "completed"
    persisted_states: list[tuple[str | None, dict[str, float]]] = []
    current_time = {"value": 50.0}
    timestamps = iter(
        [
            "2026-01-01T00:00:01Z",
            "2026-01-01T00:00:02Z",
            "2026-01-01T00:00:03Z",
            "2026-01-01T00:00:04Z",
            "2026-01-01T00:00:05Z",
        ]
    )

    def fake_perf_counter() -> float:
        return current_time["value"]

    monkeypatch.setattr(PIPELINE.time, "perf_counter", fake_perf_counter)

    def capture_persist(state) -> None:
        persisted_states.append(
            (
                state.finalization_current_stage,
                dict(state.finalization_stage_durations),
            )
        )

    def finalize_index_batch_fn(*_args, stage_progress_callback, **_kwargs):
        stage_progress_callback("inheritance")
        current_time["value"] += 1.5
        stage_progress_callback("function_calls")
        current_time["value"] += 3.0
        return {"inheritance": 1.5, "function_calls": 3.0}

    builder = SimpleNamespace(
        _last_call_relationship_metrics={
            "fallback_duration_seconds": 3.0,
            "exact_duration_seconds": 1.5,
        }
    )

    finalize_repository_batch(
        builder=builder,
        root_path=repo_path,
        run_state=run_state,
        repo_paths=[repo_path],
        committed_repo_paths=[],
        iter_snapshot_file_data_fn=lambda _repo_path: iter(()),
        merged_imports_map={},
        component="test",
        family="index",
        source="manual",
        info_logger_fn=lambda *_a, **_kw: None,
        error_logger_fn=lambda *_a, **_kw: None,
        finalize_index_batch_fn=finalize_index_batch_fn,
        persist_run_state_fn=capture_persist,
        delete_snapshots_fn=lambda *_a, **_kw: None,
        telemetry=_telemetry(),
        utc_now_fn=lambda: next(timestamps),
        publish_run_repository_coverage_fn=_publish_coverage,
        publish_runtime_progress_fn=_noop,
    )

    assert run_state.finalization_status == "completed"
    assert run_state.finalization_started_at == "2026-01-01T00:00:01Z"
    assert run_state.finalization_finished_at == "2026-01-01T00:00:04Z"
    assert run_state.finalization_duration_seconds == 4.5
    assert run_state.finalization_stage_durations == {
        "inheritance": 1.5,
        "function_calls": 3.0,
    }
    assert run_state.finalization_stage_details == {
        "function_calls": {
            "fallback_duration_seconds": 3.0,
            "exact_duration_seconds": 1.5,
        }
    }
    assert run_state.finalization_current_stage is None
    assert run_state.finalization_stage_started_at is None
    assert persisted_states == [
        (None, {}),
        ("inheritance", {}),
        ("function_calls", {}),
        (
            None,
            {
                "inheritance": 1.5,
                "function_calls": 3.0,
            },
        ),
    ]


def test_finalize_repository_batch_treats_commit_incomplete_as_blocking() -> None:
    """Finalization should not run while a repository remains commit-incomplete."""

    repo_path = Path("/tmp/repo-a")
    run_state = _make_run_state([repo_path])
    run_state.repositories[str(repo_path.resolve())].status = "commit_incomplete"
    persisted_statuses: list[tuple[str, str]] = []

    def capture_persist(state) -> None:
        persisted_statuses.append((state.status, state.finalization_status))

    finalize_repository_batch(
        builder=SimpleNamespace(),
        root_path=repo_path,
        run_state=run_state,
        repo_paths=[repo_path],
        committed_repo_paths=[],
        iter_snapshot_file_data_fn=lambda _repo_path: iter(()),
        merged_imports_map={},
        component="test",
        family="index",
        source="manual",
        info_logger_fn=lambda *_a, **_kw: None,
        error_logger_fn=lambda *_a, **_kw: None,
        finalize_index_batch_fn=lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("finalization should not run")
        ),
        persist_run_state_fn=capture_persist,
        delete_snapshots_fn=lambda *_a, **_kw: None,
        telemetry=_telemetry(),
        utc_now_fn=lambda: "2026-01-01T00:00:00Z",
        publish_run_repository_coverage_fn=_publish_coverage,
        publish_runtime_progress_fn=_noop,
    )

    assert run_state.status == "partial_failure"
    assert run_state.finalization_status == "pending"
    assert persisted_statuses == [("partial_failure", "pending")]


def test_finalize_repository_batch_logs_structured_deferred_event() -> None:
    """Deferred finalization should emit a structured lifecycle log."""

    repo_path = Path("/tmp/repo-a")
    run_state = _make_run_state([repo_path])
    run_state.repositories[str(repo_path.resolve())].status = "commit_incomplete"
    log_records: list[dict[str, object]] = []

    def capture_info(
        message: str,
        *,
        event_name: str | None = None,
        extra_keys: dict[str, object] | None = None,
        exc_info: object = None,
    ) -> None:
        log_records.append(
            {
                "message": message,
                "event_name": event_name,
                "extra_keys": dict(extra_keys or {}),
                "exc_info": exc_info,
            }
        )

    finalize_repository_batch(
        builder=SimpleNamespace(),
        root_path=repo_path,
        run_state=run_state,
        repo_paths=[repo_path],
        committed_repo_paths=[],
        iter_snapshot_file_data_fn=lambda _repo_path: iter(()),
        merged_imports_map={},
        component="test",
        family="index",
        source="manual",
        info_logger_fn=capture_info,
        error_logger_fn=lambda *_a, **_kw: None,
        finalize_index_batch_fn=lambda *_a, **_kw: (_ for _ in ()).throw(
            AssertionError("finalization should not run")
        ),
        persist_run_state_fn=lambda _state: None,
        delete_snapshots_fn=lambda *_a, **_kw: None,
        telemetry=_telemetry(),
        utc_now_fn=lambda: "2026-01-01T00:00:00Z",
        publish_run_repository_coverage_fn=_publish_coverage,
        publish_runtime_progress_fn=_noop,
    )

    assert log_records[-1]["event_name"] == "index.finalization.deferred"
    assert log_records[-1]["extra_keys"] == {
        "run_id": "test-run",
        "root_path": str(repo_path.resolve()),
        "repository_count": 1,
        "committed_count": 0,
        "blocking_repositories": 1,
    }
    assert log_records[-1]["exc_info"] is None


def test_finalize_repository_batch_logs_structured_failure_event() -> None:
    """Finalization failures should preserve structured exception context."""

    repo_path = Path("/tmp/repo-a")
    run_state = _make_run_state([repo_path])
    run_state.repositories[str(repo_path.resolve())].status = "completed"
    error_records: list[dict[str, object]] = []

    def capture_error(
        message: str,
        *,
        event_name: str | None = None,
        extra_keys: dict[str, object] | None = None,
        exc_info: object = None,
    ) -> None:
        error_records.append(
            {
                "message": message,
                "event_name": event_name,
                "extra_keys": dict(extra_keys or {}),
                "exc_info": exc_info,
            }
        )

    def finalize_index_batch_fn(*_args, **_kwargs):
        raise RuntimeError("boom")

    finalize_repository_batch(
        builder=SimpleNamespace(),
        root_path=repo_path,
        run_state=run_state,
        repo_paths=[repo_path],
        committed_repo_paths=[repo_path],
        iter_snapshot_file_data_fn=lambda _repo_path: iter(()),
        merged_imports_map={},
        component="test",
        family="index",
        source="manual",
        info_logger_fn=lambda *_a, **_kw: None,
        error_logger_fn=capture_error,
        finalize_index_batch_fn=finalize_index_batch_fn,
        persist_run_state_fn=lambda _state: None,
        delete_snapshots_fn=lambda *_a, **_kw: None,
        telemetry=_telemetry(),
        utc_now_fn=lambda: "2026-01-01T00:00:00Z",
        publish_run_repository_coverage_fn=_publish_coverage,
        publish_runtime_progress_fn=_noop,
    )

    assert error_records[-1]["event_name"] == "index.finalization.failed"
    assert error_records[-1]["extra_keys"] == {
        "run_id": "test-run",
        "root_path": str(repo_path.resolve()),
        "repository_count": 1,
        "blocking_repositories": 0,
    }
    assert isinstance(error_records[-1]["exc_info"], RuntimeError)


def test_finalize_repository_batch_persists_function_call_heartbeats() -> None:
    """Finalization heartbeats should keep the checkpoint state moving mid-stage."""

    repo_path = Path("/tmp/repo-a")
    run_state = _make_run_state([repo_path])
    run_state.repositories[str(repo_path.resolve())].status = "completed"
    persisted_states: list[tuple[str | None, dict[str, object]]] = []

    def capture_persist(state) -> None:
        details = dict(state.finalization_stage_details.get("function_calls", {}))
        persisted_states.append((state.finalization_current_stage, details))

    def finalize_index_batch_fn(*_args, stage_progress_callback, **_kwargs):
        stage_progress_callback("function_calls")
        stage_progress_callback(
            "function_calls",
            current_file="/tmp/repo-a/src/bootstrap.php",
            processed_files=1,
            total_files=2,
        )
        return {"function_calls": 3.0}

    finalize_repository_batch(
        builder=SimpleNamespace(),
        root_path=repo_path,
        run_state=run_state,
        repo_paths=[repo_path],
        committed_repo_paths=[],
        iter_snapshot_file_data_fn=lambda _repo_path: iter(()),
        merged_imports_map={},
        component="test",
        family="index",
        source="manual",
        info_logger_fn=lambda *_a, **_kw: None,
        error_logger_fn=lambda *_a, **_kw: None,
        finalize_index_batch_fn=finalize_index_batch_fn,
        persist_run_state_fn=capture_persist,
        delete_snapshots_fn=lambda *_a, **_kw: None,
        telemetry=_telemetry(),
        utc_now_fn=lambda: "2026-01-01T00:00:00Z",
        publish_run_repository_coverage_fn=_publish_coverage,
        publish_runtime_progress_fn=_noop,
    )

    assert persisted_states[2] == (
        "function_calls",
        {
            "current_file": "/tmp/repo-a/src/bootstrap.php",
            "processed_files": 1,
            "total_files": 2,
        },
    )


def test_finalize_repository_batch_publishes_lightweight_coverage_heartbeats() -> None:
    """Finalization heartbeats should refresh coverage without recounting graph/content."""

    repo_path = Path("/tmp/repo-a")
    run_state = _make_run_state([repo_path])
    run_state.repositories[str(repo_path.resolve())].status = "completed"
    coverage_calls: list[tuple[bool, bool, str | None]] = []

    def publish_coverage(**kwargs) -> None:
        coverage_calls.append(
            (
                kwargs["include_graph_counts"],
                kwargs["include_content_counts"],
                kwargs["run_state"].finalization_current_stage,
            )
        )

    def finalize_index_batch_fn(*_args, stage_progress_callback, **_kwargs):
        stage_progress_callback("function_calls")
        stage_progress_callback(
            "function_calls",
            current_file="/tmp/repo-a/src/bootstrap.php",
            processed_files=1,
            total_files=2,
        )
        return {"function_calls": 3.0}

    finalize_repository_batch(
        builder=SimpleNamespace(),
        root_path=repo_path,
        run_state=run_state,
        repo_paths=[repo_path],
        committed_repo_paths=[],
        iter_snapshot_file_data_fn=lambda _repo_path: iter(()),
        merged_imports_map={},
        component="test",
        family="index",
        source="manual",
        info_logger_fn=lambda *_a, **_kw: None,
        error_logger_fn=lambda *_a, **_kw: None,
        finalize_index_batch_fn=finalize_index_batch_fn,
        persist_run_state_fn=lambda _state: None,
        delete_snapshots_fn=lambda *_a, **_kw: None,
        telemetry=_telemetry(),
        utc_now_fn=lambda: "2026-01-01T00:00:00Z",
        publish_run_repository_coverage_fn=publish_coverage,
        publish_runtime_progress_fn=_noop,
    )

    assert (True, True, None) in coverage_calls
    assert (False, False, "function_calls") in coverage_calls


def test_pipeline_resumes_completed_repo_from_metadata_without_reloading_file_data(
    tmp_path: Path,
) -> None:
    """Completed repos should restore imports without loading heavyweight file data."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('a')\n", encoding="utf-8")
    run_state = _make_run_state([repo])
    run_state.repositories[str(repo.resolve())].status = "completed"

    async def should_not_parse(*_args, **_kwargs):
        raise AssertionError("completed repos should not be reparsed")

    committed_repo_paths, merged_imports_map, _ = asyncio.run(
        process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=run_state,
            repo_paths=[repo],
            repo_file_sets={repo: [file_path]},
            resumed=True,
            is_dependency=False,
            job_id=None,
            component="test",
            family="index",
            source="manual",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_a, **_kw: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _w: 8,
            parse_repository_snapshot_async_fn=should_not_parse,
            commit_repository_snapshot_fn=lambda *_a, **_kw: None,
            iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
            load_snapshot_metadata_fn=lambda *_a, **_kw: RepositorySnapshotMetadata(
                repo_path=str(repo.resolve()),
                file_count=1,
                imports_map={"module": [str(file_path.resolve())]},
            ),
            snapshot_file_data_exists_fn=lambda *_a, **_kw: True,
            save_snapshot_metadata_fn=lambda *_a, **_kw: None,
            save_snapshot_file_data_fn=lambda *_a, **_kw: None,
            persist_run_state_fn=lambda _state: None,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=_noop,
            publish_run_repository_coverage_fn=_publish_coverage,
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=_telemetry(),
        )
    )

    assert committed_repo_paths == [repo.resolve()]
    assert merged_imports_map == {"module": [str(file_path.resolve())]}


def test_pipeline_reparses_completed_repo_when_file_data_snapshot_is_missing(
    tmp_path: Path,
) -> None:
    """Resume should reparse completed repos when only lightweight metadata remains."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('a')\n", encoding="utf-8")
    run_state = _make_run_state([repo])
    repo_state = run_state.repositories[str(repo.resolve())]
    repo_state.status = "completed"

    parse_calls: list[Path] = []

    async def reparse_snapshot(_builder, repo_path, repo_files, **_kwargs):
        parse_calls.append(repo_path)
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={"module": [str(repo_files[0].resolve())]},
            file_data=[{"path": str(repo_files[0].resolve()), "functions": []}],
        )

    committed_repo_paths, merged_imports_map, _ = asyncio.run(
        process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=run_state,
            repo_paths=[repo],
            repo_file_sets={repo: [file_path]},
            resumed=True,
            is_dependency=False,
            job_id=None,
            component="test",
            family="index",
            source="manual",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_a, **_kw: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _w: 8,
            parse_repository_snapshot_async_fn=reparse_snapshot,
            commit_repository_snapshot_fn=lambda *_a, **_kw: None,
            iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
            load_snapshot_metadata_fn=lambda *_a, **_kw: RepositorySnapshotMetadata(
                repo_path=str(repo.resolve()),
                file_count=1,
                imports_map={"stale": ["/tmp/stale.py"]},
            ),
            snapshot_file_data_exists_fn=lambda *_a, **_kw: False,
            save_snapshot_metadata_fn=lambda *_a, **_kw: None,
            save_snapshot_file_data_fn=lambda *_a, **_kw: None,
            persist_run_state_fn=lambda _state: None,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=_noop,
            publish_run_repository_coverage_fn=_publish_coverage,
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=_telemetry(),
        )
    )

    assert parse_calls == [repo]
    assert repo_state.status == "completed"
    assert committed_repo_paths == [repo.resolve()]
    assert merged_imports_map == {"module": [str(file_path.resolve())]}


def test_pipeline_concurrent_commit_workers_complete_successfully(
    tmp_path: Path, monkeypatch
) -> None:
    """With PCG_COMMIT_WORKERS=2, multiple repos commit and the pipeline completes."""

    monkeypatch.setenv("PCG_COMMIT_WORKERS", "2")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")

    repos = [tmp_path / f"repo-{i}" for i in range(3)]
    for repo in repos:
        repo.mkdir()
        (repo / "main.py").write_text("print('ok')\n", encoding="utf-8")

    repo_file_sets = {repo: [repo / "main.py"] for repo in repos}

    async def parse_snapshot(_builder, repo_path, repo_files, **_kw):
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={repo_path.name: [str(repo_files[0].resolve())]},
            file_data=[],
        )

    # CW>1 uses commit_repository_snapshot_async with ProcessPoolExecutor.
    # Patch _sync_setup_repo since the test builder is a SimpleNamespace
    # that lacks the db_manager/driver attrs the real setup needs.
    with patch(
        "platform_context_graph.indexing.coordinator_async_commit._sync_setup_repo"
    ):
        committed_repo_paths, merged, run_state, _ = asyncio.run(
            _run_pipeline(
                repos,
                repo_file_sets,
                parse_snapshot,
                parse_worker_count=4,
            )
        )

    assert len(committed_repo_paths) == 3
    for repo in repos:
        assert run_state.repositories[str(repo.resolve())].status == "completed"
    # Verify imports from all repos were merged
    assert len(merged) == 3


def test_pipeline_concurrent_commit_workers_send_correct_sentinel_count(
    tmp_path: Path, monkeypatch
) -> None:
    """With PCG_COMMIT_WORKERS=2, two sentinels are sent so all consumers exit."""

    monkeypatch.setenv("PCG_COMMIT_WORKERS", "2")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")

    # Even with zero repos to parse, the pipeline must send N sentinels and
    # await N commit tasks without deadlocking.
    committed_repo_paths, merged, run_state, _ = asyncio.run(
        _run_pipeline(
            [],
            {},
            lambda *_a, **_kw: None,
            parse_worker_count=1,
        )
    )

    assert committed_repo_paths == []
    assert merged == {}


def test_pipeline_concurrent_commit_workers_overlap(
    tmp_path: Path, monkeypatch
) -> None:
    """With PCG_COMMIT_WORKERS=2, two repos should commit concurrently."""

    monkeypatch.setenv("PCG_COMMIT_WORKERS", "2")
    monkeypatch.setenv("NEO4J_URI", "bolt://localhost:7687")

    repo_a = tmp_path / "repo-a"
    repo_b = tmp_path / "repo-b"
    repo_a.mkdir()
    repo_b.mkdir()
    (repo_a / "main.py").write_text("a", encoding="utf-8")
    (repo_b / "main.py").write_text("b", encoding="utf-8")

    repos = [repo_a, repo_b]
    repo_file_sets = {
        repo_a: [repo_a / "main.py"],
        repo_b: [repo_b / "main.py"],
    }

    async def parse_snapshot(_builder, repo_path, repo_files, **_kw):
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[],
        )

    # CW>1 uses commit_repository_snapshot_async with ProcessPoolExecutor.
    # Patch _sync_setup_repo since the test builder lacks driver attrs.
    with patch(
        "platform_context_graph.indexing.coordinator_async_commit._sync_setup_repo"
    ):
        committed_repo_paths, _, run_state, _ = asyncio.run(
            _run_pipeline(
                repos,
                repo_file_sets,
                parse_snapshot,
                parse_worker_count=4,
            )
        )

    # Both repos should complete; the pipeline should not deadlock with 2 workers.
    assert len(committed_repo_paths) == 2
    assert run_state.repositories[str(repo_a.resolve())].status == "completed"
    assert run_state.repositories[str(repo_b.resolve())].status == "completed"


def test_pipeline_facts_first_emits_before_snapshot_clear_and_forwards_exact_result(
    tmp_path: Path,
) -> None:
    """Facts-first flow should emit before clearing file data and forward identity."""

    repo = tmp_path / "repo-a"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('a')\n", encoding="utf-8")

    emitted_snapshots: list[list[dict[str, object]]] = []
    forwarded_results: list[object] = []
    forwarded_progress_callbacks: list[object] = []
    forwarded_iter_fns: list[object] = []
    forwarded_repo_classes: list[str | None] = []
    merged_imports: dict[str, list[str]] = {}

    async def parse_snapshot(_builder, repo_path, repo_files, **_kw):
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={"helper": [str(repo_files[0].resolve())]},
            file_data=[
                {
                    "path": str(repo_files[0].resolve()),
                    "repo_path": str(repo_path.resolve()),
                    "lang": "python",
                    "functions": [{"name": "handler", "line_number": 1}],
                }
            ],
        )

    emission_result = SimpleNamespace(work_item_id="work-1", fact_count=2)

    def emit_snapshot_facts_fn(*, snapshot, **_kwargs):
        emitted_snapshots.append(list(snapshot.file_data))
        return emission_result

    def commit_snapshot(_builder, snapshot, **kwargs) -> None:
        forwarded_results.append(kwargs["fact_emission_result"])
        forwarded_progress_callbacks.append(kwargs["progress_callback"])
        forwarded_iter_fns.append(kwargs["iter_snapshot_file_data_batches_fn"])
        forwarded_repo_classes.append(kwargs["repo_class"])
        merged_imports.update(snapshot.imports_map)

    asyncio.run(
        process_repository_snapshots(
            builder=SimpleNamespace(),
            run_state=_make_run_state([repo]),
            repo_paths=[repo],
            repo_file_sets={repo: [file_path]},
            resumed=False,
            is_dependency=False,
            job_id=None,
            component="test",
            family="index",
            source="manual",
            asyncio_module=asyncio,
            info_logger_fn=lambda *_a, **_kw: None,
            warning_logger_fn=lambda *_a, **_kw: None,
            parse_worker_count_fn=lambda: 1,
            index_queue_depth_fn=lambda _w: 8,
            parse_repository_snapshot_async_fn=parse_snapshot,
            commit_repository_snapshot_fn=commit_snapshot,
            iter_snapshot_file_data_batches_fn=lambda *_a, **_kw: iter(()),
            load_snapshot_metadata_fn=lambda *_a: None,
            snapshot_file_data_exists_fn=lambda *_a: False,
            save_snapshot_metadata_fn=lambda *_a: None,
            save_snapshot_file_data_fn=lambda *_a: None,
            emit_snapshot_facts_fn=emit_snapshot_facts_fn,
            persist_run_state_fn=lambda _state: None,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=_noop,
            publish_run_repository_coverage_fn=_publish_coverage,
            utc_now_fn=lambda: "2026-01-01T00:00:00Z",
            telemetry=_telemetry(),
            facts_first_mode=True,
        )
    )

    assert emitted_snapshots == [
        [
            {
                "path": str(file_path.resolve()),
                "repo_path": str(repo.resolve()),
                "lang": "python",
                "functions": [{"name": "handler", "line_number": 1}],
            }
        ]
    ]
    assert forwarded_results == [emission_result]
    assert callable(forwarded_progress_callbacks[0])
    assert callable(forwarded_iter_fns[0])
    assert forwarded_repo_classes == ["small"]
    assert merged_imports == {"helper": [str(file_path.resolve())]}
