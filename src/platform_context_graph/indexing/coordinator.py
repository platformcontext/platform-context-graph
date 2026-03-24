"""Durable repo-batch indexing coordinator with checkpointed resume support."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from platform_context_graph.observability import get_observability
from platform_context_graph.repository_identity import (
    git_remote_for_path,
    repository_metadata,
)
from platform_context_graph.tools.graph_builder_indexing import (
    finalize_index_batch,
    parse_repository_snapshot_async,
    resolve_repository_file_sets,
)
from .coordinator_pipeline import (
    finalize_repository_batch,
    process_repository_snapshots,
)

from .coordinator_models import (
    IndexExecutionResult,
    RepositorySnapshot,
)
from .coordinator_runtime_status import (
    publish_runtime_progress as _publish_runtime_progress,
)
from .coordinator_storage import (
    _archive_run,
    _delete_snapshots,
    _graph_store_adapter,
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
        "finalization_started_at": run_state.finalization_started_at,
        "finalization_finished_at": run_state.finalization_finished_at,
        "finalization_duration_seconds": run_state.finalization_duration_seconds,
        "finalization_current_stage": run_state.finalization_current_stage,
        "finalization_stage_started_at": run_state.finalization_stage_started_at,
        "finalization_stage_durations": run_state.finalization_stage_durations,
        "finalization_stage_details": run_state.finalization_stage_details,
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
                "phase": state.phase,
                "phase_started_at": state.phase_started_at,
                "last_progress_at": state.last_progress_at,
                "current_file": state.current_file,
                "commit_started_at": state.commit_started_at,
                "commit_finished_at": state.commit_finished_at,
                "commit_duration_seconds": state.commit_duration_seconds,
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
    graph_store = _graph_store_adapter(builder)
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
        graph_store.delete_repository(metadata["id"])
    except Exception:
        pass

    builder.add_repository_to_graph(repo_path, is_dependency=is_dependency)
    batch_size = _positive_int_env("PCG_FILE_BATCH_SIZE", 50, maximum=512)
    for i in range(0, len(snapshot.file_data), batch_size):
        batch = snapshot.file_data[i : i + batch_size]
        builder.commit_file_batch_to_graph(batch, repo_path)


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
        1
        for repo_state in run_state.repositories.values()
        if repo_state.status == "skipped"
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
        snapshots, merged_imports_map = await process_repository_snapshots(
            builder=builder,
            run_state=run_state,
            repo_paths=repo_paths,
            repo_file_sets=repo_file_sets,
            resumed=resumed,
            is_dependency=is_dependency,
            job_id=job_id,
            component=component,
            family=family,
            source=source,
            asyncio_module=asyncio_module,
            info_logger_fn=info_logger_fn,
            warning_logger_fn=warning_logger_fn,
            parse_worker_count_fn=_parse_worker_count,
            index_queue_depth_fn=_index_queue_depth,
            parse_repository_snapshot_async_fn=parse_repository_snapshot_async,
            commit_repository_snapshot_fn=_commit_repository_snapshot,
            load_snapshot_fn=_load_snapshot,
            save_snapshot_fn=_save_snapshot,
            persist_run_state_fn=_persist_run_state,
            record_checkpoint_metric_fn=_record_checkpoint_metric,
            update_pending_repository_gauge_fn=_update_pending_repository_gauge,
            publish_runtime_progress_fn=_publish_runtime_progress,
            utc_now_fn=_utc_now,
            telemetry=telemetry,
        )
        finalize_repository_batch(
            builder=builder,
            root_path=root_path,
            run_state=run_state,
            repo_paths=repo_paths,
            snapshots=snapshots,
            merged_imports_map=merged_imports_map,
            component=component,
            family=family,
            source=source,
            info_logger_fn=info_logger_fn,
            error_logger_fn=error_logger_fn,
            finalize_index_batch_fn=finalize_index_batch,
            persist_run_state_fn=_persist_run_state,
            delete_snapshots_fn=_delete_snapshots,
            telemetry=telemetry,
            utc_now_fn=_utc_now,
        )

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
