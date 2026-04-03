"""Internal async pipeline helpers for checkpointed repo-batch indexing."""

from __future__ import annotations

import asyncio
import multiprocessing
import os
import threading
import time
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from platform_context_graph.collectors.git.indexing import merge_import_maps
from platform_context_graph.utils.debug_log import emit_log_call

from platform_context_graph.graph.persistence.worker import (
    get_commit_worker_connection_params,
)

from .coordinator_finalize import finalize_repository_batch
from .memory_diagnostics import log_memory_usage, read_memory_usage_sample
from .coordinator_models import (
    ACTIVE_REPO_STATES,
    RepositorySnapshotMetadata,
)
from .repo_telemetry import (
    RepoTelemetry,
    create_repo_telemetry,
    record_memory_sample,
)
from .anomaly_detection import (
    check_anomalies,
    class_adjusted_thresholds,
    emit_anomaly_events,
    load_anomaly_thresholds,
)
from .coordinator_async_commit import (
    _ASYNC_COMMIT_ENABLED,
    commit_repository_snapshot_async,
)
from .repo_classification import (
    classify_repo_pre_parse,
    classify_repo_runtime,
    load_repo_class_overrides,
)

_ENTITY_FIELDS = ("functions", "classes", "variables", "interfaces", "structs", "enums")


