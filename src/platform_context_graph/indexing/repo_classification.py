"""Repository classification for observability tagging.

Assigns a repo class (small/medium/large/xlarge) based on pre-parse
signals and runtime observations. Classification drives metric
aggregation dimensions and anomaly threshold selection. It does NOT
change indexing behavior -- that is the Adaptive Optimization PRD.
"""

from __future__ import annotations

import os

# File count boundaries for pre-parse classification.
_SMALL_MAX = 99
_MEDIUM_MAX = 999
_LARGE_MAX = 4999

# Runtime reclassification thresholds.
_PARSE_DURATION_LARGE_SECONDS = 60.0
_PARSE_DURATION_XLARGE_SECONDS = 300.0
_ENTITY_DENSITY_LARGE = 50  # entities per file
_ENTITY_DENSITY_XLARGE = 100

# Ordered from smallest to largest for upgrade-only comparisons.
_CLASS_ORDER = ("small", "medium", "large", "xlarge")


def classify_repo_pre_parse(
    *,
    discovered_file_count: int,
    file_type_mix: dict[str, int] | None = None,
) -> str:
    """Assign a preliminary repo class from cheap pre-parse signals.

    Uses discovered file count as the primary signal. The ``file_type_mix``
    parameter is accepted for future use but not yet factored into the
    classification decision.

    Args:
        discovered_file_count: Total files discovered before filtering.
        file_type_mix: Optional per-extension file counts (reserved).

    Returns:
        One of ``small``, ``medium``, ``large``, ``xlarge``.
    """
    if discovered_file_count <= _SMALL_MAX:
        return "small"
    if discovered_file_count <= _MEDIUM_MAX:
        return "medium"
    if discovered_file_count <= _LARGE_MAX:
        return "large"
    return "xlarge"


def classify_repo_runtime(
    *,
    pre_class: str,
    parse_duration_seconds: float,
    parsed_file_count: int,
    entity_count: int = 0,
    rss_mib_commit_end: float | None = None,
) -> str:
    """Refine repo class using runtime signals after parse/commit.

    A repo's class can be upgraded (e.g. medium to large) but NEVER
    downgraded within the same run, preventing oscillation.

    Args:
        pre_class: The pre-parse classification result.
        parse_duration_seconds: Observed parse wall-clock time.
        parsed_file_count: Files successfully parsed.
        entity_count: Total entities extracted (optional).
        rss_mib_commit_end: Process RSS at commit exit in MiB (optional).

    Returns:
        The refined repo class, always >= pre_class in the class order.
    """
    pre_rank = _CLASS_ORDER.index(pre_class) if pre_class in _CLASS_ORDER else 0
    runtime_class = pre_class

    # Check parse duration thresholds
    if parse_duration_seconds >= _PARSE_DURATION_XLARGE_SECONDS:
        runtime_class = "xlarge"
    elif parse_duration_seconds >= _PARSE_DURATION_LARGE_SECONDS:
        runtime_class = "large"

    # Check entity density if we have entity counts
    if parsed_file_count > 0 and entity_count > 0:
        density = entity_count / parsed_file_count
        if density >= _ENTITY_DENSITY_XLARGE:
            runtime_class = "xlarge"
        elif density >= _ENTITY_DENSITY_LARGE:
            if runtime_class not in ("large", "xlarge"):
                runtime_class = "large"

    # Enforce upgrade-only: never downgrade from pre_class
    runtime_rank = (
        _CLASS_ORDER.index(runtime_class) if runtime_class in _CLASS_ORDER else 0
    )
    if runtime_rank < pre_rank:
        return pre_class
    return runtime_class


def load_repo_class_overrides() -> dict[str, str]:
    """Load per-repo class overrides from the environment.

    Format: ``PCG_REPO_CLASS_OVERRIDE=repo_name:class,repo_name:class``
    Malformed entries (missing colon) are silently skipped.

    Returns:
        A dict mapping repo names to their pinned class strings.
    """
    raw = os.getenv("PCG_REPO_CLASS_OVERRIDE")
    if not raw or not raw.strip():
        return {}

    overrides: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" not in entry:
            continue
        parts = entry.split(":", 1)
        repo_name = parts[0].strip()
        repo_class = parts[1].strip()
        if repo_name and repo_class:
            overrides[repo_name] = repo_class
    return overrides


__all__ = [
    "classify_repo_pre_parse",
    "classify_repo_runtime",
    "load_repo_class_overrides",
]
