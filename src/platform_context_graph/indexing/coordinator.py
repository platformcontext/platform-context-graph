"""Durable repo-batch indexing coordinator with checkpointed resume support."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from platform_context_graph.observability import get_observability
from platform_context_graph.repository_identity import git_remote_for_path, repository_metadata
from platform_context_graph.tools.graph_builder_indexing import (
    finalize_index_batch,
    merge_import_maps,
    parse_repository_snapshot_async,
    resolve_repository_file_sets,
)

from .coordinator_models import (
    ACTIVE_REPO_STATES,
    IndexExecutionResult,
    RepositorySnapshot,
)
from .coordinator_runtime_status import publish_runtime_progress as _publish_runtime_progress
from .coordinator_storage import (
    _archive_run,
    _delete_snapshots,
    _load_or_create_run,
    _load_run_state_by_id,
    _load_snapshot,
    _matching_run_states,
    _persist_run_state,
    _record_checkpoint_metric,
    _save_snapshot,
    _update_pending_repository_gauge,
    _utc_now,
)


def _describe_run_state(run_state: Any) -> dict[str, Any]:
    """Return a CLI/API-friendly summary for one checkpointed run."""

    return {
        "run_id": run_state.run_id,
        "root_path": run_state.root_path,
        "family": run_state.family,
        "source": run_state.source,
        "status": run_state.status,
        "finalization_status": run_state.finalization_status,
        "created_at": run_state.created_at,
        "updated_at": run_state.updated_at,
        "last_error": run_state.last_error,
        "repository_count": len(run_state.repositories),
        "completed_repositories": run_state.completed_repositories(),
        "failed_repositories": run_state.failed_repositories(),
        "pending_repositories": run_state.pending_repositories(),
        "repositories": [
            {
                "repo_path": state.repo_path,
                "status": state.status,
                "file_count": state.file_count,
                "error": state.error,
                "started_at": state.started_at,
                "finished_at": state.finished_at,
                "updated_at": state.updated_at,
            }
            for state in sorted(
                run_state.repositories.values(),
                key=lambda item: item.repo_path,
            )
        ],
    }


def _positive_int_env(name: str, default: int, *, maximum: int = 128) -> int:
    """Return a bounded positive integer from the environment."""

    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return max(1, min(int(raw_value), maximum))
    except ValueError:
        return default


def _parse_worker_count() -> int:
    """Return the configured repository-parse concurrency."""

    legacy_default = _positive_int_env("PARALLEL_WORKERS", 4)
    return _positive_int_env("PCG_PARSE_WORKERS", legacy_default)


def _index_queue_depth(parse_workers: int) -> int:
    """Return the maximum number of parsed repositories awaiting commit."""

    return _positive_int_env("PCG_INDEX_QUEUE_DEPTH", max(2, parse_workers * 2))


def _commit_repository_snapshot(
    builder: Any,
    snapshot: RepositorySnapshot,
    *,
    is_dependency: bool,
) -> None:
    """Replace one repository's persisted graph/content state from a snapshot."""

    repo_path = Path(snapshot.repo_path).resolve()
    metadata = repository_metadata(
        name=repo_path.name,
        local_path=str(repo_path),
        remote_url=git_remote_for_path(repo_path),
    )
    content_provider = getattr(builder, "_content_provider", None)
    if content_provider is None:
        from platform_context_graph.content.state import get_postgres_content_provider

        content_provider = get_postgres_content_provider()
        builder._content_provider = content_provider

    if content_provider is not None and content_provider.enabled:
        content_provider.delete_repository_content(metadata["id"])

    try:
        builder.delete_repository_from_graph(str(repo_path))
    except Exception:
        pass

    builder.add_repository_to_graph(repo_path, is_dependency=is_dependency)
    for file_data in snapshot.file_data:
        builder.add_file_to_graph(file_data, repo_path.name, snapshot.imports_map)

