"""Threshold-based anomaly detection for indexing observability."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .repo_telemetry import RepoTelemetry

# Multipliers applied to base thresholds for class-aware adjustment.
_CLASS_MULTIPLIERS: dict[str, float] = {
    "small": 0.5,
    "medium": 1.0,
    "large": 1.5,
    "xlarge": 2.0,
}


@dataclass(frozen=True)
class AnomalyThresholds:
    """Configurable warning thresholds for indexing anomaly detection.

    Bootstrap defaults are intentionally conservative to avoid false-positive
    noise before baseline calibration. They should be tightened after Phase 2
    produces real distributions from the run summary artifact.

    Attributes:
        parse_queue_wait_high_seconds: Parse slot wait warning threshold.
        commit_queue_wait_high_seconds: Commit slot wait warning threshold.
        commit_duration_high_seconds: Commit duration warning threshold.
        graph_batch_rows_high: Graph batch row count warning threshold.
        content_batch_rows_high: Content batch row count warning threshold.
        repo_rss_high_mib: Process RSS warning threshold in MiB.
        fallback_resolution_high_count: Fallback resolution count threshold.
        graph_lookup_high_count: Expensive graph lookup count threshold.
    """

    parse_queue_wait_high_seconds: float = 120.0
    commit_queue_wait_high_seconds: float = 120.0
    commit_duration_high_seconds: float = 300.0
    graph_batch_rows_high: int = 5000
    content_batch_rows_high: int = 5000
    repo_rss_high_mib: float = 2048.0
    fallback_resolution_high_count: int = 500
    graph_lookup_high_count: int = 1000


def load_anomaly_thresholds() -> AnomalyThresholds:
    """Load thresholds from environment variables with bootstrap defaults.

    Environment variable names follow the pattern
    ``PCG_ANOMALY_<FIELD_NAME_UPPER>``. Unset or invalid values fall back
    to the compiled defaults.

    Returns:
        An ``AnomalyThresholds`` instance with any env overrides applied.
    """

    def _float_env(key: str, default: float) -> float:
        """Read a float from env, falling back to *default*."""
        raw = os.getenv(key)
        if raw is None or not raw.strip():
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def _int_env(key: str, default: int) -> int:
        """Read an int from env, falling back to *default*."""
        raw = os.getenv(key)
        if raw is None or not raw.strip():
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    return AnomalyThresholds(
        parse_queue_wait_high_seconds=_float_env(
            "PCG_ANOMALY_PARSE_QUEUE_WAIT_HIGH_SECONDS", 120.0
        ),
        commit_queue_wait_high_seconds=_float_env(
            "PCG_ANOMALY_COMMIT_QUEUE_WAIT_HIGH_SECONDS", 120.0
        ),
        commit_duration_high_seconds=_float_env(
            "PCG_ANOMALY_COMMIT_DURATION_HIGH_SECONDS", 300.0
        ),
        graph_batch_rows_high=_int_env("PCG_ANOMALY_GRAPH_BATCH_ROWS_HIGH", 5000),
        content_batch_rows_high=_int_env("PCG_ANOMALY_CONTENT_BATCH_ROWS_HIGH", 5000),
        repo_rss_high_mib=_float_env("PCG_ANOMALY_REPO_RSS_HIGH_MIB", 2048.0),
        fallback_resolution_high_count=_int_env(
            "PCG_ANOMALY_FALLBACK_RESOLUTION_HIGH_COUNT", 500
        ),
        graph_lookup_high_count=_int_env("PCG_ANOMALY_GRAPH_LOOKUP_HIGH_COUNT", 1000),
    )


def check_anomalies(
    telemetry: RepoTelemetry,
    thresholds: AnomalyThresholds,
) -> list[dict[str, Any]]:
    """Check per-repository telemetry against warning thresholds.

    Each anomaly dict contains the anomaly type, actual value, threshold,
    and repository identity fields.

    Args:
        telemetry: The per-repo telemetry accumulator to check.
        thresholds: The active threshold configuration.

    Returns:
        A list of anomaly dicts, empty when no thresholds are exceeded.
    """
    anomalies: list[dict[str, Any]] = []

    checks: list[tuple[str, Any, Any]] = [
        (
            "parse_queue_wait_high",
            telemetry.parse_queue_wait_seconds,
            thresholds.parse_queue_wait_high_seconds,
        ),
        (
            "commit_queue_wait_high",
            telemetry.commit_queue_wait_seconds,
            thresholds.commit_queue_wait_high_seconds,
        ),
        (
            "duration_high",
            telemetry.commit_duration_seconds,
            thresholds.commit_duration_high_seconds,
        ),
        (
            "commit_memory_high",
            telemetry.rss_mib_commit_end,
            thresholds.repo_rss_high_mib,
        ),
        (
            "graph_batch_rows_high",
            telemetry.max_graph_batch_rows or None,
            thresholds.graph_batch_rows_high,
        ),
        (
            "content_batch_rows_high",
            telemetry.max_content_batch_rows or None,
            thresholds.content_batch_rows_high,
        ),
        (
            "fallback_resolution_high",
            telemetry.fallback_resolution_attempts or None,
            thresholds.fallback_resolution_high_count,
        ),
        (
            "graph_lookup_high",
            telemetry.hot_graph_lookup_count or None,
            thresholds.graph_lookup_high_count,
        ),
    ]

    for anomaly_type, actual, threshold in checks:
        if actual is not None and actual > threshold:
            anomalies.append(
                {
                    "type": anomaly_type,
                    "actual": actual,
                    "threshold": threshold,
                    "repo_name": telemetry.repo_name,
                    "repo_path": telemetry.repo_path,
                }
            )

    return anomalies


def class_adjusted_thresholds(
    base: AnomalyThresholds,
    repo_class: str,
) -> AnomalyThresholds:
    """Return thresholds adjusted for the given repository class.

    Larger repo classes get proportionally looser thresholds to reduce
    false-positive anomaly noise. The ``medium`` class is the baseline
    (1.0x multiplier).

    Args:
        base: The base threshold configuration.
        repo_class: The assigned repository class.

    Returns:
        An adjusted ``AnomalyThresholds`` instance.
    """
    multiplier = _CLASS_MULTIPLIERS.get(repo_class, 1.0)
    if multiplier == 1.0:
        return base

    return AnomalyThresholds(
        parse_queue_wait_high_seconds=(base.parse_queue_wait_high_seconds * multiplier),
        commit_queue_wait_high_seconds=(
            base.commit_queue_wait_high_seconds * multiplier
        ),
        commit_duration_high_seconds=(base.commit_duration_high_seconds * multiplier),
        graph_batch_rows_high=int(base.graph_batch_rows_high * multiplier),
        content_batch_rows_high=int(base.content_batch_rows_high * multiplier),
        repo_rss_high_mib=base.repo_rss_high_mib * multiplier,
        fallback_resolution_high_count=int(
            base.fallback_resolution_high_count * multiplier
        ),
        graph_lookup_high_count=int(base.graph_lookup_high_count * multiplier),
    )


def emit_anomaly_events(
    anomalies: list[dict[str, Any]],
    *,
    warning_logger_fn: Any,
    run_id: str,
) -> None:
    """Emit structured warning-level log events for detected anomalies.

    Args:
        anomalies: List of anomaly dicts from ``check_anomalies``.
        warning_logger_fn: Callable accepting a message string and keyword
            arguments for structured log fields.
        run_id: The current run identifier for correlation.
    """
    for anomaly in anomalies:
        anomaly_type = anomaly["type"]
        repo_name = anomaly.get("repo_name", "unknown")
        repo_path = anomaly.get("repo_path", "")
        actual = anomaly.get("actual")
        threshold = anomaly.get("threshold")
        warning_logger_fn(
            f"Anomaly detected: {anomaly_type} for {repo_name} "
            f"(actual={actual}, threshold={threshold}, "
            f"run_id={run_id}, repo_path={repo_path})"
        )


__all__ = [
    "AnomalyThresholds",
    "check_anomalies",
    "class_adjusted_thresholds",
    "emit_anomaly_events",
    "load_anomaly_thresholds",
]
