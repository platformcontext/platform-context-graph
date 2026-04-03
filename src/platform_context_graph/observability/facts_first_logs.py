"""Structured log helpers for the facts-first pipeline."""

from __future__ import annotations

from typing import Any

from platform_context_graph.utils.debug_log import error_logger
from platform_context_graph.utils.debug_log import info_logger
from platform_context_graph.utils.debug_log import warning_logger


def log_snapshot_emitted(**extra_keys: Any) -> None:
    """Emit one snapshot-emitted facts-first log event."""

    info_logger(
        "Emitted facts for one repository snapshot",
        event_name="facts.snapshot.emitted",
        extra_keys=extra_keys,
    )


def log_inline_projection(outcome: str, **extra_keys: Any) -> None:
    """Emit one inline-projection log event."""

    event_name = f"facts.inline_projection.{outcome}"
    message = {
        "leased": "Leased facts-first work item for inline projection",
        "lease_missed": "Facts-first inline projection lease missed",
        "failed": "Facts-first inline projection failed",
        "completed": "Facts-first inline projection completed",
    }.get(outcome, "Facts-first inline projection updated")
    logger_fn = warning_logger if outcome in {"lease_missed", "failed"} else info_logger
    logger_fn(message, event_name=event_name, extra_keys=extra_keys)


def log_resolution_work_item(outcome: str, **extra_keys: Any) -> None:
    """Emit one Resolution Engine work-item lifecycle log event."""

    event_name = f"resolution.work_item.{outcome}"
    message = {
        "completed": "Resolution Engine completed one work item",
        "failed": "Resolution Engine returned one work item to retry",
        "dead_lettered": "Resolution Engine dead-lettered one work item",
        "projected": "Resolution Engine projected one work item",
    }.get(outcome, "Resolution Engine updated one work item")
    logger_fn = error_logger if outcome == "dead_lettered" else warning_logger
    if outcome in {"completed", "projected"}:
        logger_fn = info_logger
    logger_fn(message, event_name=event_name, extra_keys=extra_keys)


def log_resolution_stage_failure(**extra_keys: Any) -> None:
    """Emit one Resolution Engine stage-failure log event."""

    error_logger(
        "Resolution Engine stage failed",
        event_name="resolution.stage.failed",
        extra_keys=extra_keys,
    )
