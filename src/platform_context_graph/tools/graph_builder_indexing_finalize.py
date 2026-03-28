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
) -> dict[str, float]:
    """Create cross-file and cross-repo relationships after repo commits finish."""

    emit_log_call(
        info_logger_fn,
        "Creating inheritance links and function calls for "
        f"{len(committed_repo_paths)} committed repositories...",
        event_name="index.finalization.started",
        extra_keys={"repository_count": len(committed_repo_paths), "run_id": run_id},
    )
    total_start = time.monotonic()
    committed_repo_data_iter = lambda: _iter_repository_file_data(
        committed_repo_paths,
        iter_snapshot_file_data_fn,
    )
    stage_timings: dict[str, float] = {}

    def _notify_stage_progress(stage_name: str, **kwargs: Any) -> None:
        """Send stage heartbeats without breaking legacy one-arg callbacks."""

        if not callable(stage_progress_callback):
            return
        if kwargs and _supports_keyword_arguments(
            stage_progress_callback,
            tuple(kwargs.keys()),
        ):
            stage_progress_callback(stage_name, **kwargs)
            return
        stage_progress_callback(stage_name)

    def _run_function_call_stage() -> None:
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

    for stage_name, stage_fn in (
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
        ("workloads", builder._materialize_workloads),
        (
            "relationship_resolution",
            lambda: builder._resolve_repository_relationships(
                committed_repo_paths,
                run_id=run_id,
            ),
        ),
    ):
        _notify_stage_progress(stage_name)
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
            stage_fn()
        else:
            with stage_span:
                stage_fn()
        elapsed = time.monotonic() - stage_start
        stage_timings[stage_name] = elapsed
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
            },
        )
    total_elapsed = time.monotonic() - total_start
    emit_log_call(
        info_logger_fn,
        "Finalization timings: "
        f"inheritance={stage_timings['inheritance']:.1f}s, "
        f"function_calls={stage_timings['function_calls']:.1f}s, "
        f"infra_links={stage_timings['infra_links']:.1f}s, "
        f"workloads={stage_timings['workloads']:.1f}s, "
        f"relationship_resolution={stage_timings['relationship_resolution']:.1f}s, "
        f"total={total_elapsed:.1f}s",
        event_name="index.finalization.completed",
        extra_keys={
            "run_id": run_id,
            "inheritance_seconds": round(stage_timings["inheritance"], 3),
            "function_calls_seconds": round(stage_timings["function_calls"], 3),
            "infra_links_seconds": round(stage_timings["infra_links"], 3),
            "workloads_seconds": round(stage_timings["workloads"], 3),
            "relationship_resolution_seconds": round(
                stage_timings["relationship_resolution"], 3
            ),
            "total_seconds": round(total_elapsed, 3),
        },
    )
    return stage_timings
