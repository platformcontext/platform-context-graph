"""Durable repo-batch indexing coordinator with checkpointed resume support."""

from __future__ import annotations

import contextlib
from concurrent.futures import ProcessPoolExecutor
import logging
import multiprocessing
import os
from pathlib import Path
import sys
import time
from typing import Any

from platform_context_graph.observability import get_observability

logger = logging.getLogger(__name__)
from platform_context_graph.repository_identity import (
    git_remote_for_path,
    repository_metadata,
)
from platform_context_graph.utils.debug_log import emit_log_call, warning_logger
from platform_context_graph.collectors.git.indexing import (
    parse_repository_snapshot_async,
    resolve_repository_file_sets,
)
from platform_context_graph.collectors.git.parse_worker import init_parse_worker
from platform_context_graph.facts.state import get_fact_store
from platform_context_graph.facts.state import get_fact_work_queue
from .coordinator_pipeline import process_repository_snapshots
from .coordinator_facts import (
    create_facts_first_commit_callback,
    create_snapshot_fact_emitter,
    finalize_fact_projection_batch,
    facts_first_projection_enabled,
    finalize_facts_first_run,
)
from .coordinator_coverage import publish_run_repository_coverage
from .run_summary import (
    RunSummaryConfig,
    build_run_summary,
    write_run_summary,
)
from .commit_timing import CommitTimingResult

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
    _iter_snapshot_file_data,
    _iter_snapshot_file_data_batches,
    _load_or_create_run,
    _load_run_state_by_id,
    _load_snapshot_metadata,
    _matching_run_states,
    _persist_run_state,
    _record_checkpoint_metric,
    _snapshot_file_data_exists,
    _save_snapshot_file_data,
    _save_snapshot_metadata,
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


