"""Per-repository telemetry accumulator for indexing observability."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_BYTES_PER_MIB = 1024 * 1024

# Mapping from lifecycle phase to the RepoTelemetry field names that get set.
_PHASE_RSS_FIELD_MAP: dict[str, str] = {
    "parse_start": "rss_mib_parse_start",
    "parse_end": "rss_mib_parse_end",
    "commit_start": "rss_mib_commit_start",
    "commit_end": "rss_mib_commit_end",
}

_PHASE_CGROUP_FIELD_MAP: dict[str, str] = {
    "parse_start": "cgroup_memory_mib_parse_start",
    "commit_start": "cgroup_memory_mib_commit_start",
    "commit_end": "cgroup_memory_mib_commit_end",
}


@dataclass
class RepoTelemetry:
    """Per-repository telemetry collected across the indexing lifecycle.

    Created once per repository at parse start, updated incrementally at
    each lifecycle point (parse, queue wait, commit, finalization), and
    consumed by the run summary builder after all repositories complete.

    Attributes:
        repo_path: Resolved absolute path to the repository root.
        repo_name: Short repository name derived from the path.
        parse_queue_wait_seconds: Time spent waiting for a parse slot.
        parse_duration_seconds: Wall-clock parse time.
        commit_queue_wait_seconds: Time spent waiting for a commit slot.
        commit_duration_seconds: Wall-clock commit time.
        graph_write_duration_seconds: Cumulative Neo4j graph write time.
        content_write_duration_seconds: Cumulative Postgres content write time.
        checkpoint_duration_seconds: Time persisting checkpoint state.
        total_repository_duration_seconds: End-to-end repo processing time.
        discovered_file_count: Files discovered before filtering.
        parsed_file_count: Files successfully parsed.
        graph_batch_count: Number of graph write batches committed.
        content_batch_count: Number of content write batches committed.
        max_graph_batch_rows: Largest single graph write batch row count.
        max_content_batch_rows: Largest single content write batch row count.
        entity_totals: Per-label entity counts from graph writes.
        rss_mib_parse_start: Process RSS at parse entry in MiB.
        rss_mib_parse_end: Process RSS at parse exit in MiB.
        rss_mib_commit_start: Process RSS at commit entry in MiB.
        rss_mib_commit_end: Process RSS at commit exit in MiB.
        rss_mib_commit_peak_estimate: Max RSS observed during commit in MiB.
        cgroup_memory_mib_parse_start: Cgroup memory at parse entry in MiB.
        cgroup_memory_mib_commit_start: Cgroup memory at commit entry in MiB.
        cgroup_memory_mib_commit_end: Cgroup memory at commit exit in MiB.
        fallback_resolution_attempts: Name-only fallback call resolution count.
        ambiguous_resolution_count: Multi-target ambiguous resolution count.
        hot_graph_lookup_count: Expensive graph lookup count.
        repo_class: Assigned repository class for observability tagging.
        status: Current processing status.
        error: Error message when the repo failed.
        anomalies: Detected anomaly records for this repository.
    """

    repo_path: str
    repo_name: str

    # Timing
    parse_queue_wait_seconds: float | None = None
    parse_duration_seconds: float | None = None
    commit_queue_wait_seconds: float | None = None
    commit_duration_seconds: float | None = None
    graph_write_duration_seconds: float | None = None
    content_write_duration_seconds: float | None = None
    checkpoint_duration_seconds: float | None = None
    total_repository_duration_seconds: float | None = None

    # Shape
    discovered_file_count: int = 0
    parsed_file_count: int = 0
    graph_batch_count: int = 0
    content_batch_count: int = 0
    max_graph_batch_rows: int = 0
    max_content_batch_rows: int = 0
    entity_totals: dict[str, int] = field(default_factory=dict)

    # Memory samples (MiB)
    rss_mib_parse_start: float | None = None
    rss_mib_parse_end: float | None = None
    rss_mib_commit_start: float | None = None
    rss_mib_commit_end: float | None = None
    rss_mib_commit_peak_estimate: float | None = None
    cgroup_memory_mib_parse_start: float | None = None
    cgroup_memory_mib_commit_start: float | None = None
    cgroup_memory_mib_commit_end: float | None = None

    # Resolution counters
    fallback_resolution_attempts: int = 0
    ambiguous_resolution_count: int = 0
    hot_graph_lookup_count: int = 0

    # Classification
    repo_class: str | None = None

    # Status
    status: str = "pending"
    error: str | None = None

    # Anomalies
    anomalies: list[dict[str, Any]] = field(default_factory=list)


def create_repo_telemetry(repo_path: Path) -> RepoTelemetry:
    """Create a telemetry accumulator for one repository.

    Args:
        repo_path: Path to the repository root directory.

    Returns:
        A new ``RepoTelemetry`` instance with repo_name derived from the path.
    """
    resolved = repo_path.resolve()
    return RepoTelemetry(
        repo_path=str(resolved),
        repo_name=resolved.name,
    )


def record_memory_sample(
    telemetry: RepoTelemetry,
    phase: str,
    sample: Any,
) -> None:
    """Record a memory usage sample at a specific lifecycle phase.

    Supported phases: ``parse_start``, ``parse_end``, ``commit_start``,
    ``commit_end``, ``commit_batch``.

    The ``commit_batch`` phase updates the peak RSS estimate by tracking the
    maximum RSS observed across all commit batch samples.

    Args:
        telemetry: The per-repo telemetry accumulator to update.
        phase: The lifecycle phase identifier.
        sample: A ``MemoryUsageSample``-compatible object with ``rss_bytes``
            and ``cgroup_memory_bytes`` attributes.
    """
    rss_bytes = getattr(sample, "rss_bytes", None)
    cgroup_bytes = getattr(sample, "cgroup_memory_bytes", None)

    if phase == "commit_batch":
        if rss_bytes is not None:
            rss_mib = rss_bytes / _BYTES_PER_MIB
            current_peak = telemetry.rss_mib_commit_peak_estimate
            if current_peak is None or rss_mib > current_peak:
                telemetry.rss_mib_commit_peak_estimate = rss_mib
        return

    rss_field = _PHASE_RSS_FIELD_MAP.get(phase)
    if rss_field is not None and rss_bytes is not None:
        setattr(telemetry, rss_field, rss_bytes / _BYTES_PER_MIB)

    cgroup_field = _PHASE_CGROUP_FIELD_MAP.get(phase)
    if cgroup_field is not None and cgroup_bytes is not None:
        setattr(telemetry, cgroup_field, cgroup_bytes / _BYTES_PER_MIB)


__all__ = [
    "RepoTelemetry",
    "create_repo_telemetry",
    "record_memory_sample",
]
