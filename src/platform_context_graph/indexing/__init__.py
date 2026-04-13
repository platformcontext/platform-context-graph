"""Shared resumable indexing helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

__all__ = [
    "describe_index_run",
    "describe_latest_index_run",
]

if TYPE_CHECKING:
    from .run_status import describe_index_run, describe_latest_index_run


def __getattr__(name: str) -> Any:
    """Lazily expose coordinator-backed helpers without eager import cycles."""

    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from . import run_status

    return getattr(run_status, name)
