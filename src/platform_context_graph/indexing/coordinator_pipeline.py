"""Internal async pipeline helpers for checkpointed repo-batch indexing."""

from __future__ import annotations

import asyncio
import os
import time
import traceback
from pathlib import Path
from typing import Any

from platform_context_graph.tools.graph_builder_indexing import merge_import_maps
from platform_context_graph.utils.debug_log import emit_log_call

from .coordinator_finalize import finalize_repository_batch
from .memory_diagnostics import log_memory_usage
from .coordinator_models import (
    ACTIVE_REPO_STATES,
    RepositorySnapshotMetadata,
)


def prepare_repository_snapshots(
    *,
    run_state: Any,
    repo_paths: list[Path],
    resumed: bool,
    load_snapshot_metadata_fn: Any,
    snapshot_file_data_exists_fn: Any,
    persist_run_state_fn: Any,
) -> tuple[list[Path], dict[str, list[str]], list[tuple[Path, bool]]]:
    """Restore saved repository snapshots and identify repos that need parsing."""

    committed_repo_paths: list[Path] = []
    merged_imports_map: dict[str, list[str]] = {}
    parse_targets: list[tuple[Path, bool]] = []

    for repo_path in repo_paths:
        repo_state = run_state.repositories[str(repo_path.resolve())]
        if repo_state.status == "completed":
            snapshot_metadata = load_snapshot_metadata_fn(run_state.run_id, repo_path)
            if snapshot_metadata is not None and snapshot_file_data_exists_fn(
                run_state.run_id, repo_path
            ):
                committed_repo_paths.append(repo_path.resolve())
                merge_import_maps(merged_imports_map, snapshot_metadata.imports_map)
                continue
            repo_state.status = "pending"
            repo_state.error = (
                "Completed repo snapshot incomplete; re-parsing repository"
            )
            persist_run_state_fn(run_state)

        parse_targets.append(
            (repo_path, resumed and repo_state.status in ACTIVE_REPO_STATES)
        )

    return committed_repo_paths, merged_imports_map, parse_targets