def _count_snapshot_entities(file_data: list[dict[str, Any]]) -> int:
    """Count total entities across all parsed files for reclassification."""
    total = 0
    for fd in file_data:
        for field in _ENTITY_FIELDS:
            total += len(fd.get(field, []))
    return total


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
    emit_snapshot_facts_fn: Any | None = None,
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
    facts_first_mode: bool = False,
) -> tuple[list[Path], dict[str, list[str]], dict[str, RepoTelemetry]]:
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
    repo_telemetry_map: dict[str, RepoTelemetry] = {}
    # Create minimal telemetry entries for already-completed repos
    for completed_path in committed_repo_paths:
        completed_key = str(completed_path)
        repo_state = run_state.repositories.get(completed_key)
        if repo_state is not None and completed_key not in repo_telemetry_map:
            tel = create_repo_telemetry(completed_path)
            tel.status = "completed"
            tel.parsed_file_count = getattr(repo_state, "file_count", 0) or 0
            tel.commit_duration_seconds = getattr(
                repo_state, "commit_duration_seconds", None
            )
            repo_telemetry_map[completed_key] = tel
    anomaly_thresholds = load_anomaly_thresholds()
    repo_class_overrides = load_repo_class_overrides()
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
            repo_tel = create_repo_telemetry(repo_path)
            repo_tel.discovered_file_count = len(repo_file_sets[repo_path])
            override_class = repo_class_overrides.get(repo_tel.repo_name)
            if override_class:
                repo_tel.repo_class = override_class
            else:
                repo_tel.repo_class = classify_repo_pre_parse(
                    discovered_file_count=repo_tel.discovered_file_count
                )
            repo_telemetry_map[repo_key] = repo_tel

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
                repo_tel.parse_queue_wait_seconds = queue_wait_duration
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
                            repo_class=repo_tel.repo_class,
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
                            repo_class=repo_tel.repo_class,
                        )
                        if resume_candidate:
                            telemetry.record_index_repositories(
                                component=component,
                                phase="resumed",
                                count=1,
                                mode=family,
                                source=source,
                                repo_class=repo_tel.repo_class,
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
                        record_memory_sample(
                            repo_tel, "parse_start", read_memory_usage_sample()
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
                        record_memory_sample(
                            repo_tel, "parse_end", read_memory_usage_sample()
                        )
                        repo_tel.parse_duration_seconds = parse_duration
                        repo_tel.parsed_file_count = snapshot.file_count
                        entity_count = _count_snapshot_entities(snapshot.file_data)
                        pre_class = repo_tel.repo_class or "medium"
                        upgraded_class = classify_repo_runtime(
                            pre_class=pre_class,
                            parse_duration_seconds=parse_duration,
                            parsed_file_count=snapshot.file_count,
                            entity_count=entity_count,
                        )
                        if upgraded_class != pre_class:
                            emit_log_call(
                                info_logger_fn,
                                f"Runtime reclassification {repo_path.name}: "
                                f"{pre_class} -> {upgraded_class}",
                                event_name="index.repository.reclassified",
                                extra_keys={
                                    "repo_path": str(repo_path.resolve()),
                                    "pre_class": pre_class,
                                    "runtime_class": upgraded_class,
                                    "parse_duration": round(parse_duration, 3),
                                    "entity_count": entity_count,
                                },
                            )
                        repo_tel.repo_class = upgraded_class
                        if hasattr(telemetry, "record_index_stage_duration"):
                            telemetry.record_index_stage_duration(
                                component=component,
                                mode=family,
                                source=source,
                                stage="repository_parse",
                                duration_seconds=parse_duration,
                                parse_strategy=parse_strategy,
                                parse_workers=parse_workers,
                                repo_class=repo_tel.repo_class,
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
                    fact_emission_result = None
                    if callable(emit_snapshot_facts_fn):
                        fact_emission_result = emit_snapshot_facts_fn(
                            run_id=run_state.run_id,
                            repo_path=repo_path,
                            snapshot=snapshot,
                            is_dependency=is_dependency,
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
                        emit_log_call(
                            info_logger_fn,
                            f"Queueing snapshot for commit: {repo_path.resolve()} "
                            f"(qsize_before={snapshot_queue.qsize()})",
                            event_name="index.snapshot.queue_put",
                            extra_keys={
                                "repo_path": str(repo_path.resolve()),
                                "queue_size_before": snapshot_queue.qsize(),
                            },
                        )
                        await snapshot_queue.put(
                            (
                                repo_path,
                                snapshot,
                                started,
                                commit_wait_started,
                                repo_tel,
                                fact_emission_result,
                            )
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
            if repo_key in repo_telemetry_map:
                repo_telemetry_map[repo_key].status = "failed"
                repo_telemetry_map[repo_key].error = str(exc)
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
                repo_class=(
                    repo_telemetry_map[repo_key].repo_class
                    if repo_key in repo_telemetry_map
                    else None
                ),
            )
            if started is not None:
                telemetry.record_index_repository_duration(
                    component=component,
                    mode=family,
                    source=source,
                    status="failed",
                    duration_seconds=time.perf_counter() - started,
                    repo_class=(
                        repo_telemetry_map[repo_key].repo_class
                        if repo_key in repo_telemetry_map
                        else None
                    ),
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

    raw = os.environ.get("PCG_COMMIT_WORKERS", "1")
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        commit_concurrency = 1
    else:
        commit_concurrency = max(1, min(parsed, 32))
    if facts_first_mode:
        commit_concurrency = 1
    emit_log_call(
        info_logger_fn,
        f"Commit worker config: PCG_COMMIT_WORKERS={raw!r}, "
        f"parsed={parsed if 'parsed' in dir() else 'N/A'}, "
        f"commit_concurrency={commit_concurrency}",
        event_name="index.commit_workers.config",
        extra_keys={
            "raw_env": raw,
            "commit_concurrency": commit_concurrency,
        },
    )

    # Create ProcessPoolExecutor when commit_concurrency > 1 for true parallelism
    _commit_process_pool: ProcessPoolExecutor | None = None
    _connection_params: dict[str, str | None] | None = None
    if commit_concurrency > 1:
        mp_start_method = os.getenv("PCG_MULTIPROCESS_START_METHOD", "spawn")
        mp_context = multiprocessing.get_context(mp_start_method)
        _commit_process_pool = ProcessPoolExecutor(
            max_workers=commit_concurrency,
            mp_context=mp_context,
        )
        _connection_params = get_commit_worker_connection_params()
        emit_log_call(
            info_logger_fn,
            f"Using ProcessPoolExecutor with {commit_concurrency} commit workers",
            event_name="index.commit_pool.created",
            extra_keys={"commit_concurrency": commit_concurrency},
        )

    commit_state_lock = asyncio.Lock()
    _checkpoint_write_lock = threading.Lock()

    def _safe_persist_run_state() -> None:
        """Serialize checkpoint writes across commit worker threads."""
        with _checkpoint_write_lock:
            persist_run_state_fn(run_state)

    async def _commit_snapshots(worker_id: int = 0) -> None:
        """Commit parsed repository snapshots from the queue in arrival order."""

        emit_log_call(
            info_logger_fn,
            f"Commit worker {worker_id} started, waiting for snapshots",
            event_name="index.commit_worker.started",
            extra_keys={"worker_id": worker_id},
        )
        while True:
            emit_log_call(
                info_logger_fn,
                f"Commit worker {worker_id} waiting on queue (qsize={snapshot_queue.qsize()})",
                event_name="index.commit_worker.waiting",
                extra_keys={
                    "worker_id": worker_id,
                    "queue_size": snapshot_queue.qsize(),
                },
            )
            item = await snapshot_queue.get()
            if item is queue_sentinel:
                emit_log_call(
                    info_logger_fn,
                    f"Commit worker {worker_id} received sentinel, exiting",
                    event_name="index.commit_worker.sentinel",
                    extra_keys={"worker_id": worker_id},
                )
                snapshot_queue.task_done()
                return

            (
                repo_path,
                snapshot,
                started,
                snapshot_ready_started,
                repo_tel,
                fact_emission_result,
            ) = item
            repo_state = run_state.repositories[str(repo_path.resolve())]
            commit_started: float | None = None
            last_commit_progress_publish = 0.0
            last_commit_coverage_publish = 0.0
            try:
                commit_wait_duration = time.perf_counter() - snapshot_ready_started
                repo_tel.commit_queue_wait_seconds = commit_wait_duration
                if hasattr(telemetry, "record_index_stage_duration"):
                    telemetry.record_index_stage_duration(
                        component=component,
                        mode=family,
                        source=source,
                        stage="repository_commit_wait",
                        duration_seconds=commit_wait_duration,
                        parse_strategy=parse_strategy,
                        parse_workers=parse_workers,
                        repo_class=repo_tel.repo_class,
                    )
                emit_log_call(
                    info_logger_fn,
                    f"Commit worker {worker_id}: acquired slot for {repo_path.resolve()} after "
                    f"{commit_wait_duration:.3f}s",
                    event_name="index.repository.commit_wait.completed",
                    extra_keys={
                        "run_id": run_state.run_id,
                        "repo_path": str(repo_path.resolve()),
                        "worker_id": worker_id,
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
                record_memory_sample(
                    repo_tel, "commit_start", read_memory_usage_sample()
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

                    with _checkpoint_write_lock:
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
                        _safe_persist_run_state()
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
                        "pcg.index.commit_workers": commit_concurrency,
                    },
                ):
                    _iter_fn = lambda repo_path, batch_size: (
                        iter_snapshot_file_data_batches_fn(
                            run_state.run_id,
                            repo_path,
                            batch_size=batch_size,
                        )
                    )
                    to_thread_fn = getattr(asyncio_module, "to_thread", asyncio.to_thread)
                    if facts_first_mode:
                        commit_timing_result = await to_thread_fn(
                            commit_repository_snapshot_fn,
                            builder,
                            snapshot,
                            is_dependency=is_dependency,
                            progress_callback=_commit_progress_callback,
                            iter_snapshot_file_data_batches_fn=_iter_fn,
                            repo_class=repo_tel.repo_class,
                            fact_emission_result=fact_emission_result,
                        )
                    elif _commit_process_pool is not None:
                        # CW > 1: use ProcessPoolExecutor for true parallelism
                        commit_timing_result = await commit_repository_snapshot_async(
                            builder,
                            snapshot,
                            is_dependency=is_dependency,
                            progress_callback=_commit_progress_callback,
                            iter_snapshot_file_data_batches_fn=_iter_fn,
                            repo_class=repo_tel.repo_class,
                            process_executor=_commit_process_pool,
                            connection_params=_connection_params,
                        )
                    elif _ASYNC_COMMIT_ENABLED:
                        # CW == 1: async commit with ThreadPoolExecutor
                        commit_timing_result = await commit_repository_snapshot_async(
                            builder,
                            snapshot,
                            is_dependency=is_dependency,
                            progress_callback=_commit_progress_callback,
                            iter_snapshot_file_data_batches_fn=_iter_fn,
                            repo_class=repo_tel.repo_class,
                        )
                    else:
                        # CW == 1: sync commit via asyncio.to_thread
                        commit_timing_result = await to_thread_fn(
                            commit_repository_snapshot_fn,
                            builder,
                            snapshot,
                            is_dependency=is_dependency,
                            progress_callback=_commit_progress_callback,
                            iter_snapshot_file_data_batches_fn=_iter_fn,
                            repo_class=repo_tel.repo_class,
                        )
                    emit_log_call(
                        info_logger_fn,
                        f"Commit worker {worker_id}: finished commit for {repo_path.resolve()}",
                        event_name="index.commit_worker.commit_done",
                        extra_keys={
                            "worker_id": worker_id,
                            "repo_path": str(repo_path.resolve()),
                        },
                    )
                    if commit_timing_result is not None:
                        repo_tel.graph_write_duration_seconds = (
                            commit_timing_result.graph_write_duration_seconds
                        )
                        repo_tel.content_write_duration_seconds = (
                            commit_timing_result.content_write_duration_seconds
                        )
                        repo_tel.max_graph_batch_rows = (
                            commit_timing_result.max_graph_batch_rows
                        )
                        repo_tel.max_content_batch_rows = (
                            commit_timing_result.max_content_batch_rows
                        )
                async with commit_state_lock:
                    committed_repo_paths.append(repo_path.resolve())
                    merge_import_maps(merged_imports_map, snapshot.imports_map)
                snapshot.file_data = []
                commit_finished_at = utc_now_fn()
                with _checkpoint_write_lock:
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
                _safe_persist_run_state()
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
                    context=(f"Repository commit memory repo={repo_path.resolve()}"),
                )
                mem_sample = read_memory_usage_sample()
                record_memory_sample(repo_tel, "commit_end", mem_sample)
                telemetry.record_index_repositories(
                    component=component,
                    phase="completed",
                    count=1,
                    mode=family,
                    source=source,
                    repo_class=repo_tel.repo_class,
                )
                telemetry.record_index_repository_duration(
                    component=component,
                    mode=family,
                    source=source,
                    status="completed",
                    duration_seconds=time.perf_counter() - started,
                    repo_class=repo_tel.repo_class,
                )
                commit_duration = (
                    time.perf_counter() - commit_started
                    if commit_started is not None
                    else 0.0
                )
                repo_tel.commit_duration_seconds = commit_duration
                repo_tel.total_repository_duration_seconds = (
                    time.perf_counter() - started if started else None
                )
                repo_tel.status = "completed"
                adjusted = class_adjusted_thresholds(
                    anomaly_thresholds, repo_tel.repo_class
                )
                detected = check_anomalies(repo_tel, adjusted)
                if detected:
                    repo_tel.anomalies.extend(detected)
                    emit_anomaly_events(
                        detected,
                        warning_logger_fn=warning_logger_fn,
                        run_id=run_state.run_id,
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
                        repo_class=repo_tel.repo_class,
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
                repo_tel.status = "failed"
                repo_tel.error = str(exc)
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
                    repo_class=repo_tel.repo_class,
                )
                telemetry.record_index_repository_duration(
                    component=component,
                    mode=family,
                    source=source,
                    status="commit_incomplete",
                    duration_seconds=time.perf_counter() - started,
                    repo_class=repo_tel.repo_class,
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

    emit_log_call(
        info_logger_fn,
        f"Creating {commit_concurrency} commit worker(s)",
        event_name="index.commit_workers.creating",
        extra_keys={"commit_concurrency": commit_concurrency},
    )
    commit_tasks = [
        asyncio_module.create_task(_commit_snapshots(worker_id=i))
        for i in range(commit_concurrency)
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
        # Shutdown ProcessPoolExecutor if we created one
        if _commit_process_pool is not None:
            _commit_process_pool.shutdown(wait=True)
            emit_log_call(
                info_logger_fn,
                "ProcessPoolExecutor shutdown complete",
                event_name="index.commit_pool.shutdown",
            )
    if escaped_parse_exception is not None:
        raise escaped_parse_exception
    return committed_repo_paths, merged_imports_map, repo_telemetry_map


__all__ = [
    "finalize_repository_batch",
    "prepare_repository_snapshots",
    "process_repository_snapshots",
]
