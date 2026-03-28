"""Best-effort process and cgroup memory diagnostics for indexing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROC_STATUS_PATH = Path("/proc/self/status")
CGROUP_MEMORY_CURRENT_PATH = Path("/sys/fs/cgroup/memory.current")
CGROUP_MEMORY_MAX_PATH = Path("/sys/fs/cgroup/memory.max")
_BYTES_PER_MIB = 1024 * 1024


@dataclass(frozen=True)
class MemoryUsageSample:
    """One best-effort memory usage snapshot."""

    rss_bytes: int | None
    cgroup_memory_bytes: int | None
    cgroup_memory_limit_bytes: int | None = None


def read_memory_usage_sample() -> MemoryUsageSample:
    """Return current process RSS and cgroup memory usage when available."""

    return MemoryUsageSample(
        rss_bytes=_read_process_rss_bytes(),
        cgroup_memory_bytes=_read_cgroup_memory_bytes(),
        cgroup_memory_limit_bytes=_read_cgroup_memory_limit_bytes(),
    )


def log_memory_usage(info_logger_fn: Any, *, context: str) -> None:
    """Emit one concise memory usage line when diagnostics are available."""

    sample = read_memory_usage_sample()
    parts: list[str] = []
    if sample.rss_bytes is not None:
        parts.append(f"rss={_format_mebibytes(sample.rss_bytes)}")
    if sample.cgroup_memory_bytes is not None:
        parts.append(f"cgroup_memory={_format_mebibytes(sample.cgroup_memory_bytes)}")
    if sample.cgroup_memory_limit_bytes is not None:
        parts.append(
            f"cgroup_limit={_format_mebibytes(sample.cgroup_memory_limit_bytes)}"
        )
    if not parts:
        return
    info_logger_fn(f"{context}: {' '.join(parts)}")
    _record_memory_gauges(sample)


def _record_memory_gauges(sample: MemoryUsageSample) -> None:
    """Push the current memory sample to OTEL gauge state."""

    try:
        from platform_context_graph.observability import get_observability

        observability = get_observability()
        if hasattr(observability, "record_memory_usage"):
            observability.record_memory_usage(sample)
    except Exception:
        pass


def _read_process_rss_bytes() -> int | None:
    """Read the process RSS from ``/proc/self/status`` when present."""

    try:
        for line in PROC_STATUS_PATH.read_text(encoding="utf-8").splitlines():
            if not line.startswith("VmRSS:"):
                continue
            parts = line.split()
            if len(parts) < 2:
                return None
            return int(parts[1]) * 1024
    except (FileNotFoundError, OSError, ValueError):
        return None
    return None


def _read_cgroup_memory_bytes() -> int | None:
    """Read the current cgroup memory usage when present."""

    try:
        return int(CGROUP_MEMORY_CURRENT_PATH.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None


def _read_cgroup_memory_limit_bytes() -> int | None:
    """Read the cgroup memory limit from ``memory.max``, treating ``max`` as unbounded."""

    try:
        raw = CGROUP_MEMORY_MAX_PATH.read_text(encoding="utf-8").strip()
        if raw == "max":
            return None
        return int(raw)
    except (FileNotFoundError, OSError, ValueError):
        return None


def _format_mebibytes(size_bytes: int) -> str:
    """Return a human-readable mebibyte value."""

    return f"{size_bytes / _BYTES_PER_MIB:.1f}MiB"


__all__ = [
    "MemoryUsageSample",
    "log_memory_usage",
    "read_memory_usage_sample",
]
