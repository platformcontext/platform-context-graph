"""Shared helper functions for repository content enrichment."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml


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


def ordered_unique_strings(values: Iterable[Any]) -> list[str]:
    """Return ordered unique non-empty string values."""

    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def load_yaml_path(path: Path) -> Any | None:
    """Load one YAML file from disk, returning ``None`` on parse errors."""

    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None


def flatten_string_values(value: Any) -> list[str]:
    """Flatten nested scalar values into a simple list of strings."""

    if value is None:
        return []
    if isinstance(value, dict):
        flattened: list[str] = []
        for key, child in value.items():
            flattened.extend(flatten_string_values(key))
            flattened.extend(flatten_string_values(child))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for child in value:
            flattened.extend(flatten_string_values(child))
        return flattened
    normalized = str(value).strip()
    return [normalized] if normalized else []
