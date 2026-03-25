"""Shared resumable indexing helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "IndexExecutionResult",
    "describe_latest_index_run",
    "execute_index_run",
    "raise_for_failed_index_run",
]

if TYPE_CHECKING:
    from .coordinator import (
        IndexExecutionResult,
        describe_latest_index_run,
        execute_index_run,
        raise_for_failed_index_run,
    )


def __getattr__(name: str) -> Any:
    """Lazily expose coordinator-backed helpers without eager import cycles."""

    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import coordinator

    return getattr(coordinator, name)
