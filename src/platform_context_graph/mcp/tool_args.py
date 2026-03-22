"""Shared MCP tool-argument helpers."""

from __future__ import annotations

from typing import Any

__all__ = ["require_str_argument"]


def require_str_argument(args: dict[str, Any], key: str) -> str | None:
    """Return a stripped string argument when present and non-empty."""

    value = args.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
