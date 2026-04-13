"""Shared resumable indexing helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "describe_index_run",
    "IndexExecutionResult",
    "describe_latest_index_run",
    "execute_index_run",
    "raise_for_failed_index_run",
]

if TYPE_CHECKING:
    from .coordinator import IndexExecutionResult, execute_index_run, raise_for_failed_index_run
    from .run_status import describe_index_run, describe_latest_index_run


def __getattr__(name: str) -> Any:
    """Lazily expose coordinator-backed helpers without eager import cycles."""

    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name in {"describe_index_run", "describe_latest_index_run"}:
        from . import run_status

        return getattr(run_status, name)
    from . import coordinator

    return getattr(coordinator, name)
