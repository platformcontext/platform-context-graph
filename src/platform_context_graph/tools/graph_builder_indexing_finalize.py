"""Finalization helpers for post-commit indexing stages."""

from __future__ import annotations

import inspect
import time
from pathlib import Path
from typing import Any, Iterable

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


def _stage_progress_accepts_details(callback: Any) -> bool:
    """Return whether one stage callback can consume structured progress details."""

    return _supports_keyword_arguments(
        callback,
        (
            "status",
            "duration_seconds",
            "repo_count",
            "run_id",
        ),
    )


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
) -> dict[str, float]:
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
    stage_timings: dict[str, float] = {}
    callback_accepts_details = _stage_progress_accepts_details(stage_progress_callback)

    def _notify_stage_progress(stage_name: str, **kwargs: Any) -> None:
        """Send stage heartbeats without breaking legacy one-arg callbacks."""

        if not callable(stage_progress_callback):
            return
        if kwargs and callback_accepts_details:
            stage_progress_callback(stage_name, **kwargs)
            return
        if not kwargs or kwargs.get("status") == "started":
            stage_progress_callback(stage_name)

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

    all_stages: tuple[tuple[str, Any], ...] = (
        (
            "inheritance",
            lambda: builder._create_all_inheritance_links(
                committed_repo_data_iter(),
                merged_imports_map,
            ),
        ),
        ("function_calls", _run_function_call_stage),
        (
            "infra_links",
            lambda: builder._create_all_infra_links(committed_repo_data_iter()),
        ),
        (
            "workloads",
            _run_workload_stage,
        ),
        (
            "relationship_resolution",
            lambda: builder._resolve_repository_relationships(
                committed_repo_paths,
                run_id=run_id,
            ),
        ),
    )
    available_stage_names = {stage_name for stage_name, _stage_fn in all_stages}
    if stages is not None:
        unknown_stages = sorted(set(stages) - available_stage_names)
        if unknown_stages:
            raise ValueError(
                "Unsupported finalization stages: " + ", ".join(unknown_stages)
            )
        requested_stage_names = set(stages)
        all_stages = tuple(
            (stage_name, stage_fn)
            for stage_name, stage_fn in all_stages
            if stage_name in requested_stage_names
        )

    for stage_name, stage_fn in all_stages:
        if skip_per_repo_stages and stage_name in _PER_REPO_STAGES:
            emit_log_call(
                info_logger_fn,
                f"Skipping finalization stage {stage_name} (already run per-repo)",
                event_name="index.finalization.stage.skipped",
                extra_keys={
                    "stage": stage_name,
                    "run_id": run_id,
                },
            )
            stage_timings[stage_name] = 0.0
            continue
        _notify_stage_progress(
            stage_name,
            status="started",
            repo_count=len(committed_repo_paths),
            run_id=run_id,
        )
        log_memory_usage(
            info_logger_fn,
            context=f"Before finalization stage {stage_name}",
        )
        stage_start = time.monotonic()
        stage_span = (
            telemetry.start_span(
                "pcg.index.finalize.stage",
                component=component,
                attributes={
                    "pcg.index.run_id": run_id,
                    "pcg.index.stage": stage_name,
                    "pcg.index.parse_strategy": parse_strategy,
                    "pcg.index.parse_workers": parse_workers,
                },
            )
            if telemetry is not None
            else None
        )
        if stage_span is None:
            stage_metrics = stage_fn()
        else:
            with stage_span:
                stage_metrics = stage_fn()
        elapsed = time.monotonic() - stage_start
        stage_timings[stage_name] = elapsed
        _notify_stage_progress(
            stage_name,
            status="completed",
            duration_seconds=round(elapsed, 3),
            repo_count=len(committed_repo_paths),
            run_id=run_id,
            **(
                stage_metrics
                if isinstance(stage_metrics, dict)
                else {}
            ),
        )
        if (
            telemetry is not None
            and component is not None
            and mode is not None
            and source is not None
            and hasattr(telemetry, "record_index_stage_duration")
        ):
            telemetry.record_index_stage_duration(
                component=component,
                mode=mode,
                source=source,
                stage=f"finalize_{stage_name}",
                duration_seconds=elapsed,
                parse_strategy=parse_strategy,
                parse_workers=parse_workers,
            )
        log_memory_usage(
            info_logger_fn,
            context=f"After finalization stage {stage_name}",
        )
        emit_log_call(
            info_logger_fn,
            f"Finalization stage {stage_name} done in {elapsed:.1f}s",
            event_name="index.finalization.stage.completed",
            extra_keys={
                "stage": stage_name,
                "duration_seconds": round(elapsed, 3),
                "run_id": run_id,
                **(
                    stage_metrics
                    if isinstance(stage_metrics, dict)
                    else {}
                ),
            },
        )
    total_elapsed = time.monotonic() - total_start
    timings_summary = ", ".join(
        f"{stage_name}={duration:.1f}s"
        for stage_name, duration in stage_timings.items()
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
                for stage_name, duration in stage_timings.items()
            },
        },
    )
    return stage_timings
