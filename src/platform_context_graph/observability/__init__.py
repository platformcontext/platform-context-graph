"""Public observability API for platform-context-graph."""

from __future__ import annotations

from .otel import (
    FastAPIInstrumentor,
    current_component,
    current_transport,
)
from .runtime import ObservabilityRuntime
from .state import (
    configure_test_exporters,
    get_observability,
    initialize_observability,
    reset_observability_for_tests,
    trace_query,
)

__all__ = [
    "ObservabilityRuntime",
    "configure_test_exporters",
    "current_component",
    "current_transport",
    "get_observability",
    "initialize_observability",
    "reset_observability_for_tests",
    "trace_query",
]
