"""Global state management for the platform observability runtime."""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Iterator
from typing import Any

from .otel import (
    BatchSpanProcessor,
    FastAPI,
    MeterProvider,
    MetricReader,
    OTLPMetricExporter,
    OTLPSpanExporter,
    PeriodicExportingMetricReader,
    Resource,
    SimpleSpanProcessor,
    SpanExporter,
    TracerProvider,
    current_component,
    env_truthy,
    excluded_urls,
    otel_endpoint_configured,
    resource_attributes,
    service_name_for_component,
)
from .runtime import ObservabilityRuntime
from .structured_logging import configure_logging

_STATE_LOCK = threading.Lock()
_STATE: ObservabilityRuntime | None = None
_TEST_SPAN_EXPORTER: SpanExporter | None = None
_TEST_METRIC_READER: MetricReader | None = None


def initialize_observability(
    *,
    component: str,
    app: FastAPI | None = None,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> ObservabilityRuntime:
    """Create or reuse the process-wide observability runtime.

    Args:
        component: The logical component being instrumented.
        app: A FastAPI application to instrument, if one should be attached.
        span_exporter: An explicit span exporter override, typically for tests.
        metric_reader: An explicit metric reader override, typically for tests.

    Returns:
        The shared observability runtime for the current process.
    """

    global _STATE, _TEST_SPAN_EXPORTER, _TEST_METRIC_READER

    configure_logging(component=component, runtime_role=component)

    with _STATE_LOCK:
        if _STATE is not None:
            if app is not None:
                _STATE.instrument_fastapi_app(app)
            return _STATE

        enabled = (
            TracerProvider is not None
            and MeterProvider is not None
            and not env_truthy("OTEL_SDK_DISABLED")
            and (
                otel_endpoint_configured()
                or _TEST_SPAN_EXPORTER is not None
                or _TEST_METRIC_READER is not None
            )
        )

        if not enabled:
            _STATE = ObservabilityRuntime(
                enabled=False,
                service_name=service_name_for_component(component),
                component=component,
            )
            if app is not None:
                _STATE.instrument_fastapi_app(app)
            return _STATE

        selected_span_exporter = (
            span_exporter or _TEST_SPAN_EXPORTER or OTLPSpanExporter()
        )
        selected_metric_reader = (
            metric_reader
            or _TEST_METRIC_READER
            or PeriodicExportingMetricReader(OTLPMetricExporter())
        )
        use_simple_span_processor = (
            span_exporter is not None or _TEST_SPAN_EXPORTER is not None
        )
        _TEST_SPAN_EXPORTER = None
        _TEST_METRIC_READER = None

        resource = Resource.create(
            resource_attributes(service_name_for_component(component))
        )
        tracer_provider = TracerProvider(resource=resource)
        span_processor_cls = (
            SimpleSpanProcessor if use_simple_span_processor else BatchSpanProcessor
        )
        tracer_provider.add_span_processor(span_processor_cls(selected_span_exporter))
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[selected_metric_reader],
        )
        _STATE = ObservabilityRuntime(
            enabled=True,
            service_name=service_name_for_component(component),
            component=component,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            trace_exporter=selected_span_exporter,
            metric_reader=selected_metric_reader,
            excluded_urls=excluded_urls(),
        )
        if app is not None:
            _STATE.instrument_fastapi_app(app)
        return _STATE


def get_observability() -> ObservabilityRuntime:
    """Return the shared observability runtime.

    Returns:
        The process-wide observability runtime, creating the default API runtime
        on first access.
    """

    global _STATE
    if _STATE is None:
        return initialize_observability(component="api")
    return _STATE


def configure_test_exporters(
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> None:
    """Set in-memory exporters that should be used by the next initialization.

    Args:
        span_exporter: The span exporter to use for the next runtime creation.
        metric_reader: The metric reader to use for the next runtime creation.
    """

    global _TEST_SPAN_EXPORTER, _TEST_METRIC_READER
    _TEST_SPAN_EXPORTER = span_exporter
    _TEST_METRIC_READER = metric_reader


def reset_observability_for_tests() -> None:
    """Clear the shared observability runtime and test exporters."""

    global _STATE, _TEST_SPAN_EXPORTER, _TEST_METRIC_READER
    with _STATE_LOCK:
        if _STATE is not None:
            with contextlib.suppress(Exception):
                _STATE.shutdown()
        _STATE = None
        _TEST_SPAN_EXPORTER = None
        _TEST_METRIC_READER = None


@contextlib.contextmanager
def trace_query(
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Wrap a query operation in a component-aware tracing span.

    Args:
        name: The logical query name to append to the span prefix.
        attributes: Additional span attributes to include in the emitted span.

    Yields:
        The active span object, or ``None`` when tracing is disabled.
    """

    runtime = get_observability()
    component = current_component() or "unknown"
    with runtime.start_span(
        f"pcg.query.{name}",
        component=component,
        attributes=attributes,
    ) as span:
        yield span
