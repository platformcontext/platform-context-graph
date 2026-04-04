"""Helpers for PlatformContextGraph version formatting."""

from __future__ import annotations

import re


_PREFIXED_VERSION_PATTERN = re.compile(r"^[vV]\d")


def ensure_v_prefix(version: str) -> str:
    """Return a normalized user-facing version string with ``v`` prefix.

    Args:
        version: Raw version string from packaging metadata or config.

    Returns:
        Version text normalized to use a lowercase leading ``v`` for any
        non-empty input. Development fallback strings such as
        ``"0.0.0 (dev)"`` are normalized to the same style for consistent CLI
        and API output. Empty or whitespace-only input falls back to
        ``"v0.0.0"``.
    """

    cleaned = version.strip()
    if not cleaned:
        return "v0.0.0"
    if _PREFIXED_VERSION_PATTERN.match(cleaned):
        return f"v{cleaned[1:]}"
    return f"v{cleaned}"
