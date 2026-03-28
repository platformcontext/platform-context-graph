"""Shared MCP tool-argument helpers."""

from __future__ import annotations

from typing import Any

__all__ = ["require_int_argument", "require_str_argument"]


def require_str_argument(args: dict[str, Any], key: str) -> str | None:
    """Return a stripped string argument when present and non-empty."""

    value = args.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def require_int_argument(
    args: dict[str, Any],
    key: str,
    *,
    default: int,
    minimum: int | None = None,
) -> int:
    """Return a bounded integer argument or the supplied default.

    Non-integer or out-of-range values fall back to ``default`` so MCP tools do
    not fail with unstructured tracebacks when clients send loose JSON values.
    """

    value = args.get(key)
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if minimum is not None and parsed < minimum:
        return default
    return parsed
