"""Helpers for PlatformContextGraph version formatting."""

from __future__ import annotations


def ensure_v_prefix(version: str) -> str:
    """Return a user-facing version string prefixed with ``v``.

    Args:
        version: Raw version string from packaging metadata or config.

    Returns:
        Version text with a leading ``v`` when the input looks like a release
        version. Development fallback strings such as ``"0.0.0 (dev)"`` are
        also normalized to the same style for consistent CLI and API output.
    """

    cleaned = version.strip()
    if not cleaned:
        return "v0.0.0"
    if cleaned.startswith(("v", "V")):
        return f"v{cleaned[1:]}"
    return f"v{cleaned}"
