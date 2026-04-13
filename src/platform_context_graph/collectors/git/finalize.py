"""Finalization helpers for post-commit indexing stages."""

from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any, Iterable

from platform_context_graph.indexing.post_commit_writer import (
    PostCommitStage,
    PostCommitWriteResult,
    execute_post_commit_stages,
)
from platform_context_graph.indexing.memory_diagnostics import log_memory_usage
from platform_context_graph.utils.debug_log import emit_log_call


def _iter_repository_file_data(
    committed_repo_paths: Iterable[Path],
    iter_snapshot_file_data_fn: Any,
) -> Iterable[dict[str, Any]]:
    """Yield parsed file payloads one committed repository at a time."""

    for repo_path in committed_repo_paths:
        repo_file_data = iter_snapshot_file_data_fn(repo_path)
        if repo_file_data is None:
            raise FileNotFoundError(
                f"Missing file data snapshot for committed repository {repo_path.resolve()}"
            )
        yield from repo_file_data


def _accumulate_metric_totals(
    totals: dict[str, float | int],
    current: dict[str, float | int] | None,
) -> None:
    """Add one metrics payload into a mutable aggregate in place."""

    if not current:
        return
    for key, value in current.items():
        if isinstance(value, (int, float)):
            totals[key] = totals.get(key, 0) + value


def _supports_keyword_arguments(callback: Any, keyword_names: tuple[str, ...]) -> bool:
    """Return whether a callable accepts the requested keyword arguments."""

    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return False
    accepted = {parameter.name for parameter in parameters}
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return True
    return all(name in accepted for name in keyword_names)


def _filter_supported_keyword_arguments(
    callback: Any,
    keyword_arguments: dict[str, Any],
) -> dict[str, Any]:
    """Return only the keyword arguments that one callback can consume."""

    try:
        parameters = inspect.signature(callback).parameters.values()
    except (TypeError, ValueError):
        return {}
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return keyword_arguments
    accepted = {parameter.name for parameter in parameters}
    return {
        name: value for name, value in keyword_arguments.items() if name in accepted
    }


_PER_REPO_STAGES = frozenset({"inheritance"})


def finalize_single_repository(
    builder: Any,
    *,
    repo_path: Path,
    iter_snapshot_file_data_fn: Any,
    merged_imports_map: dict[str, list[str]],
    info_logger_fn: Any,
) -> dict[str, float]:
    """Run per-repo finalization stages (inheritance + workloads) for one repository.

    This can be called immediately after a single repo commit to reduce
    end-of-batch finalization wall time.  The caller is responsible for
    ensuring the file data snapshot is available via *iter_snapshot_file_data_fn*.
    """

    stage_timings: dict[str, float] = {}

    def _repo_file_data_iter() -> Iterable[dict[str, Any]]:
        """Yield file payloads for the single repository."""

        data = iter_snapshot_file_data_fn(repo_path)
        if data is None:
            raise FileNotFoundError(
                f"Missing file data snapshot for repository {repo_path.resolve()}"
            )
        yield from data

    # Only inheritance is truly per-repo. Workloads materialization is global
    # (queries and MERGEs across all repos), so it must stay in batch finalization.
    for stage_name, stage_fn in (
        (
            "inheritance",
            lambda: builder._create_all_inheritance_links(
                _repo_file_data_iter(),
                merged_imports_map,
            ),
        ),
    ):
        log_memory_usage(
            info_logger_fn,
            context=f"Before per-repo finalization stage {stage_name} for {repo_path.name}",
        )
        stage_start = time.monotonic()
        stage_fn()
        elapsed = time.monotonic() - stage_start
        stage_timings[stage_name] = elapsed
        log_memory_usage(
            info_logger_fn,
            context=f"After per-repo finalization stage {stage_name} for {repo_path.name}",
        )
        emit_log_call(
            info_logger_fn,
            f"Per-repo finalization stage {stage_name} for {repo_path.name} "
            f"done in {elapsed:.1f}s",
            event_name="index.finalization.per_repo_stage.completed",
            extra_keys={
                "stage": stage_name,
                "repo_path": str(repo_path.resolve()),
                "duration_seconds": round(elapsed, 3),
            },
        )

    return stage_timings


