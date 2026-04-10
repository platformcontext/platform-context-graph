"""Lightweight runtime status helpers for observability contexts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class _IndexRunScope:
    """Mutable status returned to callers inside an index-run context."""

    status: str
    finalization_status: str