def _normalize_batch_commit_result(
    commit_result: Any,
    batch: list[dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return committed and failed file paths from one builder batch result."""

    if commit_result is None:
        return tuple(str(Path(item["path"]).resolve()) for item in batch), ()

    committed = tuple(getattr(commit_result, "committed_file_paths", ()) or ())
    failed = tuple(getattr(commit_result, "failed_file_paths", ()) or ())
    return committed, failed


def _parse_worker_count() -> int:
    """Return the configured repository-parse concurrency."""

    return _positive_int_env("PCG_PARSE_WORKERS", 4)


def _repo_file_parse_multiprocess_enabled() -> bool:
    """Return whether file parsing should use the process-pool path."""

    raw_value = os.getenv("PCG_REPO_FILE_PARSE_MULTIPROCESS")
    return bool(raw_value and raw_value.strip().lower() == "true")


def _parse_strategy_label(*, parse_executor: ProcessPoolExecutor | None) -> str:
    """Return the effective parse strategy label for this run."""

    return "multiprocess" if parse_executor is not None else "threaded"


def _multiprocess_start_method() -> str:
    """Return the process start method for parse workers."""

    configured = os.getenv("PCG_MULTIPROCESS_START_METHOD")
    if configured and configured.strip():
        return configured.strip().lower()
    return "spawn"


def _parse_worker_max_tasks_per_child() -> int | None:
    """Return the optional worker recycle threshold for parse workers."""

    raw_value = os.getenv("PCG_WORKER_MAX_TASKS")
    if raw_value is None or not raw_value.strip():
        return None
    try:
        return max(1, int(raw_value))
    except ValueError:
        return None


@contextlib.contextmanager
def _parse_executor_scope() -> Any:
    """Yield the shared process pool used for file parsing when enabled."""

    if not _repo_file_parse_multiprocess_enabled():
        yield None
        return

    start_method = _multiprocess_start_method()
    mp_context = multiprocessing.get_context(start_method)
    max_tasks_per_child = _parse_worker_max_tasks_per_child()
    executor_kwargs: dict[str, Any] = {
        "max_workers": _parse_worker_count(),
        "mp_context": mp_context,
        "initializer": init_parse_worker,
    }
    if start_method != "fork" and max_tasks_per_child is not None:
        executor_kwargs["max_tasks_per_child"] = max_tasks_per_child
    executor = ProcessPoolExecutor(**executor_kwargs)
    try:
        yield executor
    finally:
        executor.shutdown(wait=True, cancel_futures=True)


def _index_queue_depth(parse_workers: int) -> int:
    """Return the maximum number of parsed repositories awaiting commit."""

    return _positive_int_env("PCG_INDEX_QUEUE_DEPTH", max(2, parse_workers * 2))


def _commit_repository_snapshot(
    builder: Any,
    snapshot: RepositorySnapshot,
    *,
    is_dependency: bool,
    progress_callback: Any | None = None,
    iter_snapshot_file_data_batches_fn: Any | None = None,
    repo_class: str | None = None,
    fact_emission_result: Any | None = None,
) -> CommitTimingResult:
    """Replace one repository's persisted graph/content state from a snapshot."""

    del fact_emission_result

    from .adaptive_batch_config import resolve_batch_config

    batch_config = resolve_batch_config(repo_class=repo_class)

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

    try:
        graph_store.delete_repository(metadata["id"])
    except Exception as exc:
        emit_log_call(
            warning_logger,
            "Failed to delete repository from graph store",
            event_name="index.commit.graph_delete_failed",
            extra_keys={"repo_id": metadata["id"], "error": str(exc)},
            exc_info=exc,
        )
        raise

    if content_provider is not None and content_provider.enabled:
        content_provider.delete_repository_content(metadata["id"])

    builder.add_repository_to_graph(repo_path, is_dependency=is_dependency)
    batch_size = min(
        batch_config.file_batch_size,
        _positive_int_env("PCG_FILE_BATCH_SIZE", 50, maximum=512),
    )
    logger.info(
        "Adaptive batch config: repo_class=%s, file_batch=%d, flush_threshold=%d, "
        "entity_batch=%d, tx_file_limit=%d",
        batch_config.repo_class,
        batch_size,
        batch_config.flush_row_threshold,
        batch_config.entity_batch_size,
        batch_config.tx_file_limit,
    )
    total_files = snapshot.file_count or len(snapshot.file_data)
    committed_files = 0
    timing = CommitTimingResult()

    def _relay_batch_progress(
        *,
        committed_offset: int,
        batch_processed_files: int,
        current_file: str | None = None,
        committed: bool,
    ) -> None:
        """Translate per-batch heartbeats into repo-level progress updates."""

        if not callable(progress_callback):
            return
        progress_callback(
            processed_files=min(committed_offset + batch_processed_files, total_files),
            total_files=total_files,
            current_file=current_file,
            committed=committed,
        )

    if snapshot.file_data:
        while snapshot.file_data:
            batch = snapshot.file_data[:batch_size]
            del snapshot.file_data[:batch_size]
            committed_offset = committed_files
            commit_kwargs: dict[str, Any] = {}
            if callable(progress_callback):
                commit_kwargs["progress_callback"] = (
                    lambda *, processed_files, total_files, current_file=None, committed=False: _relay_batch_progress(
                        committed_offset=committed_offset,
                        batch_processed_files=processed_files,
                        current_file=current_file,
                        committed=committed,
                    )
                )
            _batch_start = time.perf_counter()
            commit_kwargs["adaptive_flush_threshold"] = batch_config.flush_row_threshold
            commit_kwargs["adaptive_entity_batch_size"] = batch_config.entity_batch_size
            commit_kwargs["adaptive_tx_file_limit"] = batch_config.tx_file_limit
            commit_kwargs["adaptive_content_batch_size"] = (
                batch_config.content_upsert_batch_size
            )
            commit_result = builder.commit_file_batch_to_graph(
                batch, repo_path, **commit_kwargs
            )
            _batch_duration = time.perf_counter() - _batch_start
            if commit_result is not None:
                result_entity_totals = getattr(commit_result, "entity_totals", None)
                entity_row_count = (
                    sum(result_entity_totals.values())
                    if result_entity_totals
                    else len(batch)
                )
                graph_dur = getattr(
                    commit_result, "graph_write_duration_seconds", _batch_duration
                )
                timing.accumulate_graph_batch(
                    duration_seconds=graph_dur, row_count=entity_row_count
                )
                if result_entity_totals:
                    timing.merge_entity_totals(result_entity_totals)
                content_dur = getattr(
                    commit_result, "content_write_duration_seconds", 0.0
                )
                if content_dur > 0:
                    timing.content_write_duration_seconds += content_dur
                    timing.content_batch_count += 1
            else:
                timing.accumulate_graph_batch(
                    duration_seconds=_batch_duration, row_count=len(batch)
                )
            committed_paths, failed_paths = _normalize_batch_commit_result(
                commit_result, batch
            )
            committed_files += len(committed_paths)
            if committed_paths:
                _relay_batch_progress(
                    committed_offset=committed_offset,
                    batch_processed_files=len(committed_paths),
                    current_file=committed_paths[-1],
                    committed=True,
                )
            if failed_paths:
                failed_set = set(failed_paths)
                snapshot.file_data[:0] = [
                    file_data
                    for file_data in batch
                    if str(Path(file_data["path"]).resolve()) in failed_set
                ]
                raise RuntimeError(
                    f"Failed to persist {len(failed_paths)} files for repository "
                    f"{repo_path}: {', '.join(failed_paths)}"
                )
        return timing

    if not callable(iter_snapshot_file_data_batches_fn):
        raise FileNotFoundError(
            f"Missing file data batches for repository {repo_path.resolve()}"
        )

    for batch in iter_snapshot_file_data_batches_fn(repo_path, batch_size):
        if not batch:
            continue
        committed_offset = committed_files
        commit_kwargs = {}
        if callable(progress_callback):
            commit_kwargs["progress_callback"] = (
                lambda *, processed_files, total_files, current_file=None, committed=False: _relay_batch_progress(
                    committed_offset=committed_offset,
                    batch_processed_files=processed_files,
                    current_file=current_file,
                    committed=committed,
                )
            )
        _batch_start = time.perf_counter()
        commit_result = builder.commit_file_batch_to_graph(
            batch, repo_path, **commit_kwargs
        )
        _batch_duration = time.perf_counter() - _batch_start
        if commit_result is not None:
            result_entity_totals = getattr(commit_result, "entity_totals", None)
            entity_row_count = (
                sum(result_entity_totals.values())
                if result_entity_totals
                else len(batch)
            )
            graph_dur = getattr(
                commit_result, "graph_write_duration_seconds", _batch_duration
            )
            timing.accumulate_graph_batch(
                duration_seconds=graph_dur, row_count=entity_row_count
            )
            if result_entity_totals:
                timing.merge_entity_totals(result_entity_totals)
            content_dur = getattr(commit_result, "content_write_duration_seconds", 0.0)
            if content_dur > 0:
                timing.content_write_duration_seconds += content_dur
                timing.content_batch_count += 1
        else:
            timing.accumulate_graph_batch(
                duration_seconds=_batch_duration, row_count=len(batch)
            )
        committed_paths, failed_paths = _normalize_batch_commit_result(
            commit_result, batch
        )
        committed_files += len(committed_paths)
        if committed_paths:
            _relay_batch_progress(
                committed_offset=committed_offset,
                batch_processed_files=len(committed_paths),
                current_file=committed_paths[-1],
                committed=True,
            )
        if failed_paths:
            raise RuntimeError(
                f"Failed to persist {len(failed_paths)} files for repository "
                f"{repo_path}: {', '.join(failed_paths)}"
            )
    return timing


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
    publish_run_repository_coverage(
        builder=builder,
        run_state=run_state,
        repo_paths=repo_paths,
        include_graph_counts=False,
        include_content_counts=False,
    )
    with telemetry.index_run(
        component=component,
        mode=family,
        source=source,
        repo_count=len(repo_paths),
        run_id=run_state.run_id,
        resume=resumed,
    ) as run_scope:
        facts_first_enabled = facts_first_projection_enabled()
        if not facts_first_enabled:
            raise RuntimeError(
                "facts-first runtime is required for Python indexing"
            )
        fact_store = get_fact_store()
        fact_work_queue = get_fact_work_queue()
        if fact_store is None or fact_work_queue is None:
            raise RuntimeError(
                "facts-first indexing requires configured fact store and work queue"
            )

        snapshot_fact_emitter = None
        commit_repository_snapshot_fn: Any = _commit_repository_snapshot
        if facts_first_enabled:
            snapshot_fact_emitter = create_snapshot_fact_emitter(
                source_run_id=run_state.run_id,
                fact_store=fact_store,
                work_queue=fact_work_queue,
            )
            commit_repository_snapshot_fn = create_facts_first_commit_callback(
                builder=builder,
                source_run_id=run_state.run_id,
                fact_store=fact_store,
                work_queue=fact_work_queue,
                fact_emission_results=getattr(
                    snapshot_fact_emitter,
                    "fact_emission_results",
                    None,
                ),
                info_logger_fn=info_logger_fn,
                warning_logger_fn=warning_logger_fn,
            )
        with _parse_executor_scope() as parse_executor:
            parse_strategy = _parse_strategy_label(parse_executor=parse_executor)
            committed_repo_paths, _merged_imports_map, repo_telemetry_map = (
                await process_repository_snapshots(
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
                    commit_repository_snapshot_fn=commit_repository_snapshot_fn,
                    iter_snapshot_file_data_batches_fn=_iter_snapshot_file_data_batches,
                    load_snapshot_metadata_fn=_load_snapshot_metadata,
                    snapshot_file_data_exists_fn=_snapshot_file_data_exists,
                    save_snapshot_metadata_fn=_save_snapshot_metadata,
                    save_snapshot_file_data_fn=_save_snapshot_file_data,
                    emit_snapshot_facts_fn=snapshot_fact_emitter,
                    persist_run_state_fn=_persist_run_state,
                    record_checkpoint_metric_fn=_record_checkpoint_metric,
                    update_pending_repository_gauge_fn=_update_pending_repository_gauge,
                    publish_runtime_progress_fn=_publish_runtime_progress,
                    publish_run_repository_coverage_fn=publish_run_repository_coverage,
                    utc_now_fn=_utc_now,
                    telemetry=telemetry,
                    parse_executor=parse_executor,
                    parse_strategy=parse_strategy,
                    parse_workers=_parse_worker_count(),
                    facts_first_mode=facts_first_enabled,
                )
            )
        if facts_first_enabled:
            facts_finalize_metrics = finalize_fact_projection_batch(
                builder=builder,
                root_path=root_path,
                run_state=run_state,
                repo_paths=repo_paths,
                committed_repo_paths=committed_repo_paths,
                iter_snapshot_file_data_fn=lambda repo_path: _iter_snapshot_file_data(
                    run_state.run_id, repo_path
                ),
                info_logger_fn=info_logger_fn,
            )
            finalize_facts_first_run(
                run_state=run_state,
                repo_paths=repo_paths,
                committed_repo_paths=committed_repo_paths,
                builder=builder,
                component=component,
                source=source,
                persist_run_state_fn=_persist_run_state,
                delete_snapshots_fn=_delete_snapshots,
                publish_run_repository_coverage_fn=publish_run_repository_coverage,
                publish_runtime_progress_fn=_publish_runtime_progress,
                utc_now_fn=_utc_now,
                last_metrics={
                    "projected_repositories": len(committed_repo_paths),
                    **(facts_finalize_metrics or {}),
                },
            )
            if run_state.status == "running":
                run_state.status = "completed"
            if run_state.finalization_status == "pending":
                run_state.finalization_status = "completed"

        try:
            summary_config = RunSummaryConfig.from_env()
            summary = build_run_summary(
                run_state=run_state,
                repo_telemetry_map=repo_telemetry_map,
                config=summary_config,
                started_at=run_state.created_at,
                finished_at=run_state.updated_at or _utc_now(),
            )
            summary_path = write_run_summary(summary, run_id=run_state.run_id)
            info_logger_fn(f"Run summary artifact written to {summary_path}")
        except Exception as summary_exc:
            warning_logger_fn(f"Failed to write run summary artifact: {summary_exc}")

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