async def execute_index_run(
    builder: Any,
    root_path: Path,
    *,
    is_dependency: bool = False,
    job_id: str | None = None,
    selected_repositories: list[Path] | tuple[Path, ...] | None = None,
    family: str,
    source: str,
    force: bool,
    component: str,
    asyncio_module: Any,
    datetime_cls: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
    error_logger_fn: Any,
    job_status_enum: Any,
    pathspec_module: Any,
) -> IndexExecutionResult:
    """Execute a checkpointed repo-batch index request."""

    repo_file_sets = resolve_repository_file_sets(
        builder,
        root_path,
        selected_repositories=selected_repositories,
        pathspec_module=pathspec_module,
    )
    repo_paths = list(repo_file_sets.keys())
    if not repo_paths:
        if job_id:
            builder.job_manager.update_job(
                job_id,
                status=job_status_enum.COMPLETED,
                end_time=datetime_cls.now(),
                result={"repository_count": 0},
            )
        return IndexExecutionResult(
            run_id="",
            root_path=root_path.resolve(),
            repository_count=0,
            completed_repositories=0,
            failed_repositories=0,
            resumed_repositories=0,
            skipped_repositories=0,
            finalization_status="skipped",
            status="completed",
        )

    run_state, resumed = _load_or_create_run(
        root_path=root_path.resolve(),
        family=family,
        source=source,
        repo_paths=repo_paths,
        is_dependency=is_dependency,
    )
    if force:
        _archive_run(run_state.run_id, reason="Force reindex requested")
        _record_checkpoint_metric(
            component=component,
            mode=family,
            source=source,
            operation="invalidate",
            status="completed",
        )
        run_state, resumed = _load_or_create_run(
            root_path=root_path.resolve(),
            family=family,
            source=source,
            repo_paths=repo_paths,
            is_dependency=is_dependency,
        )

    total_files = sum(len(files) for files in repo_file_sets.values())
    if job_id:
        builder.job_manager.update_job(
            job_id,
            status=job_status_enum.RUNNING,
            total_files=total_files,
        )

    telemetry = get_observability()
    resumed_repositories = sum(
        1
        for repo_state in run_state.repositories.values()
        if repo_state.status in {"failed", "parsed", "running", "commit_incomplete"}
    )
    skipped_repositories = sum(
        1 for repo_state in run_state.repositories.values() if repo_state.status == "skipped"
    )
    _update_pending_repository_gauge(
        component=component,
        mode=family,
        source=source,
        pending_count=run_state.pending_repositories(),
    )
    _publish_runtime_progress(
        ingester=component,
        source=source,
        run_state=run_state,
        repository_count=len(repo_paths),
        status="indexing",
    )
    with telemetry.index_run(
        component=component,
        mode=family,
        source=source,
        repo_count=len(repo_paths),
        run_id=run_state.run_id,
        resume=resumed,
    ) as run_scope:
        snapshots: list[RepositorySnapshot] = []
        merged_imports_map: dict[str, list[str]] = {}
        parse_targets: list[tuple[Path, bool]] = []
        for repo_path in repo_paths:
            repo_state = run_state.repositories[str(repo_path.resolve())]
            if repo_state.status == "completed":
                snapshot = _load_snapshot(run_state.run_id, repo_path)
                if snapshot is not None:
                    snapshots.append(snapshot)
                    merge_import_maps(merged_imports_map, snapshot.imports_map)
                    continue
                repo_state.status = "pending"
                repo_state.error = "Completed repo snapshot missing; re-parsing repository"
                _persist_run_state(run_state)

            parse_targets.append(
                (repo_path, resumed and repo_state.status in ACTIVE_REPO_STATES)
            )

        parse_workers = _parse_worker_count()
        snapshot_queue = asyncio_module.Queue(
            maxsize=_index_queue_depth(parse_workers)
        )
        queue_sentinel = object()
        parse_semaphore = asyncio_module.Semaphore(parse_workers)

        async def _parse_repository(
            repo_path: Path,
            *,
            resume_candidate: bool,
        ) -> None:
            repo_state = run_state.repositories[str(repo_path.resolve())]
            repo_state.started_at = _utc_now()
            repo_state.finished_at = None
            repo_state.error = None
            repo_state.status = "running"
            _persist_run_state(run_state)
            _record_checkpoint_metric(
                component=component,
                mode=family,
                source=source,
                operation="save",
                status="completed",
            )
            _update_pending_repository_gauge(
                component=component,
                mode=family,
                source=source,
                pending_count=run_state.pending_repositories(),
            )
            _publish_runtime_progress(
                ingester=component,
                source=source,
                run_state=run_state,
                repository_count=len(repo_paths),
                status="indexing",
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
                        snapshot = await parse_repository_snapshot_async(
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
                    _save_snapshot(run_state.run_id, snapshot)
                    _record_checkpoint_metric(
                        component=component,
                        mode=family,
                        source=source,
                        operation="save",
                        status="completed",
                    )
                    _persist_run_state(run_state)
                    _publish_runtime_progress(
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
                    repo_state.finished_at = _utc_now()
                    repo_state.status = "failed"
                    run_state.last_error = str(exc)
                    _persist_run_state(run_state)
                    _publish_runtime_progress(
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
                    warning_logger_fn(
                        f"Failed to index repository {repo_path.resolve()}: {exc}"
                    )
                finally:
                    _update_pending_repository_gauge(
                        component=component,
                        mode=family,
                        source=source,
                        pending_count=run_state.pending_repositories(),
                    )
                    _publish_runtime_progress(
                        ingester=component,
                        source=source,
                        run_state=run_state,
                        repository_count=len(repo_paths),
                        status="indexing",
                    )

        async def _commit_snapshots() -> None:
            while True:
                item = await snapshot_queue.get()
                if item is queue_sentinel:
                    snapshot_queue.task_done()
                    return

                repo_path, snapshot, started = item
                repo_state = run_state.repositories[str(repo_path.resolve())]
                try:
                    repo_state.status = "commit_incomplete"
                    _persist_run_state(run_state)
                    _publish_runtime_progress(
                        ingester=component,
                        source=source,
                        run_state=run_state,
                        repository_count=len(repo_paths),
                        status="indexing",
                    )
                    _commit_repository_snapshot(
                        builder,
                        snapshot,
                        is_dependency=is_dependency,
                    )
                    snapshots.append(snapshot)
                    merge_import_maps(merged_imports_map, snapshot.imports_map)
                    repo_state.status = "completed"
                    repo_state.finished_at = _utc_now()
                    _persist_run_state(run_state)
                    _publish_runtime_progress(
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
                    repo_state.finished_at = _utc_now()
                    repo_state.status = "commit_incomplete"
                    run_state.last_error = str(exc)
                    _persist_run_state(run_state)
                    _publish_runtime_progress(
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
                    warning_logger_fn(
                        f"Failed to commit repository {repo_path.resolve()}: {exc}"
                    )
                finally:
                    snapshot_queue.task_done()
                    _update_pending_repository_gauge(
                        component=component,
                        mode=family,
                        source=source,
                        pending_count=run_state.pending_repositories(),
                    )
                    _publish_runtime_progress(
                        ingester=component,
                        source=source,
                        run_state=run_state,
                        repository_count=len(repo_paths),
                        status="indexing",
                    )

        commit_task = asyncio_module.create_task(_commit_snapshots())
        parse_tasks = [
            asyncio_module.create_task(
                _parse_repository(repo_path, resume_candidate=resume_candidate)
            )
            for repo_path, resume_candidate in parse_targets
        ]
        if parse_tasks:
            await asyncio_module.gather(*parse_tasks)
        await snapshot_queue.join()
        await snapshot_queue.put(queue_sentinel)
        await commit_task

        if run_state.failed_repositories() == 0:
            run_state.finalization_status = "running"
            _persist_run_state(run_state)
            with telemetry.start_span(
                "pcg.index.finalize",
                component=component,
                attributes={
                    "pcg.index.run_id": run_state.run_id,
                    "pcg.index.repo_count": len(repo_paths),
                },
            ) as finalize_span:
                try:
                    finalize_index_batch(
                        builder,
                        snapshots=snapshots,
                        merged_imports_map=merged_imports_map,
                        info_logger_fn=info_logger_fn,
                    )
                    run_state.finalization_status = "completed"
                    run_state.status = "completed"
                    _persist_run_state(run_state)
                    _delete_snapshots(run_state.run_id)
                except Exception as exc:
                    run_state.status = "failed"
                    run_state.finalization_status = "failed"
                    run_state.last_error = str(exc)
                    _persist_run_state(run_state)
                    if finalize_span is not None:
                        finalize_span.record_exception(exc)
                    error_logger_fn(
                        f"Failed to finalize repository batch for {root_path.resolve()}: {exc}"
                    )
        else:
            run_state.status = "partial_failure"
            run_state.finalization_status = "pending"
            _persist_run_state(run_state)

        run_scope.status = run_state.status
        run_scope.finalization_status = run_state.finalization_status
        _update_pending_repository_gauge(
            component=component,
            mode=family,
            source=source,
            pending_count=run_state.pending_repositories(),
        )
        _publish_runtime_progress(
            ingester=component,
            source=source,
            run_state=run_state,
            repository_count=len(repo_paths),
            status=run_state.status,
            last_success_at=_utc_now() if run_state.status == "completed" else None,
        )

    if job_id:
        final_status = (
            job_status_enum.COMPLETED
            if run_state.status == "completed"
            else job_status_enum.FAILED
        )
        errors = [run_state.last_error] if run_state.last_error else []
        builder.job_manager.update_job(
            job_id,
            status=final_status,
            end_time=datetime_cls.now(),
            errors=errors,
            result={
                "run_id": run_state.run_id,
                "repository_count": len(repo_paths),
                "completed_repositories": run_state.completed_repositories(),
                "failed_repositories": run_state.failed_repositories(),
                "finalization_status": run_state.finalization_status,
                "status": run_state.status,
            },
        )

    return IndexExecutionResult(
        run_id=run_state.run_id,
        root_path=root_path.resolve(),
        repository_count=len(repo_paths),
        completed_repositories=run_state.completed_repositories(),
        failed_repositories=run_state.failed_repositories(),
        resumed_repositories=resumed_repositories,
        skipped_repositories=skipped_repositories,
        finalization_status=run_state.finalization_status,
        status=run_state.status,
    )


def raise_for_failed_index_run(result: IndexExecutionResult) -> None:
    """Raise a runtime error when a coordinated run did not finish cleanly."""

    if result.status == "completed":
        return
    raise RuntimeError(
        "Index run "
        f"{result.run_id or '<empty>'} finished with status {result.status} "
        f"(completed={result.completed_repositories}, failed={result.failed_repositories}, "
        f"finalization={result.finalization_status})"
    )


def describe_latest_index_run(path: Path) -> dict[str, Any] | None:
    """Return the latest persisted run summary for a root path."""

    matches = _matching_run_states(path.resolve())
    if not matches:
        return None
    return _describe_run_state(matches[0])


def describe_index_run(path_or_run_id: str | Path) -> dict[str, Any] | None:
    """Return a persisted run summary for a root path or explicit run ID."""

    if isinstance(path_or_run_id, Path):
        return describe_latest_index_run(path_or_run_id)

    candidate = str(path_or_run_id).strip()
    if candidate and all(char in "0123456789abcdef" for char in candidate.lower()):
        run_state = _load_run_state_by_id(candidate)
        if run_state is not None:
            return _describe_run_state(run_state)
    return describe_latest_index_run(Path(candidate).resolve())
