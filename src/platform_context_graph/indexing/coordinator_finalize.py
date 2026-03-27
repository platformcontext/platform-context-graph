"""Finalization helpers for checkpointed repo-batch indexing."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..utils.debug_log import emit_log_call

_FINALIZATION_COVERAGE_HEARTBEAT_SECONDS = 15.0


def finalize_repository_batch(
    *,
    builder: Any,
    root_path: Path,
    run_state: Any,
    repo_paths: list[Path],
    committed_repo_paths: list[Path],
    iter_snapshot_file_data_fn: Any,
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
    utc_now_fn: Any,
    publish_run_repository_coverage_fn: Any,
    publish_runtime_progress_fn: Any,
) -> None:
    """Finalize one successful repo batch or mark the run as partial failure."""

    def _publish_runtime_status(*, last_success_at: str | None = None) -> None:
        """Project run-level status into the runtime ingester view."""

        if not callable(publish_runtime_progress_fn):
            return
        publish_runtime_progress_fn(
            ingester=component,
            source=source,
            run_state=run_state,
            repository_count=len(repo_paths),
            status="indexing" if run_state.status == "running" else run_state.status,
            last_success_at=last_success_at,
        )

    if run_state.blocking_repositories() == 0:
        started_at = utc_now_fn()
        started = time.perf_counter()
        run_state.finalization_status = "running"
        run_state.finalization_started_at = started_at
        run_state.finalization_finished_at = None
        run_state.finalization_duration_seconds = None
        run_state.finalization_current_stage = None
        run_state.finalization_stage_started_at = None
        run_state.finalization_stage_durations = {}
        run_state.finalization_stage_details = {}
        persist_run_state_fn(run_state)
        publish_run_repository_coverage_fn(
            builder=builder,
            run_state=run_state,
            repo_paths=repo_paths,
            include_graph_counts=True,
            include_content_counts=True,
        )
        _publish_runtime_status()
        last_coverage_publish = time.monotonic()

        def _stage_progress_callback(stage_name: str, **details: Any) -> None:
            """Persist the current finalization stage as it advances."""

            nonlocal last_coverage_publish
            stage_changed = run_state.finalization_current_stage != stage_name
            if stage_changed:
                run_state.finalization_current_stage = stage_name
                run_state.finalization_stage_started_at = utc_now_fn()
                run_state.finalization_stage_details[stage_name] = {}
            if details:
                stage_details = run_state.finalization_stage_details.get(stage_name, {})
                if not isinstance(stage_details, dict):
                    stage_details = {}
                stage_details.update(details)
                run_state.finalization_stage_details[stage_name] = stage_details
            persist_run_state_fn(run_state)
            _publish_runtime_status()
            now = time.monotonic()
            if (
                stage_changed
                or now - last_coverage_publish
                >= _FINALIZATION_COVERAGE_HEARTBEAT_SECONDS
            ):
                last_coverage_publish = now
                publish_run_repository_coverage_fn(
                    builder=builder,
                    run_state=run_state,
                    repo_paths=repo_paths,
                    include_graph_counts=False,
                    include_content_counts=False,
                )

        with telemetry.start_span(
            "pcg.index.finalize",
            component=component,
            attributes={
                "pcg.index.run_id": run_state.run_id,
                "pcg.index.repo_count": len(repo_paths),
            },
        ) as finalize_span:
            try:
                stage_timings = finalize_index_batch_fn(
                    builder,
                    committed_repo_paths=committed_repo_paths,
                    iter_snapshot_file_data_fn=iter_snapshot_file_data_fn,
                    merged_imports_map=merged_imports_map,
                    info_logger_fn=info_logger_fn,
                    stage_progress_callback=_stage_progress_callback,
                    run_id=run_state.run_id,
                )
                run_state.finalization_finished_at = utc_now_fn()
                run_state.finalization_duration_seconds = time.perf_counter() - started
                run_state.finalization_current_stage = None
                run_state.finalization_stage_started_at = None
                run_state.finalization_stage_durations = dict(stage_timings or {})
                call_relationship_metrics = getattr(
                    builder, "_last_call_relationship_metrics", None
                )
                if call_relationship_metrics is not None:
                    run_state.finalization_stage_details = {
                        "function_calls": dict(call_relationship_metrics)
                    }
                run_state.finalization_status = "completed"
                run_state.status = "completed"
                persist_run_state_fn(run_state)
                publish_run_repository_coverage_fn(
                    builder=builder,
                    run_state=run_state,
                    repo_paths=repo_paths,
                    include_graph_counts=True,
                    include_content_counts=True,
                )
                _publish_runtime_status(
                    last_success_at=run_state.finalization_finished_at
                )
                delete_snapshots_fn(run_state.run_id)
            except Exception as exc:
                run_state.status = "failed"
                run_state.finalization_status = "failed"
                run_state.finalization_finished_at = utc_now_fn()
                run_state.finalization_duration_seconds = time.perf_counter() - started
                run_state.last_error = str(exc)
                persist_run_state_fn(run_state)
                publish_run_repository_coverage_fn(
                    builder=builder,
                    run_state=run_state,
                    repo_paths=repo_paths,
                    include_graph_counts=True,
                    include_content_counts=True,
                )
                if finalize_span is not None:
                    finalize_span.record_exception(exc)
                _publish_runtime_status()
                emit_log_call(
                    error_logger_fn,
                    f"Failed to finalize repository batch for {root_path.resolve()}",
                    event_name="index.finalization.failed",
                    extra_keys={
                        "run_id": run_state.run_id,
                        "root_path": str(root_path.resolve()),
                        "repository_count": len(repo_paths),
                        "blocking_repositories": run_state.blocking_repositories(),
                    },
                    exc_info=exc,
                )
        return

    run_state.status = "partial_failure"
    run_state.finalization_status = "pending"
    persist_run_state_fn(run_state)
    publish_run_repository_coverage_fn(
        builder=builder,
        run_state=run_state,
        repo_paths=repo_paths,
        include_graph_counts=True,
        include_content_counts=True,
    )
    emit_log_call(
        info_logger_fn,
        "Repository batch finalization deferred because repositories are still blocking",
        event_name="index.finalization.deferred",
        extra_keys={
            "run_id": run_state.run_id,
            "root_path": str(root_path.resolve()),
            "repository_count": len(repo_paths),
            "blocking_repositories": run_state.blocking_repositories(),
        },
    )
    _publish_runtime_status()
