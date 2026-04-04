"""Regression tests for repository parse pool failure containment."""

from __future__ import annotations

import asyncio
from concurrent.futures.process import BrokenProcessPool
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from platform_context_graph.indexing.coordinator_models import (
    IndexRunState,
    RepositoryRunState,
    RepositorySnapshot,
)
from platform_context_graph.indexing.coordinator_pipeline import (
    process_repository_snapshots,
)


def _make_run_state(repo_paths: list[Path]) -> IndexRunState:
    """Build a minimal run state with pending repositories."""

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
            str(repo_path.resolve()): RepositoryRunState(
                repo_path=str(repo_path.resolve())
            )
            for repo_path in repo_paths
        },
    )


def _noop(**_kwargs: Any) -> None:
    """Ignore a callback from the pipeline."""


def _publish_coverage(**_kwargs: Any) -> None:
    """Ignore repository coverage publishing."""


@contextmanager
def _span_scope(*_args: Any, **_kwargs: Any):
    """Yield a span stub that tolerates record_exception calls."""

    yield SimpleNamespace(record_exception=lambda _exc: None)


def _telemetry():
    """Return a minimal telemetry stub for pipeline tests."""

    return SimpleNamespace(
        start_span=_span_scope,
        record_index_repositories=_noop,
        record_index_repository_duration=_noop,
    )


async def _run_pipeline(
    repo_paths: list[Path],
    repo_file_sets: dict[Path, list[Path]],
    parse_fn: Any,
    *,
    parse_executor: Any | None = None,
    parse_strategy: str = "threaded",
    telemetry: Any | None = None,
) -> tuple[list[Path], IndexRunState, list[str]]:
    """Run the repository pipeline with minimal stubbed collaborators."""

    run_state = _make_run_state(repo_paths)
    warnings: list[str] = []

    committed_repo_paths, _merged, _repo_telemetry = await process_repository_snapshots(
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
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=warnings.append,
        parse_worker_count_fn=lambda: 4,
        index_queue_depth_fn=lambda _workers: 8,
        parse_repository_snapshot_async_fn=parse_fn,
        commit_repository_snapshot_fn=lambda *_args, **_kwargs: None,
        iter_snapshot_file_data_batches_fn=lambda *_args, **_kwargs: iter(()),
        load_snapshot_metadata_fn=lambda *_args: None,
        snapshot_file_data_exists_fn=lambda *_args: False,
        save_snapshot_metadata_fn=lambda *_args: None,
        save_snapshot_file_data_fn=lambda *_args: None,
        persist_run_state_fn=lambda _state: None,
        record_checkpoint_metric_fn=_noop,
        update_pending_repository_gauge_fn=_noop,
        publish_runtime_progress_fn=_noop,
        publish_run_repository_coverage_fn=_publish_coverage,
        utc_now_fn=lambda: "2026-01-01T00:00:00Z",
        telemetry=telemetry or _telemetry(),
        parse_executor=parse_executor,
        parse_strategy=parse_strategy,
        parse_workers=4,
    )
    return committed_repo_paths, run_state, warnings


def test_pipeline_falls_back_to_threaded_parse_when_process_pool_breaks(
    tmp_path: Path,
) -> None:
    """A broken process pool should degrade the repo to threaded parsing once."""

    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")
    parse_executor = object()
    observed_executors: list[Any | None] = []

    async def parse_snapshot(
        _builder: Any, repo_path: Path, repo_files: list[Path], **kwargs: Any
    ):
        observed_executors.append(kwargs["parse_executor"])
        if kwargs["parse_executor"] is parse_executor:
            raise BrokenProcessPool("worker died")
        return RepositorySnapshot(
            repo_path=str(repo_path.resolve()),
            file_count=len(repo_files),
            imports_map={},
            file_data=[],
        )

    committed_repo_paths, run_state, warnings = asyncio.run(
        _run_pipeline(
            [repo],
            {repo: [file_path]},
            parse_snapshot,
            parse_executor=parse_executor,
            parse_strategy="multiprocess",
        )
    )

    repo_state = run_state.repositories[str(repo.resolve())]
    assert committed_repo_paths == [repo.resolve()]
    assert repo_state.status == "completed"
    assert observed_executors == [parse_executor, None]
    assert any(
        "falling back to threaded parsing" in warning.lower() for warning in warnings
    )


def test_pipeline_does_not_record_exception_on_closed_repository_span(
    tmp_path: Path,
) -> None:
    """Repo failure should not try to record onto an exited span."""

    repo = tmp_path / "repo"
    repo.mkdir()
    file_path = repo / "main.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    @contextmanager
    def closed_span_scope(*_args: Any, **_kwargs: Any):
        """Yield a span stub that would fail if used after scope exit."""

        yield SimpleNamespace(
            record_exception=lambda _exc: (_ for _ in ()).throw(
                AssertionError("record_exception should not be called")
            )
        )

    telemetry = SimpleNamespace(
        start_span=closed_span_scope,
        record_index_repositories=_noop,
        record_index_repository_duration=_noop,
    )

    async def failing_parse(*_args: Any, **_kwargs: Any):
        raise RuntimeError("boom")

    committed_repo_paths, run_state, warnings = asyncio.run(
        _run_pipeline(
            [repo],
            {repo: [file_path]},
            failing_parse,
            telemetry=telemetry,
        )
    )

    repo_state = run_state.repositories[str(repo.resolve())]
    assert committed_repo_paths == []
    assert repo_state.status == "failed"
    assert repo_state.error == "boom"
    assert any("boom" in warning for warning in warnings)
