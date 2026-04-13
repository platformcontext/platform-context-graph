"""Query-layer instrumentation helpers for observability."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .runtime import ObservabilityRuntime

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def instrument_query(
    runtime: ObservabilityRuntime,
    *,
    query_type: str,
    db_system: str,
) -> Iterator[None]:
    """Instrument one query operation with spans and metrics.

    Args:
        runtime: The active observability runtime.
        query_type: The logical query type being executed.
        db_system: The database system (neo4j, postgresql).

    Yields:
        ``None`` while the query executes.
    """
    start = time.perf_counter()
    status = "succeeded"

    with runtime.start_span(
        "pcg.query.execute",
        component="query",
        attributes={
            "pcg.query.type": query_type,
            "pcg.component": "query",
            "db.system": db_system,
        },
    ):
        try:
            yield
        except Exception:
            status = "failed"
            raise
        finally:
            duration = time.perf_counter() - start
            _record_query_metrics(
                runtime,
                query_type=query_type,
                db_system=db_system,
                duration_seconds=duration,
                status=status,
            )


def _record_query_metrics(
    runtime: ObservabilityRuntime,
    *,
    query_type: str,
    db_system: str,
    duration_seconds: float,
    status: str,
) -> None:
    """Record query metrics to the observability runtime.

    Args:
        runtime: The active observability runtime.
        query_type: The logical query type.
        db_system: The database system (neo4j, postgresql).
        duration_seconds: The query duration in seconds.
        status: The query status (succeeded/failed).
    """
    if not runtime.enabled:
        return

    attrs = {
        "query_type": query_type,
        "db_system": db_system,
        "status": status,
    }

    if hasattr(runtime, "query_total") and runtime.query_total:
        runtime.query_total.add(1, attrs)

    duration_attrs = {
        "query_type": query_type,
        "db_system": db_system,
    }
    if hasattr(runtime, "query_duration") and runtime.query_duration:
        runtime.query_duration.record(duration_seconds, duration_attrs)


__all__ = ["instrument_query"]