async def process_repository_snapshots(
    *,
    builder: Any,
    run_state: Any,
    repo_paths: list[Path],
    repo_file_sets: dict[Path, list[Path]],
    resumed: bool,
    is_dependency: bool,
    job_id: str | None,
    component: str,
    family: str,
    source: str,
    asyncio_module: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
    parse_worker_count_fn: Any,
    index_queue_depth_fn: Any,
    parse_repository_snapshot_async_fn: Any,
    commit_repository_snapshot_fn: Any,
    iter_snapshot_file_data_batches_fn: Any,
    load_snapshot_metadata_fn: Any,
    snapshot_file_data_exists_fn: Any,
    save_snapshot_metadata_fn: Any,
    save_snapshot_file_data_fn: Any,
    persist_run_state_fn: Any,
    record_checkpoint_metric_fn: Any,
    update_pending_repository_gauge_fn: Any,
    publish_runtime_progress_fn: Any,
    publish_run_repository_coverage_fn: Any,
    utc_now_fn: Any,
    telemetry: Any,
    parse_executor: Any | None = None,
    parse_strategy: str = "threaded",
    parse_workers: int = 1,
) -> tuple[list[Path], dict[str, list[str]]]:
    """Parse repositories concurrently and commit via PCG_COMMIT_WORKERS consumers."""

    committed_repo_paths, merged_imports_map, parse_targets = (
        prepare_repository_snapshots(
            run_state=run_state,
            repo_paths=repo_paths,
            resumed=resumed,
            load_snapshot_metadata_fn=load_snapshot_metadata_fn,
            snapshot_file_data_exists_fn=snapshot_file_data_exists_fn,
            persist_run_state_fn=persist_run_state_fn,
        )
    )
    parse_slots = parse_worker_count_fn()
    snapshot_queue = asyncio_module.Queue(maxsize=index_queue_depth_fn(parse_slots))
    queue_sentinel = object()
    parse_semaphore = asyncio_module.Semaphore(parse_slots)
    if hasattr(telemetry, "set_index_snapshot_queue_depth"):
        telemetry.set_index_snapshot_queue_depth(
            component=component,
            mode=family,
            source=source,
            depth=0,
            parse_strategy=parse_strategy,
            parse_workers=parse_workers,
        )

    def _publish_runtime_state() -> None:
        """Publish the current pending-repo count and indexing progress snapshot."""

        update_pending_repository_gauge_fn(
            component=component,
            mode=family,
            source=source,
            pending_count=run_state.pending_repositories(),
        )
        publish_runtime_progress_fn(
            ingester=component,
            source=source,
            run_state=run_state,
            repository_count=len(repo_paths),
            status="indexing",
        )

    def _update_repo_progress(
        repo_state: Any,
        *,
        status: str | None = None,
        phase: str | None = None,
        current_file: str | None = None,
        clear_current_file: bool = False,
        persist: bool = False,
        finished_at: str | None = None,
        commit_started_at: str | None = None,
        commit_finished_at: str | None = None,
        commit_duration_seconds: float | None = None,
    ) -> None:
        """Update one repository checkpoint with additive phase diagnostics."""

        now = utc_now_fn()
        repo_state.updated_at = now
        repo_state.last_progress_at = now
        if status is not None:
            repo_state.status = status
        if phase is not None and phase != repo_state.phase:
            repo_state.phase = phase
            repo_state.phase_started_at = now
        if clear_current_file:
            repo_state.current_file = None
        elif current_file is not None:
            repo_state.current_file = current_file
        if finished_at is not None:
            repo_state.finished_at = finished_at
        if commit_started_at is not None:
            repo_state.commit_started_at = commit_started_at
        if commit_finished_at is not None:
            repo_state.commit_finished_at = commit_finished_at
        if commit_duration_seconds is not None:
            repo_state.commit_duration_seconds = commit_duration_seconds
        if persist:
            persist_run_state_fn(run_state)
            _publish_runtime_state()

    async def _parse_repository(
        repo_path: Path,
        *,
        resume_candidate: bool,
    ) -> None:
        """Parse one repository snapshot and enqueue it for serialized commit."""

        repo_key = str(repo_path.resolve())
        started: float | None = None
        repo_span = None
        last_progress_publish = 0.0
        try:
            repo_state = run_state.repositories[repo_key]

            def _progress_callback(
                *, current_file: str | None = None, force: bool = False
            ):
                """Persist repo progress while throttling checkpoint churn."""

                nonlocal last_progress_publish
                _update_repo_progress(
                    repo_state,
                    current_file=current_file,
                    persist=False,
                )
                now_monotonic = time.monotonic()
                if force or now_monotonic - last_progress_publish >= 1.0:
                    last_progress_publish = now_monotonic
                    persist_run_state_fn(run_state)
                    _publish_runtime_state()

            with telemetry.start_span(
                "pcg.index.repository",
                component=component,
                attributes={
                    "pcg.index.run_id": run_state.run_id,
                    "pcg.index.repo_path": repo_key,
                    "pcg.index.resume": resume_candidate,
                    "pcg.index.parse_strategy": parse_strategy,
                    "pcg.index.parse_workers": parse_workers,
                },
            ) as repo_span:
                queue_wait_started = time.perf_counter()
                with telemetry.start_span(
                    "pcg.index.repository.queue_wait",
                    component=component,
                    attributes={
                        "pcg.index.run_id": run_state.run_id,
                        "pcg.index.repo_path": repo_key,
                        "pcg.index.parse_strategy": parse_strategy,
                        "pcg.index.parse_workers": parse_workers,
                    },
                ):
                    await parse_semaphore.acquire()
                queue_wait_duration = time.perf_counter() - queue_wait_started
                try:
                    if hasattr(telemetry, "record_index_stage_duration"):
                        telemetry.record_index_stage_duration(
                            component=component,
                            mode=family,
                            source=source,
                            stage="repository_queue_wait",
                            duration_seconds=queue_wait_duration,
                            parse_strategy=parse_strategy,
                            parse_workers=parse_workers,
                        )
                    emit_log_call(
                        info_logger_fn,
                        f"Repository parse slot acquired for {repo_path.resolve()} after "
                        f"{queue_wait_duration:.3f}s",
                        event_name="index.repository.queue_wait.completed",
                        extra_keys={
                            "run_id": run_state.run_id,
                            "repo_path": str(repo_path.resolve()),
                            "duration_seconds": round(queue_wait_duration, 6),
                            "parse_strategy": parse_strategy,
                            "parse_workers": parse_workers,
                        },
                    )
                    with telemetry.start_span(
                        "pcg.index.repository.parse",
                        component=component,
                        attributes={
                            "pcg.index.run_id": run_state.run_id,
                            "pcg.index.repo_path": repo_key,
                            "pcg.index.file_count": len(repo_file_sets[repo_path]),
                            "pcg.index.parse_strategy": parse_strategy,
                            "pcg.index.parse_workers": parse_workers,
                        },
                    ):
                        started = time.perf_counter()
                        repo_state.started_at = utc_now_fn()
                        repo_state.finished_at = None
                        repo_state.error = None
                        repo_state.commit_started_at = None
                        repo_state.commit_finished_at = None
                        repo_state.commit_duration_seconds = None
                        _update_repo_progress(
                            repo_state,
                            status="running",
                            phase="parsing",
                            clear_current_file=True,
                            persist=True,
                        )
                        record_checkpoint_metric_fn(
                            component=component,
                            mode=family,
                            source=source,
                            operation="save",
                            status="completed",
                        )
                        telemetry.record_index_repositories(
                            component=component,
                            phase="started",
                            count=1,
                            mode=family,
                            source=source,
                        )
                        if resume_candidate:
                            telemetry.record_index_repositories(
                                component=component,
                                phase="resumed",
                                count=1,
                                mode=family,
                                source=source,
                            )
                        emit_log_call(
                            info_logger_fn,
                            f"Starting repository parse for {repo_path.resolve()}",
                            event_name="index.repository.parse.started",
                            extra_keys={
                                "run_id": run_state.run_id,
                                "repo_path": str(repo_path.resolve()),
                                "file_count": len(repo_file_sets[repo_path]),
                                "parse_strategy": parse_strategy,
                                "parse_workers": parse_workers,
                            },
                        )
                        parse_started = time.perf_counter()
                        snapshot = await parse_repository_snapshot_async_fn(
                            builder,
                            repo_path,
                            repo_file_sets[repo_path],
                            is_dependency=is_dependency,
                            job_id=job_id,
                            asyncio_module=asyncio_module,
                            info_logger_fn=info_logger_fn,
                            progress_callback=_progress_callback,
                            parse_executor=parse_executor,
                            component=component,
                            mode=family,
                            source=source,
                            parse_workers=parse_workers,
                        )
                        parse_duration = time.perf_counter() - parse_started
                        if hasattr(telemetry, "record_index_stage_duration"):
                            telemetry.record_index_stage_duration(
                                component=component,
                                mode=family,
                                source=source,
                                stage="repository_parse",
                                duration_seconds=parse_duration,
                                parse_strategy=parse_strategy,
                                parse_workers=parse_workers,
                            )
                        emit_log_call(
                            info_logger_fn,
                            f"Finished repository parse for {repo_path.resolve()} in "
                            f"{parse_duration:.3f}s",
                            event_name="index.repository.parse.completed",
                            extra_keys={
                                "run_id": run_state.run_id,
                                "repo_path": str(repo_path.resolve()),
                                "file_count": snapshot.file_count,
                                "duration_seconds": round(parse_duration, 6),
                                "parse_strategy": parse_strategy,
                                "parse_workers": parse_workers,
                            },
                        )
                        _progress_callback(force=True)
                    repo_state.file_count = snapshot.file_count
                    _update_repo_progress(
                        repo_state,
                        status="parsed",
                        phase="parsed",
                        persist=False,
                    )
                    save_snapshot_file_data_fn(
                        run_state.run_id,
                        Path(snapshot.repo_path),
                        snapshot.file_data,
                    )
                    save_snapshot_metadata_fn(
                        run_state.run_id,
                        RepositorySnapshotMetadata(
                            repo_path=snapshot.repo_path,
                            file_count=snapshot.file_count,
                            imports_map=snapshot.imports_map,
                        ),
                    )
                    snapshot.file_data = []
                    record_checkpoint_metric_fn(
                        component=component,
                        mode=family,
                        source=source,
                        operation="save",
                        status="completed",
                    )
                    persist_run_state_fn(run_state)
                    _publish_runtime_state()
                    publish_run_repository_coverage_fn(
                        builder=builder,
                        run_state=run_state,
                        repo_paths=[repo_path],
                        include_graph_counts=False,
                        include_content_counts=False,
                    )
                    commit_wait_started = time.perf_counter()
                    with telemetry.start_span(
                        "pcg.index.repository.commit_wait",
                        component=component,
                        attributes={
                            "pcg.index.run_id": run_state.run_id,
                            "pcg.index.repo_path": repo_key,
                            "pcg.index.parse_strategy": parse_strategy,
                            "pcg.index.parse_workers": parse_workers,
                        },
                    ):
                        await snapshot_queue.put(
                            (repo_path, snapshot, started, commit_wait_started)
                        )
                    if hasattr(telemetry, "set_index_snapshot_queue_depth"):
                        telemetry.set_index_snapshot_queue_depth(
                            component=component,
                            mode=family,
                            source=source,
                            depth=snapshot_queue.qsize(),
                            parse_strategy=parse_strategy,
                            parse_workers=parse_workers,
                        )
                    return
                finally:
                    parse_semaphore.release()
        except Exception as exc:
            repo_state = run_state.repositories.get(repo_key)
            if repo_state is not None:
                repo_state.error = str(exc)
                _update_repo_progress(
                    repo_state,
                    status="failed",
                    phase="failed",
                    clear_current_file=True,
                    finished_at=utc_now_fn(),
                    persist=False,
                )
            run_state.last_error = str(exc)
            persist_run_state_fn(run_state)
            _publish_runtime_state()
            publish_run_repository_coverage_fn(
                builder=builder,
                run_state=run_state,
                repo_paths=[Path(repo_key)],
                include_graph_counts=True,
                include_content_counts=True,
            )
            telemetry.record_index_repositories(
                component=component,
                phase="failed",
                count=1,
                mode=family,
                source=source,
            )
            if started is not None:
                telemetry.record_index_repository_duration(
                    component=component,
                    mode=family,
                    source=source,
                    status="failed",
                    duration_seconds=time.perf_counter() - started,
                )
            if repo_span is not None:
                repo_span.record_exception(exc)
            tb = traceback.format_exception(exc)
            warning_logger_fn(
                f"Failed to index repository {repo_path.resolve()}: {exc}\n"
                f"{''.join(tb)}"
            )
        finally:
            _publish_runtime_state()

    commit_concurrency = int(os.environ.get("PCG_COMMIT_WORKERS", "1"))
    commit_state_lock = asyncio.Lock()

    async def _commit_snapshots() -> None:
        """Commit parsed repository snapshots from the queue in arrival order."""

        while True:
            item = await snapshot_queue.get()
            if item is queue_sentinel:
                snapshot_queue.task_done()
                return

            repo_path, snapshot, started, snapshot_ready_started = item
            repo_state = run_state.repositories[str(repo_path.resolve())]
            commit_started: float | None = None
            last_commit_progress_publish = 0.0
            last_commit_coverage_publish = 0.0
            try:
                commit_wait_duration = time.perf_counter() - snapshot_ready_started
                if hasattr(telemetry, "record_index_stage_duration"):
                    telemetry.record_index_stage_duration(
                        component=component,
                        mode=family,
                        source=source,
                        stage="repository_commit_wait",
                        duration_seconds=commit_wait_duration,
                        parse_strategy=parse_strategy,
                        parse_workers=parse_workers,
                    )
                emit_log_call(
                    info_logger_fn,
                    f"Repository commit slot acquired for {repo_path.resolve()} after "
                    f"{commit_wait_duration:.3f}s",
                    event_name="index.repository.commit_wait.completed",
                    extra_keys={
                        "run_id": run_state.run_id,
                        "repo_path": str(repo_path.resolve()),
                        "duration_seconds": round(commit_wait_duration, 6),
                        "parse_strategy": parse_strategy,
                        "parse_workers": parse_workers,
                    },
                )
                if hasattr(telemetry, "set_index_snapshot_queue_depth"):
                    telemetry.set_index_snapshot_queue_depth(
                        component=component,
                        mode=family,
                        source=source,
                        depth=snapshot_queue.qsize(),
                        parse_strategy=parse_strategy,
                        parse_workers=parse_workers,
                    )
                commit_started_at = utc_now_fn()
                _update_repo_progress(
                    repo_state,
                    status="commit_incomplete",
                    phase="committing",
                    clear_current_file=True,
                    persist=False,
                    commit_started_at=commit_started_at,
                    commit_finished_at=None,
                    commit_duration_seconds=None,
                )
                persist_run_state_fn(run_state)
                _publish_runtime_state()
                publish_run_repository_coverage_fn(
                    builder=builder,
                    run_state=run_state,
                    repo_paths=[repo_path],
                    include_graph_counts=False,
                    include_content_counts=False,
                )
                commit_started = time.perf_counter()
                emit_log_call(
                    info_logger_fn,
                    f"Starting repository commit for {repo_path.resolve()}",
                    event_name="index.repository.commit.started",
                    extra_keys={
                        "run_id": run_state.run_id,
                        "repo_path": str(repo_path.resolve()),
                        "parse_strategy": parse_strategy,
                        "parse_workers": parse_workers,
                    },
                )

                def _commit_progress_callback(
                    *,
                    processed_files: int,
                    total_files: int,
                    current_file: str | None = None,
                    committed: bool = True,
                ) -> None:
                    """Persist commit heartbeats and partial coverage during batch writes."""

                    nonlocal last_commit_progress_publish
                    nonlocal last_commit_coverage_publish

                    _update_repo_progress(
                        repo_state,
                        current_file=current_file,
                        persist=False,
                    )
                    now_monotonic = time.monotonic()
                    is_final_batch = committed and processed_files >= total_files

                    if (
                        committed
                        or is_final_batch
                        or now_monotonic - last_commit_progress_publish >= 1.0
                    ):
                        last_commit_progress_publish = now_monotonic
                        persist_run_state_fn(run_state)
                        _publish_runtime_state()

                    if committed and (
                        is_final_batch
                        or now_monotonic - last_commit_coverage_publish >= 15.0
                    ):
                        last_commit_coverage_publish = now_monotonic
                        publish_run_repository_coverage_fn(
                            builder=builder,
                            run_state=run_state,
                            repo_paths=[repo_path],
                            include_graph_counts=True,
                            include_content_counts=True,
                        )

                with telemetry.start_span(
                    "pcg.index.repository.commit",
                    component=component,
                    attributes={
                        "pcg.index.run_id": run_state.run_id,
                        "pcg.index.repo_path": str(repo_path.resolve()),
                        "pcg.index.parse_strategy": parse_strategy,
                        "pcg.index.parse_workers": parse_workers,
                    },
                ):
                    commit_repository_snapshot_fn(
                        builder,
                        snapshot,
                        is_dependency=is_dependency,
                        progress_callback=_commit_progress_callback,
                        iter_snapshot_file_data_batches_fn=lambda repo_path, batch_size: iter_snapshot_file_data_batches_fn(
                            run_state.run_id,
                            repo_path,
                            batch_size=batch_size,
                        ),
                    )
                async with commit_state_lock:
                    committed_repo_paths.append(repo_path.resolve())
                    merge_import_maps(merged_imports_map, snapshot.imports_map)
                snapshot.file_data = []
                commit_finished_at = utc_now_fn()
                _update_repo_progress(
                    repo_state,
                    status="completed",
                    phase="completed",
                    clear_current_file=True,
                    persist=False,
                    finished_at=commit_finished_at,
                    commit_finished_at=commit_finished_at,
                    commit_duration_seconds=(
                        time.perf_counter() - commit_started
                        if commit_started is not None
                        else None
                    ),
                )
                persist_run_state_fn(run_state)
                _publish_runtime_state()
                publish_run_repository_coverage_fn(
                    builder=builder,
                    run_state=run_state,
                    repo_paths=[repo_path],
                    include_graph_counts=True,
                    include_content_counts=True,
                )
                log_memory_usage(
                    info_logger_fn,
                    context=("Repository commit memory " f"repo={repo_path.resolve()}"),
                )
                telemetry.record_index_repositories(
                    component=component,
                    phase="completed",
                    count=1,
                    mode=family,
                    source=source,
                )
                telemetry.record_index_repository_duration(
                    component=component,
                    mode=family,
                    source=source,
                    status="completed",
                    duration_seconds=time.perf_counter() - started,
                )
                commit_duration = (
                    time.perf_counter() - commit_started
                    if commit_started is not None
                    else 0.0
                )
                if hasattr(telemetry, "record_index_stage_duration"):
                    telemetry.record_index_stage_duration(
                        component=component,
                        mode=family,
                        source=source,
                        stage="repository_commit",
                        duration_seconds=commit_duration,
                        parse_strategy=parse_strategy,
                        parse_workers=parse_workers,
                    )
                emit_log_call(
                    info_logger_fn,
                    f"Finished repository commit for {repo_path.resolve()} in "
                    f"{commit_duration:.3f}s",
                    event_name="index.repository.commit.completed",
                    extra_keys={
                        "run_id": run_state.run_id,
                        "repo_path": str(repo_path.resolve()),
                        "duration_seconds": round(commit_duration, 6),
                        "parse_strategy": parse_strategy,
                        "parse_workers": parse_workers,
                    },
                )
            except Exception as exc:
                repo_state.error = str(exc)
                commit_finished_at = utc_now_fn()
                _update_repo_progress(
                    repo_state,
                    status="commit_incomplete",
                    phase="commit_incomplete",
                    clear_current_file=True,
                    persist=False,
                    finished_at=commit_finished_at,
                    commit_finished_at=commit_finished_at,
                    commit_duration_seconds=(
                        time.perf_counter() - commit_started
                        if commit_started is not None
                        else None
                    ),
                )
                run_state.last_error = str(exc)
                persist_run_state_fn(run_state)
                _publish_runtime_state()
                publish_run_repository_coverage_fn(
                    builder=builder,
                    run_state=run_state,
                    repo_paths=[repo_path],
                    include_graph_counts=True,
                    include_content_counts=True,
                )
                telemetry.record_index_repositories(
                    component=component,
                    phase="commit_incomplete",
                    count=1,
                    mode=family,
                    source=source,
                )
                telemetry.record_index_repository_duration(
                    component=component,
                    mode=family,
                    source=source,
                    status="commit_incomplete",
                    duration_seconds=time.perf_counter() - started,
                )
                tb = traceback.format_exception(exc)
                warning_logger_fn(
                    f"Failed to commit repository {repo_path.resolve()}: {exc}\n"
                    f"{''.join(tb)}"
                )
            finally:
                snapshot_queue.task_done()
                if hasattr(telemetry, "set_index_snapshot_queue_depth"):
                    telemetry.set_index_snapshot_queue_depth(
                        component=component,
                        mode=family,
                        source=source,
                        depth=snapshot_queue.qsize(),
                        parse_strategy=parse_strategy,
                        parse_workers=parse_workers,
                    )
                _publish_runtime_state()

    commit_tasks = [
        asyncio_module.create_task(_commit_snapshots())
        for _ in range(commit_concurrency)
    ]
    parse_tasks = [
        asyncio_module.create_task(
            _parse_repository(repo_path, resume_candidate=resume_candidate)
        )
        for repo_path, resume_candidate in parse_targets
    ]
    escaped_parse_exception: Exception | None = None
    try:
        if parse_tasks:
            results = await asyncio_module.gather(*parse_tasks, return_exceptions=True)
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    repo_path = parse_targets[idx][0]
                    tb = traceback.format_exception(result)
                    warning_logger_fn(
                        f"Parse task for {repo_path.resolve()} escaped error handler: {result}\n"
                        f"{''.join(tb)}"
                    )
                    if escaped_parse_exception is None:
                        escaped_parse_exception = result
    finally:
        for _ in range(commit_concurrency):
            await snapshot_queue.put(queue_sentinel)
        await asyncio_module.gather(*commit_tasks)
    if escaped_parse_exception is not None:
        raise escaped_parse_exception
    return committed_repo_paths, merged_imports_map


__all__ = [
    "finalize_repository_batch",
    "prepare_repository_snapshots",
    "process_repository_snapshots",
]
