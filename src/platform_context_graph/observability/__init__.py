"""Public observability API for platform-context-graph."""

from __future__ import annotations

from .otel import (
    FastAPIInstrumentor,
    current_component,
    current_correlation_id,
    current_request_id,
    current_transport,
    new_request_id,
)
from .runtime import ObservabilityRuntime
from .state import (
    configure_test_exporters,
    get_observability,
    initialize_observability,
    reset_observability_for_tests,
    trace_query,
)
from .structured_logging import configure_logging

__all__ = [
    "FastAPIInstrumentor",
    "ObservabilityRuntime",
    "configure_logging",
    "configure_test_exporters",
    "current_component",
    "current_correlation_id",
    "current_request_id",
    "current_transport",
    "get_observability",
    "initialize_observability",
    "new_request_id",
    "reset_observability_for_tests",
    "trace_query",
]
