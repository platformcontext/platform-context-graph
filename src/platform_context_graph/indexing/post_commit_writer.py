"""Explicit post-commit writer contract for legacy finalization compatibility."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
import time
from typing import Any, Callable, Mapping, Sequence

from platform_context_graph.utils.debug_log import emit_log_call

StageRunner = Callable[[], Mapping[str, int | float] | None]


@dataclass(frozen=True)
class PostCommitStage:
    """One named post-commit stage."""

    name: str
    runner: StageRunner


@dataclass(frozen=True)
class PostCommitWriteResult:
    """Structured outcome for one post-commit write execution."""

    stage_timings: dict[str, float]
    stage_details: dict[str, dict[str, int | float]]


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


def execute_post_commit_stages(
    *,
    stages: Sequence[PostCommitStage],
    info_logger_fn: Any,
    stage_progress_callback: Any | None = None,
    telemetry: Any | None = None,
    component: str | None = None,
    mode: str | None = None,
    source: str | None = None,
    parse_strategy: str = "threaded",
    parse_workers: int = 1,
    repo_count: int = 0,
    run_id: str | None = None,
    skipped_stage_names: set[str] | None = None,
    monotonic_fn: Callable[[], float] | None = None,
) -> PostCommitWriteResult:
    """Execute named post-commit stages with shared telemetry and progress."""

    skipped_stage_names = skipped_stage_names or set()
    if monotonic_fn is None:
        monotonic_fn = time.monotonic
    stage_timings: dict[str, float] = {}
    stage_details: dict[str, dict[str, int | float]] = {}

    def _notify_stage_progress(stage_name: str, **kwargs: Any) -> None:
        """Forward one stage progress event to the optional callback."""

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

    for stage in stages:
        stage_name = stage.name
        if stage_name in skipped_stage_names:
            emit_log_call(
                info_logger_fn,
                f"Skipping finalization stage {stage_name} (already run per-repo)",
                event_name="index.finalization.stage.skipped",
                extra_keys={"stage": stage_name, "run_id": run_id},
            )
            stage_timings[stage_name] = 0.0
            continue

        _notify_stage_progress(
            stage_name,
            status="started",
            repo_count=repo_count,
            run_id=run_id,
        )
        started = monotonic_fn()
        span = (
            telemetry.start_span(
                "pcg.index.finalize.stage",
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
        if span is None:
            metrics = stage.runner()
        else:
            with span:
                metrics = stage.runner()
        elapsed = max(monotonic_fn() - started, 0.0)
        stage_timings[stage_name] = elapsed
        details = dict(metrics or {}) if isinstance(metrics, Mapping) else {}
        if details:
            stage_details[stage_name] = details
        _notify_stage_progress(
            stage_name,
            status="completed",
            duration_seconds=round(elapsed, 3),
            repo_count=repo_count,
            run_id=run_id,
            **details,
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
        emit_log_call(
            info_logger_fn,
            f"Finalization stage {stage_name} done in {elapsed:.1f}s",
            event_name="index.finalization.stage.completed",
            extra_keys={
                "stage": stage_name,
                "duration_seconds": round(elapsed, 3),
                "run_id": run_id,
                **details,
            },
        )

    return PostCommitWriteResult(
        stage_timings=stage_timings,
        stage_details=stage_details,
    )
