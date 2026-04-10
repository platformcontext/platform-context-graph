"""Support helpers for the shared projection tuning report script."""

from __future__ import annotations

from typing import Any

from platform_context_graph.query.shared_projection_tuning import (
    build_tuning_report as _build_tuning_report,
)
from platform_context_graph.query.shared_projection_tuning import (
    format_tuning_report_table,
)


def build_tuning_report(
    *,
    include_platform: bool = False,
) -> dict[str, Any]:
    """Return one deterministic shared-write tuning report payload."""

    return _build_tuning_report(include_platform=include_platform)


__all__ = [
    "build_tuning_report",
    "format_tuning_report_table",
]
