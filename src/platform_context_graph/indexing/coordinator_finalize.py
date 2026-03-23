"""Finalization helpers for checkpointed repo-batch indexing."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .coordinator_models import RepositorySnapshot


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
    utc_now_fn: Any,
) -> None:
    """Finalize one successful repo batch or mark the run as partial failure."""

    if run_state.failed_repositories() == 0:
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

        def _stage_progress_callback(stage_name: str) -> None:
            """Persist the current finalization stage as it advances."""

            run_state.finalization_current_stage = stage_name
            run_state.finalization_stage_started_at = utc_now_fn()
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
                stage_timings = finalize_index_batch_fn(
                    builder,
                    snapshots=snapshots,
                    merged_imports_map=merged_imports_map,
                    info_logger_fn=info_logger_fn,
                    stage_progress_callback=_stage_progress_callback,
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
                delete_snapshots_fn(run_state.run_id)
            except Exception as exc:
                run_state.status = "failed"
                run_state.finalization_status = "failed"
                run_state.finalization_finished_at = utc_now_fn()
                run_state.finalization_duration_seconds = time.perf_counter() - started
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
