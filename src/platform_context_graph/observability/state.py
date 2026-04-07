"""Global state management for the platform observability runtime."""

from __future__ import annotations

import contextlib
import os
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
from .prometheus import create_prometheus_reader
from .prometheus import prometheus_metrics_enabled
from .prometheus import prometheus_metrics_host
from .prometheus import prometheus_metrics_port
from .prometheus import start_prometheus_server
from .investigation_metrics import clear_investigation_instruments_cache
from .runtime import ObservabilityRuntime
from .structured_logging import configure_logging

_STATE_LOCK = threading.Lock()
_STATE: ObservabilityRuntime | None = None
_TEST_SPAN_EXPORTER: SpanExporter | None = None
_TEST_METRIC_READER: MetricReader | None = None
_PROMETHEUS_SERVER: Any | None = None


def _parse_exporters(name: str, *, default: str) -> set[str]:
    """Return normalized exporter names from an OTEL environment variable."""

    raw_value = os.getenv(name, default)
    return {item.strip().lower() for item in raw_value.split(",") if item.strip()}


def _create_prometheus_reader() -> MetricReader | None:
    """Create the Prometheus metric reader, if the dependency is installed."""

    return create_prometheus_reader()


def _start_prometheus_http_server(*, host: str, port: int) -> Any | None:
    """Start the Prometheus HTTP server on the requested host and port."""

    return start_prometheus_server(host=host, port=port)


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
    global _PROMETHEUS_SERVER

    configure_logging(component=component, runtime_role=component)

    with _STATE_LOCK:
        if _STATE is not None:
            if app is not None:
                _STATE.instrument_fastapi_app(app)
            return _STATE

        explicit_metric_reader = metric_reader or _TEST_METRIC_READER
        explicit_span_exporter = span_exporter or _TEST_SPAN_EXPORTER
        metric_exporters = _parse_exporters(
            "OTEL_METRICS_EXPORTER",
            default="otlp",
        )
        trace_exporters = _parse_exporters(
            "OTEL_TRACES_EXPORTER",
            default="otlp",
        )
        otlp_requested = otel_endpoint_configured()
        prometheus_requested = prometheus_metrics_enabled()
        metric_readers: list[MetricReader] = []

        if explicit_metric_reader is not None:
            metric_readers.append(explicit_metric_reader)
        else:
            if "otlp" in metric_exporters and otlp_requested:
                metric_readers.append(
                    PeriodicExportingMetricReader(OTLPMetricExporter())
                )
            if prometheus_requested or "prometheus" in metric_exporters:
                prometheus_reader = _create_prometheus_reader()
                if prometheus_reader is not None:
                    metric_readers.append(prometheus_reader)
                    if _PROMETHEUS_SERVER is None:
                        _PROMETHEUS_SERVER = _start_prometheus_http_server(
                            host=prometheus_metrics_host(),
                            port=prometheus_metrics_port(),
                        )

        tracing_enabled = explicit_span_exporter is not None or (
            "otlp" in trace_exporters and otlp_requested
        )
        metrics_enabled = bool(metric_readers)
        enabled = (
            TracerProvider is not None
            and MeterProvider is not None
            and not env_truthy("OTEL_SDK_DISABLED")
            and (tracing_enabled or metrics_enabled)
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
            explicit_span_exporter
            if explicit_span_exporter is not None
            else OTLPSpanExporter()
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
        if tracing_enabled:
            span_processor_cls = (
                SimpleSpanProcessor if use_simple_span_processor else BatchSpanProcessor
            )
            tracer_provider.add_span_processor(
                span_processor_cls(selected_span_exporter)
            )
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=metric_readers,
        )
        _STATE = ObservabilityRuntime(
            enabled=True,
            service_name=service_name_for_component(component),
            component=component,
            tracer_provider=tracer_provider if tracing_enabled else None,
            meter_provider=meter_provider,
            trace_exporter=selected_span_exporter if tracing_enabled else None,
            metric_reader=metric_readers[0] if metric_readers else None,
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

    global _PROMETHEUS_SERVER, _STATE, _TEST_SPAN_EXPORTER, _TEST_METRIC_READER
    with _STATE_LOCK:
        if _STATE is not None:
            with contextlib.suppress(Exception):
                _STATE.shutdown()
        if _PROMETHEUS_SERVER is not None:
            with contextlib.suppress(Exception):
                _PROMETHEUS_SERVER.shutdown()
            _PROMETHEUS_SERVER = None
        _STATE = None
        _TEST_SPAN_EXPORTER = None
        _TEST_METRIC_READER = None
        clear_investigation_instruments_cache()


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
