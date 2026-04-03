"""Runtime orchestration helpers for the Resolution Engine."""

from __future__ import annotations

from typing import Any

__all__ = ["project_work_item", "run_resolution_iteration", "start_resolution_engine"]


def __getattr__(name: str) -> Any:
    """Load orchestration helpers lazily to avoid heavy import chains."""

    if name == "project_work_item":
        from .engine import project_work_item

        return project_work_item
    if name == "run_resolution_iteration":
        from .runtime import run_resolution_iteration

        return run_resolution_iteration
    if name == "start_resolution_engine":
        from .runtime import start_resolution_engine

        return start_resolution_engine
    raise AttributeError(name)
