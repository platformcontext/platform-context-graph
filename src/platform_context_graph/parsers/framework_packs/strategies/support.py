"""Shared helpers for declarative framework semantic strategies."""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Any, Pattern


def pack_config(pack_spec: dict[str, Any]) -> dict[str, Any]:
    """Return the normalized config payload for one pack spec."""

    config = pack_spec.get("config") or {}
    if isinstance(config, dict):
        return config
    return {}


def config_list(config: dict[str, Any], key: str, *, default: list[str]) -> list[str]:
    """Return a normalized list-of-strings config value."""

    value = config.get(key)
    if not isinstance(value, list):
        return default
    return [str(item) for item in value if isinstance(item, str)]


def config_string(config: dict[str, Any], key: str, *, default: str) -> str:
    """Return a normalized string config value."""

    value = config.get(key)
    if isinstance(value, str):
        return value
    return default


def imports_any_source(imports: list[dict[str, Any]], *, sources: list[str]) -> bool:
    """Return whether the module imports any source in the configured set."""

    source_set = set(sources)
    return any(item.get("source") in source_set for item in imports)


@lru_cache(maxsize=None)
def compile_patterns(patterns: tuple[str, ...]) -> tuple[Pattern[str], ...]:
    """Compile regex patterns once for repeated framework-pack use."""

    return tuple(re.compile(pattern, re.MULTILINE) for pattern in patterns)


def ordered_unique(values: list[str] | tuple[str, ...] | set[str] | Any) -> list[str]:
    """Return unique string values while preserving first-seen order."""

    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def strip_js_comments(source_code: str) -> str:
    """Remove JS-style line and block comments from source text."""

    without_blocks = re.sub(r"/\*.*?\*/", "", source_code, flags=re.DOTALL)
    return re.sub(r"^\s*//.*$", "", without_blocks, flags=re.MULTILINE)
