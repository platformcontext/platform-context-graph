"""Facts-first finalization helpers for post-projection indexing stages."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Callable


def finalize_fact_projection_batch(
    *,
    builder: object,
    root_path: Path,
    run_state: Any,
    repo_paths: list[Path],
    committed_repo_paths: list[Path],
    iter_snapshot_file_data_fn: Callable[[Path], Any],
    info_logger_fn: Any = lambda *_args, **_kwargs: None,
) -> dict[str, Any]:
    """Run facts-first post-projection stages that still depend on snapshots."""

    del root_path
    del repo_paths
    del run_state

    if not committed_repo_paths:
        return {}
    if not callable(getattr(builder, "_create_all_sql_relationships", None)):
        return {}

    def _iter_snapshot_rows() -> Any:
        for repo_path in committed_repo_paths:
            yield from iter_snapshot_file_data_fn(repo_path)

    started = time.perf_counter()
    sql_metrics = builder._create_all_sql_relationships(_iter_snapshot_rows())
    duration = max(time.perf_counter() - started, 0.0)
    if sql_metrics:
        info_logger_fn(
            "Facts-first SQL relationship materialization: "
            + ", ".join(f"{key}={value}" for key, value in sorted(sql_metrics.items()))
        )
    return {
        "sql_relationships": dict(sql_metrics or {}),
        "stage_durations": {"sql_relationships": duration},
    }


def finalize_facts_first_run(
    *,
    run_state: Any,
    persist_run_state_fn: Callable[[Any], None],
    delete_snapshots_fn: Callable[[str], None],
    publish_runtime_progress_fn: Callable[..., None],
    publish_run_repository_coverage_fn: Callable[..., None],
    builder: object,
    repo_paths: list[Path],
    committed_repo_paths: list[Path],
    component: str,
    source: str,
    utc_now_fn: Callable[[], str],
    run_started_at: str | None = None,
    last_metrics: dict[str, Any] | None = None,
) -> None:
    """Close out one facts-first indexing run without legacy finalization."""

    blocking_count = run_state.blocking_repositories()
    has_committed_repos = bool(committed_repo_paths)
    details: dict[str, Any] = {}
    if isinstance(last_metrics, dict):
        if "facts" in last_metrics:
            details["facts_projection"] = last_metrics.get("facts", {})
        if "sql_relationships" in last_metrics:
            details["sql_relationships"] = last_metrics.get("sql_relationships", {})
    run_state.finalization_stage_details = details
    if not has_committed_repos and blocking_count > 0:
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
        publish_runtime_progress_fn(
            ingester=component,
            source=source,
            run_state=run_state,
            repository_count=len(repo_paths),
            status="partial_failure",
        )
        return

    finished_at = utc_now_fn()
    run_state.status = "completed"
    run_state.finalization_status = "completed"
    run_state.finalization_started_at = run_started_at or finished_at
    run_state.finalization_finished_at = finished_at
    stage_durations = (
        dict(last_metrics.get("stage_durations", {}))
        if isinstance(last_metrics, dict)
        and isinstance(last_metrics.get("stage_durations"), dict)
        else {}
    )
    run_state.finalization_duration_seconds = float(sum(stage_durations.values()))
    run_state.finalization_current_stage = None
    run_state.finalization_stage_started_at = None
    run_state.finalization_stage_durations = stage_durations
    persist_run_state_fn(run_state)
    publish_run_repository_coverage_fn(
        builder=builder,
        run_state=run_state,
        repo_paths=repo_paths,
        include_graph_counts=True,
        include_content_counts=True,
    )
    publish_runtime_progress_fn(
        ingester=component,
        source=source,
        run_state=run_state,
        repository_count=len(repo_paths),
        status="completed",
        last_success_at=finished_at,
    )
    delete_snapshots_fn(run_state.run_id)
