"""Public investigation query entrypoints."""

from __future__ import annotations

from typing import Any

from ..observability import trace_query
from .investigation_service import investigate_service as investigate_service_query

__all__ = ["investigate_service"]


def investigate_service(
    database: Any,
    *,
    service_name: str,
    environment: str | None = None,
    intent: str | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Return an orchestrated investigation for one service."""

    with trace_query("investigate_service"):
        return investigate_service_query(
            database,
            service_name=service_name,
            environment=environment,
            intent=intent,
            question=question,
        )
