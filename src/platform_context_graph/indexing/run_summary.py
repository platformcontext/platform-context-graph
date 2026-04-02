"""Machine-readable run summary artifact for indexing observability."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from .repo_telemetry import RepoTelemetry


@dataclass(frozen=True)
class RunSummaryConfig:
    """Snapshot of runtime configuration captured for the summary artifact.

    Attributes:
        parse_workers: Number of concurrent parse workers.
        commit_workers: Number of concurrent commit consumers.
        queue_depth: Maximum queued parsed repositories.
        file_batch_size: Files per commit batch.
        max_calls_per_file: Call resolution cap per file.
        call_resolution_scope: Resolution scope (repo or global).
        index_variables: Whether variable nodes are indexed.
        parse_multiprocess: Whether multiprocess parsing is enabled.
    """

    parse_workers: int
    commit_workers: int
    queue_depth: int
    file_batch_size: int
    max_calls_per_file: int
    call_resolution_scope: str
    index_variables: bool
    parse_multiprocess: bool

    @classmethod
    def from_env(cls) -> RunSummaryConfig:
        """Build a config snapshot from current environment variables.

        Returns:
            A frozen config snapshot reflecting the active settings.
        """

        def _int_env(key: str, default: int) -> int:
            """Read an int from env, falling back to *default*."""
            raw = os.getenv(key)
            if raw is None or not raw.strip():
                return default
            try:
                return int(raw)
            except ValueError:
                return default

        def _bool_env(key: str, default: bool) -> bool:
            """Read a bool from env, falling back to *default*."""
            raw = os.getenv(key)
            if raw is None:
                return default
            return raw.strip().lower() == "true"

        return cls(
            parse_workers=_int_env("PCG_PARSE_WORKERS", 4),
            commit_workers=_int_env("PCG_COMMIT_WORKERS", 1),
            queue_depth=_int_env("PCG_INDEX_QUEUE_DEPTH", 8),
            file_batch_size=_int_env("PCG_FILE_BATCH_SIZE", 50),
            max_calls_per_file=_int_env("PCG_MAX_CALLS_PER_FILE", 50),
            call_resolution_scope=os.getenv("PCG_CALL_RESOLUTION_SCOPE", "repo"),
            index_variables=_bool_env("INDEX_VARIABLES", False),
            parse_multiprocess=_bool_env("PCG_REPO_FILE_PARSE_MULTIPROCESS", False),
        )


_SCHEMA_VERSION = "1.0"

# Timing fields extracted from RepoTelemetry for distribution computation.
_TIMING_FIELDS = (
    "parse_duration_seconds",
    "commit_duration_seconds",
    "parse_queue_wait_seconds",
    "commit_queue_wait_seconds",
    "graph_write_duration_seconds",
    "content_write_duration_seconds",
)

# Resolution cost stages for provisional rollup grouping.
_RESOLUTION_STAGES = ("inheritance", "function_calls")
_EVIDENCE_STAGES = ("infra_links", "workloads", "relationship_resolution")

# Anomaly type names for the by_type summary section.
_ANOMALY_TYPES = (
    "parse_queue_wait_high",
    "commit_queue_wait_high",
    "commit_memory_high",
    "graph_batch_rows_high",
    "content_batch_rows_high",
    "duration_high",
    "fallback_resolution_high",
    "graph_lookup_high",
)


def _percentile(sorted_values: list[float], p: float) -> float:
    """Return the p-th percentile from a pre-sorted list.

    Args:
        sorted_values: Ascending-sorted numeric values.
        p: Percentile as a fraction (e.g. 0.95 for p95).

    Returns:
        The value at the given percentile, or 0.0 for empty lists.
    """
    if not sorted_values:
        return 0.0
    idx = int(len(sorted_values) * p)
    idx = min(idx, len(sorted_values) - 1)
    return sorted_values[idx]


def compute_timing_distributions(
    repo_telemetries: Iterable[RepoTelemetry],
) -> dict[str, dict[str, float]]:
    """Compute p50/p95/p99/max for each timing field across repositories.

    Args:
        repo_telemetries: Iterable of per-repository telemetry accumulators.

    Returns:
        A dict keyed by timing field name, each containing p50, p95, p99, max.
    """
    telemetry_list = list(repo_telemetries)
    result: dict[str, dict[str, float]] = {}

    for field_name in _TIMING_FIELDS:
        values = sorted(
            v
            for tel in telemetry_list
            if (v := getattr(tel, field_name, None)) is not None
        )
        result[field_name] = {
            "p50": _percentile(values, 0.50),
            "p95": _percentile(values, 0.95),
            "p99": _percentile(values, 0.99),
            "max": values[-1] if values else 0.0,
        }

    return result


def compute_outliers(
    repo_telemetries: Iterable[RepoTelemetry],
    *,
    top_n: int = 5,
) -> dict[str, list[dict[str, Any]]]:
    """Extract top-N outliers for each performance category.

    Args:
        repo_telemetries: Iterable of per-repository telemetry accumulators.
        top_n: Number of outliers to return per category.

    Returns:
        A dict with outlier categories as keys and sorted outlier lists.
    """
    telemetry_list = list(repo_telemetries)

    def _top(key_fn: Any, extra_fn: Any = None) -> list[dict[str, Any]]:
        """Return top-N repos sorted descending by key_fn."""
        candidates = [
            (tel, key_fn(tel)) for tel in telemetry_list if key_fn(tel) is not None
        ]
        candidates.sort(key=lambda pair: pair[1], reverse=True)
        results = []
        for tel, value in candidates[:top_n]:
            entry: dict[str, Any] = {
                "repo_name": tel.repo_name,
                "value": value,
            }
            if extra_fn is not None:
                entry.update(extra_fn(tel))
            results.append(entry)
        return results

    return {
        "top_parse_duration": _top(
            lambda t: t.parse_duration_seconds,
            lambda t: {"file_count": t.parsed_file_count},
        ),
        "top_commit_duration": _top(lambda t: t.commit_duration_seconds),
        "top_parse_queue_wait": _top(lambda t: t.parse_queue_wait_seconds),
        "top_commit_queue_wait": _top(
            lambda t: t.commit_queue_wait_seconds,
        ),
        "top_memory": _top(
            lambda t: t.rss_mib_commit_end,
            lambda t: {"rss_mib_commit_end": t.rss_mib_commit_end},
        ),
    }


def _build_finalization_section(
    stage_durations: dict[str, float],
) -> dict[str, Any]:
    """Build the finalization section of the run summary.

    Args:
        stage_durations: Per-stage timing from IndexRunState.

    Returns:
        Finalization summary including provisional rollups.
    """
    resolution_total = sum(stage_durations.get(s, 0.0) for s in _RESOLUTION_STAGES)
    evidence_total = sum(stage_durations.get(s, 0.0) for s in _EVIDENCE_STAGES)
    return {
        "stage_durations": dict(stage_durations),
        "per_repo_stages": list(_RESOLUTION_STAGES),
        "global_stages": ["infra_links"],
        "hybrid_stages": ["workloads", "relationship_resolution"],
        "provisional_rollups": {
            "resolution_duration_seconds": resolution_total,
            "evidence_promotion_duration_seconds": evidence_total,
        },
        "provisional_rollups_note": (
            "Aggregation views, not authoritative cost boundaries. "
            "See Two Levels of Cost Truth."
        ),
    }


def _build_anomaly_section(
    telemetries: list[RepoTelemetry],
) -> dict[str, Any]:
    """Aggregate anomaly counts across all repositories.

    Args:
        telemetries: List of per-repo telemetry accumulators.

    Returns:
        Anomaly summary with total count and per-type breakdown.
    """
    by_type: dict[str, int] = {t: 0 for t in _ANOMALY_TYPES}
    total = 0
    for tel in telemetries:
        for anomaly in tel.anomalies:
            atype = anomaly.get("type", "unknown")
            if atype in by_type:
                by_type[atype] += 1
            total += 1
    return {"total_count": total, "by_type": by_type}


def _build_per_repository(
    telemetries: list[RepoTelemetry],
) -> list[dict[str, Any]]:
    """Build the per-repository section of the run summary.

    Args:
        telemetries: List of per-repo telemetry accumulators.

    Returns:
        Sorted list of per-repo summary dicts.
    """
    result = []
    for tel in sorted(telemetries, key=lambda t: t.repo_name):
        result.append(
            {
                "repo_name": tel.repo_name,
                "status": tel.status,
                "repo_class": tel.repo_class,
                "discovered_file_count": tel.discovered_file_count,
                "parsed_file_count": tel.parsed_file_count,
                "parse_duration_seconds": tel.parse_duration_seconds,
                "parse_queue_wait_seconds": tel.parse_queue_wait_seconds,
                "commit_queue_wait_seconds": tel.commit_queue_wait_seconds,
                "commit_duration_seconds": tel.commit_duration_seconds,
                "graph_write_duration_seconds": tel.graph_write_duration_seconds,
                "content_write_duration_seconds": (tel.content_write_duration_seconds),
                "rss_mib_commit_end": tel.rss_mib_commit_end,
                "per_repo_finalization": {
                    "fallback_resolution_attempts": (tel.fallback_resolution_attempts),
                    "ambiguous_resolution_count": (tel.ambiguous_resolution_count),
                },
                "error": tel.error,
            }
        )
    return result


def build_run_summary(
    *,
    run_state: Any,
    repo_telemetry_map: dict[str, RepoTelemetry],
    config: RunSummaryConfig,
    started_at: str,
    finished_at: str,
) -> dict[str, Any]:
    """Build the complete run summary artifact.

    Combines checkpoint state from ``IndexRunState`` with per-repository
    telemetry to produce a machine-readable JSON-serializable summary.

    Args:
        run_state: The ``IndexRunState`` checkpoint for this run.
        repo_telemetry_map: Per-repo telemetry keyed by repo_path.
        config: Frozen config snapshot for this run.
        started_at: ISO 8601 run start timestamp.
        finished_at: ISO 8601 run finish timestamp.

    Returns:
        A dict matching the run summary artifact schema (version 1.0).
    """
    telemetries = list(repo_telemetry_map.values())
    total_parsed = sum(t.parsed_file_count for t in telemetries)
    completed = sum(1 for t in telemetries if t.status == "completed")
    failed = sum(1 for t in telemetries if t.status == "failed")
    # Use run_state.repositories for discovered count when telemetry
    # may be incomplete (e.g. resumed runs skip parse/commit).
    discovered = (
        len(run_state.repositories)
        if hasattr(run_state, "repositories")
        else len(telemetries)
    )
    stage_durations = getattr(run_state, "finalization_stage_durations", {}) or {}

    # Compute peak memory across all repos
    rss_peaks = [t.rss_mib_commit_end for t in telemetries if t.rss_mib_commit_end]
    cgroup_peaks = [
        t.cgroup_memory_mib_commit_end
        for t in telemetries
        if t.cgroup_memory_mib_commit_end
    ]

    return {
        "schema_version": _SCHEMA_VERSION,
        "run_id": run_state.run_id,
        "root_path": run_state.root_path,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": run_state.status,
        "finalization_status": run_state.finalization_status,
        "config": asdict(config),
        "totals": {
            "repositories_discovered": discovered,
            "repositories_completed": completed,
            "repositories_failed": failed,
            "total_files_parsed": total_parsed,
        },
        "timing_distributions": compute_timing_distributions(telemetries),
        "memory": {
            "peak_rss_mib": max(rss_peaks) if rss_peaks else 0.0,
            "peak_cgroup_mib": max(cgroup_peaks) if cgroup_peaks else 0.0,
        },
        "finalization": _build_finalization_section(stage_durations),
        "outliers": compute_outliers(telemetries),
        "anomalies": _build_anomaly_section(telemetries),
        "per_repository": _build_per_repository(telemetries),
    }


def summary_output_dir(run_id: str) -> Path:
    """Determine the output directory for the run summary file.

    Checks ``PCG_INDEX_SUMMARY_DIR`` first, then falls back to the
    default location under the application home directory.

    Args:
        run_id: The unique run identifier.

    Returns:
        The resolved output directory path.
    """
    env_dir = os.getenv("PCG_INDEX_SUMMARY_DIR")
    if env_dir and env_dir.strip():
        return Path(env_dir.strip())
    from ..paths import get_app_home

    return get_app_home() / "index-runs" / run_id


def write_run_summary(
    summary: dict[str, Any],
    *,
    run_id: str,
    output_dir: Path | None = None,
) -> Path:
    """Write the summary artifact to disk atomically.

    Args:
        summary: The complete run summary dict.
        run_id: The unique run identifier for the filename.
        output_dir: Override directory (default uses ``summary_output_dir``).

    Returns:
        The path to the written summary file.
    """
    target_dir = output_dir or summary_output_dir(run_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"pcg-index-summary-{run_id}.json"

    # Atomic write: write to temp file then rename
    fd, tmp_path_str = tempfile.mkstemp(dir=str(target_dir), suffix=".json.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
            f.write("\n")
        Path(tmp_path_str).rename(target_path)
    except Exception:
        Path(tmp_path_str).unlink(missing_ok=True)
        raise

    return target_path


__all__ = [
    "RunSummaryConfig",
    "build_run_summary",
    "compute_outliers",
    "compute_timing_distributions",
    "summary_output_dir",
    "write_run_summary",
]
