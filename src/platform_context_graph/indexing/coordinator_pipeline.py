"""Internal async pipeline helpers for checkpointed repo-batch indexing."""

from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any

from platform_context_graph.tools.graph_builder_indexing import merge_import_maps

from .coordinator_models import ACTIVE_REPO_STATES, RepositorySnapshot


def prepare_repository_snapshots(
    *,
    run_state: Any,
    repo_paths: list[Path],
    resumed: bool,
    load_snapshot_fn: Any,
    persist_run_state_fn: Any,
) -> tuple[list[RepositorySnapshot], dict[str, list[str]], list[tuple[Path, bool]]]:
    """Restore saved repository snapshots and identify repos that need parsing."""

    snapshots: list[RepositorySnapshot] = []
    merged_imports_map: dict[str, list[str]] = {}
    parse_targets: list[tuple[Path, bool]] = []

    for repo_path in repo_paths:
        repo_state = run_state.repositories[str(repo_path.resolve())]
        if repo_state.status == "completed":
            snapshot = load_snapshot_fn(run_state.run_id, repo_path)
            if snapshot is not None:
                snapshots.append(snapshot)
                merge_import_maps(merged_imports_map, snapshot.imports_map)
                continue
            repo_state.status = "pending"
            repo_state.error = "Completed repo snapshot missing; re-parsing repository"
            persist_run_state_fn(run_state)

        parse_targets.append(
            (repo_path, resumed and repo_state.status in ACTIVE_REPO_STATES)
        )

    return snapshots, merged_imports_map, parse_targets


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
    load_snapshot_fn: Any,
    save_snapshot_fn: Any,
    persist_run_state_fn: Any,
    record_checkpoint_metric_fn: Any,
    update_pending_repository_gauge_fn: Any,
    publish_runtime_progress_fn: Any,
    utc_now_fn: Any,
    telemetry: Any,
) -> tuple[list[RepositorySnapshot], dict[str, list[str]]]:
    """Parse repositories concurrently and commit them one at a time."""

    snapshots, merged_imports_map, parse_targets = prepare_repository_snapshots(
        run_state=run_state,
        repo_paths=repo_paths,
        resumed=resumed,
        load_snapshot_fn=load_snapshot_fn,
        persist_run_state_fn=persist_run_state_fn,
    )
    parse_workers = parse_worker_count_fn()
    snapshot_queue = asyncio_module.Queue(maxsize=index_queue_depth_fn(parse_workers))
    queue_sentinel = object()
    parse_semaphore = asyncio_module.Semaphore(parse_workers)

    def _publish_indexing_state() -> None:
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

    async def _parse_repository(
        repo_path: Path,
        *,
        resume_candidate: bool,
    ) -> None:
        """Parse one repository snapshot and enqueue it for serialized commit."""

        repo_state = run_state.repositories[str(repo_path.resolve())]
        started = time.perf_counter()
        with telemetry.start_span(
            "pcg.index.repository",
            component=component,
            attributes={
                "pcg.index.run_id": run_state.run_id,
                "pcg.index.repo_path": str(repo_path.resolve()),
                "pcg.index.resume": resume_candidate,
            },
        ) as repo_span:
            try:
                async with parse_semaphore:
                    repo_state.started_at = utc_now_fn()
                    repo_state.finished_at = None
                    repo_state.error = None
                    repo_state.status = "running"
                    persist_run_state_fn(run_state)
                    record_checkpoint_metric_fn(
                        component=component,
                        mode=family,
                        source=source,
                        operation="save",
                        status="completed",
                    )
                    _publish_indexing_state()
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
                    snapshot = await parse_repository_snapshot_async_fn(
                        builder,
                        repo_path,
                        repo_file_sets[repo_path],
                        is_dependency=is_dependency,
                        job_id=job_id,
                        asyncio_module=asyncio_module,
                        info_logger_fn=info_logger_fn,
                    )
                repo_state.file_count = snapshot.file_count
                repo_state.status = "parsed"
                save_snapshot_fn(run_state.run_id, snapshot)
                record_checkpoint_metric_fn(
                    component=component,
                    mode=family,
                    source=source,
                    operation="save",
                    status="completed",
                )
                persist_run_state_fn(run_state)
                publish_runtime_progress_fn(
                    ingester=component,
                    source=source,
                    run_state=run_state,
                    repository_count=len(repo_paths),
                    status="indexing",
                )
                await snapshot_queue.put((repo_path, snapshot, started))
                return
            except Exception as exc:
                repo_state.error = str(exc)
                repo_state.finished_at = utc_now_fn()
                repo_state.status = "failed"
                run_state.last_error = str(exc)
                persist_run_state_fn(run_state)
                publish_runtime_progress_fn(
                    ingester=component,
                    source=source,
                    run_state=run_state,
                    repository_count=len(repo_paths),
                    status="indexing",
                )
                telemetry.record_index_repositories(
                    component=component,
                    phase="failed",
                    count=1,
                    mode=family,
                    source=source,
                )
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
                _publish_indexing_state()

    async def _commit_snapshots() -> None:
        """Commit parsed repository snapshots from the queue in arrival order."""

        while True:
            item = await snapshot_queue.get()
            if item is queue_sentinel:
                snapshot_queue.task_done()
                return

            repo_path, snapshot, started = item
            repo_state = run_state.repositories[str(repo_path.resolve())]
            try:
                repo_state.status = "commit_incomplete"
                persist_run_state_fn(run_state)
                publish_runtime_progress_fn(
                    ingester=component,
                    source=source,
                    run_state=run_state,
                    repository_count=len(repo_paths),
                    status="indexing",
                )
                commit_repository_snapshot_fn(
                    builder,
                    snapshot,
                    is_dependency=is_dependency,
                )
                snapshots.append(snapshot)
                merge_import_maps(merged_imports_map, snapshot.imports_map)
                repo_state.status = "completed"
                repo_state.finished_at = utc_now_fn()
                persist_run_state_fn(run_state)
                publish_runtime_progress_fn(
                    ingester=component,
                    source=source,
                    run_state=run_state,
                    repository_count=len(repo_paths),
                    status="indexing",
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
            except Exception as exc:
                repo_state.error = str(exc)
                repo_state.finished_at = utc_now_fn()
                repo_state.status = "commit_incomplete"
                run_state.last_error = str(exc)
                persist_run_state_fn(run_state)
                publish_runtime_progress_fn(
                    ingester=component,
                    source=source,
                    run_state=run_state,
                    repository_count=len(repo_paths),
                    status="indexing",
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
                _publish_indexing_state()

    commit_task = asyncio_module.create_task(_commit_snapshots())
    parse_tasks = [
        asyncio_module.create_task(
            _parse_repository(repo_path, resume_candidate=resume_candidate)
        )
        for repo_path, resume_candidate in parse_targets
    ]
    try:
        if parse_tasks:
            results = await asyncio_module.gather(
                *parse_tasks, return_exceptions=True
            )
            for idx, result in enumerate(results):
                if isinstance(result, Exception):
                    repo_path = parse_targets[idx][0]
                    tb = traceback.format_exception(result)
                    warning_logger_fn(
                        f"Parse task for {repo_path.resolve()} escaped error handler: {result}\n"
                        f"{''.join(tb)}"
                    )
    finally:
        await snapshot_queue.put(queue_sentinel)
        await commit_task
    return snapshots, merged_imports_map


def finalize_repository_batch(
    *,
    builder: Any,
    root_path: Path,
    run_state: Any,
    repo_paths: list[Path],
    snapshots: list[RepositorySnapshot],
    merged_imports_map: dict[str, list[str]],
    component: str,
    family: str,
    source: str,
    info_logger_fn: Any,
    error_logger_fn: Any,
    finalize_index_batch_fn: Any,
    persist_run_state_fn: Any,
    delete_snapshots_fn: Any,
    telemetry: Any,
) -> None:
    """Finalize one successful repo batch or mark the run as partial failure."""

    if run_state.failed_repositories() == 0:
        run_state.finalization_status = "running"
        persist_run_state_fn(run_state)
        with telemetry.start_span(
            "pcg.index.finalize",
            component=component,
            attributes={
                "pcg.index.run_id": run_state.run_id,
                "pcg.index.repo_count": len(repo_paths),
            },
        ) as finalize_span:
            try:
                finalize_index_batch_fn(
                    builder,
                    snapshots=snapshots,
                    merged_imports_map=merged_imports_map,
                    info_logger_fn=info_logger_fn,
                )
                run_state.finalization_status = "completed"
                run_state.status = "completed"
                persist_run_state_fn(run_state)
                delete_snapshots_fn(run_state.run_id)
            except Exception as exc:
                run_state.status = "failed"
                run_state.finalization_status = "failed"
                run_state.last_error = str(exc)
                persist_run_state_fn(run_state)
                if finalize_span is not None:
                    finalize_span.record_exception(exc)
                error_logger_fn(
                    f"Failed to finalize repository batch for {root_path.resolve()}: {exc}"
                )
        return

    run_state.status = "partial_failure"
    run_state.finalization_status = "pending"
    persist_run_state_fn(run_state)


__all__ = [
    "finalize_repository_batch",
    "prepare_repository_snapshots",
    "process_repository_snapshots",
]
