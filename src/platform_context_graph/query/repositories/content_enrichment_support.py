"""Shared helper functions for repository content enrichment."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def values_path_patterns(source_path: str) -> list[str]:
    """Return related values-file glob patterns for one source path hint."""

    normalized = source_path.strip()
    if not normalized:
        return []
    patterns: list[str] = []
    if normalized.endswith("config.yaml"):
        patterns.append(normalized[:-len("config.yaml")] + "values.yaml")
    elif normalized.endswith("config.yml"):
        patterns.append(normalized[:-len("config.yml")] + "values.yaml")
    elif normalized.endswith(".yaml") or normalized.endswith(".yml"):
        patterns.append(normalized)
    else:
        patterns.append(str(Path(normalized) / "values.yaml"))

    overlay_marker = "/overlays/"
    for pattern in list(patterns):
        if overlay_marker not in pattern:
            continue
        prefix, _, remainder = pattern.partition(overlay_marker)
        remainder_parts = Path(remainder).parts
        if len(remainder_parts) >= 2:
            base_pattern = str(Path(prefix) / "base" / "values.yaml")
            if base_pattern not in patterns:
                patterns.append(base_pattern)
    return patterns


def infer_environment_from_path(relative_path: str) -> str | None:
    """Infer environment name from a repo-relative path."""

    for part in Path(relative_path).parts:
        normalized = part.strip()
        if normalized in {"dev", "development", "prod", "production", "qa", "staging"}:
            return normalized
        if normalized.startswith("bg-"):
            return normalized
    return None


def split_csv(value: Any) -> list[str]:
    """Split a comma-delimited string field into trimmed items."""

    if not isinstance(value, str):
        return []
    return [item.strip() for item in value.split(",") if item.strip()]
