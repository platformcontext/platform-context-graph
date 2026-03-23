"""Unit tests for pipeline deadlock prevention and failure handling."""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

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
            "platform_context_graph.tools.graph_builder_indexing",
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
                "platform_context_graph.tools.graph_builder_indexing",
                PACKAGE_ROOT / "tools" / "graph_builder_indexing.py",
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
process_repository_snapshots = PIPELINE.process_repository_snapshots


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

    snapshots, merged = await process_repository_snapshots(
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
        load_snapshot_fn=lambda *_a: None,
        save_snapshot_fn=lambda *_a: None,
        persist_run_state_fn=lambda _s: None,
        record_checkpoint_metric_fn=_noop,
        update_pending_repository_gauge_fn=_noop,
        publish_runtime_progress_fn=_noop,
        utc_now_fn=lambda: "2026-01-01T00:00:00Z",
        telemetry=telemetry or _telemetry(),
    )
    return snapshots, merged, run_state, warnings


def test_pipeline_completes_when_single_repo_fails(tmp_path: Path) -> None:
    """A single failing repo must not deadlock the pipeline."""
    repo = tmp_path / "bad-repo"
    repo.mkdir()
    (repo / "main.py").write_text("x", encoding="utf-8")
    repo_paths = [repo]
    repo_file_sets = {repo: [repo / "main.py"]}

    async def failing_parse(*_a, **_kw):
        raise RuntimeError("corrupt file")

    snapshots, _, run_state, _ = asyncio.run(
        _run_pipeline(repo_paths, repo_file_sets, failing_parse)
    )
    repo_state = run_state.repositories[str(repo.resolve())]
    assert repo_state.status == "failed"
    assert "corrupt file" in repo_state.error
    assert snapshots == []


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

    snapshots, _, run_state, _ = asyncio.run(
        _run_pipeline(repo_paths, repo_file_sets, mixed_parse, commit_fn=track_commit)
    )

    good_state = run_state.repositories[str(good_repo.resolve())]
    bad_state = run_state.repositories[str(bad_repo.resolve())]
    assert good_state.status == "completed"
    assert bad_state.status == "failed"
    assert len(snapshots) == 1
    assert snapshots[0].repo_path == str(good_repo.resolve())
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
            load_snapshot_fn=lambda *_a: None,
            save_snapshot_fn=lambda *_a: None,
            persist_run_state_fn=capture_persist,
            record_checkpoint_metric_fn=_noop,
            update_pending_repository_gauge_fn=_noop,
            publish_runtime_progress_fn=_noop,
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

    snapshots, _, run_state, warnings = asyncio.run(
        _run_pipeline(
            [repo],
            {repo: [repo / "main.py"]},
            should_not_parse,
            telemetry=telemetry,
        )
    )

    repo_state = run_state.repositories[str(repo.resolve())]
    assert snapshots == []
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

        async def __aenter__(self):
            await self._semaphore.acquire()
            self._acquire_count += 1
            if self._acquire_count == 2:
                current_time["value"] += 5.0
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._semaphore.release()

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

    snapshots, _, run_state, _ = asyncio.run(
        _run_pipeline(repos, repo_file_sets, all_fail)
    )

    assert snapshots == []
    assert run_state.failed_repositories() == 3
    assert run_state.completed_repositories() == 0