def finalize_index_batch(
    builder: Any,
    *,
    committed_repo_paths: list[Path],
    iter_snapshot_file_data_fn: Any,
    merged_imports_map: dict[str, list[str]],
    info_logger_fn: Any,
    stage_progress_callback: Any | None = None,
    run_id: str | None = None,
    telemetry: Any | None = None,
    component: str | None = None,
    mode: str | None = None,
    source: str | None = None,
    parse_strategy: str = "threaded",
    parse_workers: int = 1,
    skip_per_repo_stages: bool = False,
    stages: list[str] | None = None,
) -> PostCommitWriteResult:
    """Create cross-file and cross-repo relationships after repo commits finish.

    When *skip_per_repo_stages* is ``True`` the ``inheritance`` and
    ``workloads`` stages are omitted because they were already executed
    per-repo via :func:`finalize_single_repository`.
    """

    emit_log_call(
        info_logger_fn,
        "Creating inheritance links and function calls for "
        f"{len(committed_repo_paths)} committed repositories...",
        event_name="index.finalization.started",
        extra_keys={
            "repository_count": len(committed_repo_paths),
            "run_id": run_id,
            "skip_per_repo_stages": skip_per_repo_stages,
        },
    )
    total_start = time.monotonic()
    committed_repo_data_iter = lambda: _iter_repository_file_data(
        committed_repo_paths,
        iter_snapshot_file_data_fn,
    )

    def _notify_stage_progress(stage_name: str, **kwargs: Any) -> None:
        """Forward stage progress to the caller using the shared callback contract."""

        if not callable(stage_progress_callback):
            return
        forwarded_kwargs = _filter_supported_keyword_arguments(
            stage_progress_callback,
            kwargs,
        )
        if forwarded_kwargs:
            stage_progress_callback(stage_name, **forwarded_kwargs)
            return
        if not kwargs or kwargs.get("status") == "started":
            stage_progress_callback(stage_name)

    def _with_stage_memory(stage_name: str, stage_fn: Any) -> Any:
        """Wrap one stage with memory diagnostics while preserving metrics."""

        def _run_stage() -> Any:
            """Execute one finalization stage with before/after memory logging."""

            log_memory_usage(
                info_logger_fn,
                context=f"Before finalization stage {stage_name}",
            )
            result = stage_fn()
            log_memory_usage(
                info_logger_fn,
                context=f"After finalization stage {stage_name}",
            )
            return result

        return _run_stage

    def _run_function_call_stage() -> dict[str, float | int]:
        """Materialize function-call edges and aggregate stage-level metrics."""

        aggregated_metrics: dict[str, float | int] = {}
        create_all_function_calls = builder._create_all_function_calls
        for repo_path in committed_repo_paths:
            repo_file_data = iter_snapshot_file_data_fn(repo_path)
            if repo_file_data is None:
                raise FileNotFoundError(
                    "Missing file data snapshot for committed repository "
                    f"{repo_path.resolve()}"
                )
            kwargs: dict[str, Any] = {}
            if _supports_keyword_arguments(
                create_all_function_calls,
                ("progress_callback",),
            ):
                kwargs["progress_callback"] = lambda **callback_kwargs: (
                    _notify_stage_progress(
                        "function_calls",
                        **callback_kwargs,
                    )
                )
            _accumulate_metric_totals(
                aggregated_metrics,
                create_all_function_calls(
                    repo_file_data,
                    merged_imports_map,
                    **kwargs,
                ),
            )
        setattr(builder, "_last_call_relationship_metrics", aggregated_metrics)
        return aggregated_metrics

    def _run_workload_stage() -> dict[str, int]:
        """Materialize workloads, passing targeted repos when supported."""

        materialize_workloads = builder._materialize_workloads
        kwargs: dict[str, Any] = {}
        if _supports_keyword_arguments(
            materialize_workloads,
            ("progress_callback",),
        ):
            kwargs["progress_callback"] = lambda **callback_kwargs: (
                _notify_stage_progress(
                    "workloads",
                    **callback_kwargs,
                )
            )
        if _supports_keyword_arguments(
            materialize_workloads,
            ("committed_repo_paths",),
        ):
            kwargs["committed_repo_paths"] = committed_repo_paths
        return materialize_workloads(**kwargs)

    all_stages = [
        PostCommitStage(
            name="inheritance",
            runner=_with_stage_memory(
                "inheritance",
                lambda: builder._create_all_inheritance_links(
                    committed_repo_data_iter(),
                    merged_imports_map,
                ),
            ),
        ),
        PostCommitStage(
            name="function_calls",
            runner=_with_stage_memory("function_calls", _run_function_call_stage),
        ),
        PostCommitStage(
            name="sql_relationships",
            runner=_with_stage_memory(
                "sql_relationships",
                lambda: builder._create_all_sql_relationships(committed_repo_data_iter()),
            ),
        ),
        PostCommitStage(
            name="infra_links",
            runner=_with_stage_memory(
                "infra_links",
                lambda: builder._create_all_infra_links(committed_repo_data_iter()),
            ),
        ),
        PostCommitStage(
            name="workloads",
            runner=_with_stage_memory("workloads", _run_workload_stage),
        ),
        PostCommitStage(
            name="relationship_resolution",
            runner=_with_stage_memory(
                "relationship_resolution",
                lambda: builder._resolve_repository_relationships(
                    committed_repo_paths,
                    run_id=run_id,
                ),
            ),
        ),
    ]
    available_stage_names = {stage.name for stage in all_stages}
    if stages is not None:
        unknown_stages = sorted(set(stages) - available_stage_names)
        if unknown_stages:
            raise ValueError(
                "Unsupported finalization stages: " + ", ".join(unknown_stages)
            )
        requested_stage_names = set(stages)
        all_stages = [
            stage for stage in all_stages if stage.name in requested_stage_names
        ]
    result = execute_post_commit_stages(
        stages=all_stages,
        info_logger_fn=info_logger_fn,
        stage_progress_callback=stage_progress_callback,
        telemetry=telemetry,
        component=component,
        mode=mode,
        source=source,
        parse_strategy=parse_strategy,
        parse_workers=parse_workers,
        repo_count=len(committed_repo_paths),
        run_id=run_id,
        skipped_stage_names=_PER_REPO_STAGES if skip_per_repo_stages else set(),
    )
    total_elapsed = time.monotonic() - total_start
    timings_summary = ", ".join(
        f"{stage_name}={duration:.1f}s"
        for stage_name, duration in result.stage_timings.items()
    )
    emit_log_call(
        info_logger_fn,
        f"Finalization timings: {timings_summary}, total={total_elapsed:.1f}s",
        event_name="index.finalization.completed",
        extra_keys={
            "run_id": run_id,
            "total_seconds": round(total_elapsed, 3),
            **{
                f"{stage_name}_seconds": round(duration, 3)
                for stage_name, duration in result.stage_timings.items()
            },
        },
    )
    return result
