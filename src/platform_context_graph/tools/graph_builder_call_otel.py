"""OTEL metrics helpers for CALLS resolution passes."""

from __future__ import annotations

from typing import Any

_OTEL_STAGE_KEYS = (
    ("contextual_exact", "contextual_exact_duration_seconds"),
    ("contextual_repo_scoped", "contextual_repo_scoped_duration_seconds"),
    ("contextual_fallback", "contextual_fallback_duration_seconds"),
    ("file_level_exact", "file_level_exact_duration_seconds"),
    ("file_level_repo_scoped", "file_level_repo_scoped_duration_seconds"),
    ("file_level_fallback", "file_level_fallback_duration_seconds"),
    ("total", "total_duration_seconds"),
)


def emit_call_resolution_otel_metrics(
    metrics: dict[str, float | int],
) -> None:
    """Emit OTEL stage-duration metrics for CALLS resolution passes.

    Each resolution sub-stage (contextual exact, contextual fallback,
    file-level exact, file-level fallback, total) is recorded via the
    observability subsystem when available.

    Args:
        metrics: Combined call-resolution metrics dict produced by
            ``combine_call_relationship_metrics``.
    """
    try:
        from platform_context_graph.observability import get_observability

        obs = get_observability()
        if not hasattr(obs, "record_index_stage_duration"):
            return
        for suffix, key in _OTEL_STAGE_KEYS:
            obs.record_index_stage_duration(
                component="indexer",
                mode="batch",
                source="finalization",
                stage=f"function_calls_{suffix}",
                duration_seconds=metrics.get(key, 0),
                parse_strategy="",
                parse_workers=0,
            )
    except Exception:
        pass  # Don't fail indexing if metrics emission fails
