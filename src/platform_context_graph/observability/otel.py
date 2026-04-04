"""OpenTelemetry compatibility helpers for the observability subsystem."""

from __future__ import annotations

import contextlib
import contextvars
import os
from collections.abc import Iterator
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Any
from uuid import uuid4

from ..versioning import ensure_v_prefix

try:
    from fastapi import FastAPI
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.metrics import Observation
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import (
        InMemoryMetricReader,
        MetricReader,
        PeriodicExportingMetricReader,
    )
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        SimpleSpanProcessor,
        SpanExporter,
    )
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )
except ImportError:  # pragma: no cover - guarded by tests and dependency install
    FastAPI = Any  # type: ignore[assignment]
    Observation = Any  # type: ignore[assignment]
    MeterProvider = None  # type: ignore[assignment]
    MetricReader = Any  # type: ignore[assignment]
    PeriodicExportingMetricReader = None  # type: ignore[assignment]
    InMemoryMetricReader = Any  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]
    TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = None  # type: ignore[assignment]
    SimpleSpanProcessor = None  # type: ignore[assignment]
    SpanExporter = Any  # type: ignore[assignment]
    InMemorySpanExporter = Any  # type: ignore[assignment]
    OTLPMetricExporter = None  # type: ignore[assignment]
    OTLPSpanExporter = None  # type: ignore[assignment]
    FastAPIInstrumentor = None  # type: ignore[assignment]

DEFAULT_EXCLUDED_URLS = (
    "/health",
    "/api/v0/health",
    "/api/v0/openapi.json",
    "/api/v0/docs",
    "/api/v0/redoc",
)
ActiveStateKey = tuple[tuple[str, str], ...]

_CURRENT_COMPONENT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pcg_current_component",
    default=None,
)
_CURRENT_TRANSPORT: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pcg_current_transport",
    default=None,
)
_CURRENT_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pcg_current_request_id",
    default=None,
)
_CURRENT_CORRELATION_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "pcg_current_correlation_id",
    default=None,
)
REQUEST_CONTEXT_UNSET = object()


def package_version() -> str:
    """Return the installed package version.

    Returns:
        The installed distribution version, or ``"v0.0.0"`` when the package
        metadata is unavailable in the current environment.
    """

    try:
        return ensure_v_prefix(pkg_version("platform-context-graph"))
    except PackageNotFoundError:
        return "v0.0.0"


def env_truthy(name: str) -> bool:
    """Report whether an environment variable is set to a truthy value.

    Args:
        name: The environment variable name to inspect.

    Returns:
        ``True`` when the variable is present and matches the supported truthy
        values, otherwise ``False``.
    """

    value = os.getenv(name)
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


def excluded_urls() -> tuple[str, ...]:
    """Return the FastAPI routes that should be excluded from tracing.

    Returns:
        A tuple of route patterns sourced from the OTEL environment override
        when present, otherwise the platform defaults.
    """

    configured = os.getenv("OTEL_PYTHON_FASTAPI_EXCLUDED_URLS")
    if configured:
        return tuple(part.strip() for part in configured.split(",") if part.strip())
    return DEFAULT_EXCLUDED_URLS


def otel_endpoint_configured() -> bool:
    """Check whether OTLP exporter endpoints are configured.

    Returns:
        ``True`` when any supported OTLP endpoint environment variable is set,
        otherwise ``False``.
    """

    keys = (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT",
    )
    return any(os.getenv(key) for key in keys)


def service_name_for_component(component: str) -> str:
    """Map a platform component to its OpenTelemetry service name.

    Args:
        component: The logical platform component being instrumented.

    Returns:
        The service name reported through OpenTelemetry resources.
    """

    if component == "resolution-engine":
        return "platform-context-graph-resolution-engine"
    if component in {"bootstrap-index", "repo-sync", "ingester", "ingestor", "repository"}:
        return "platform-context-graph-ingestor"
    return "platform-context-graph-api"


def resource_attributes(service_name: str) -> dict[str, str]:
    """Build resource attributes for an OpenTelemetry provider.

    Args:
        service_name: The service name to report for this runtime.

    Returns:
        A dictionary of resource attributes merged with any OTEL environment
        overrides.
    """

    attributes = {
        "service.name": service_name,
        "service.namespace": "platformcontext",
        "service.version": package_version(),
    }

    environment = os.getenv("PCG_DEPLOYMENT_ENVIRONMENT") or os.getenv(
        "DEPLOYMENT_ENVIRONMENT"
    )
    if environment:
        attributes["deployment.environment"] = environment

    raw_attributes = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "")
    for item in raw_attributes.split(","):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and value:
            attributes[key] = value
    return attributes


def status_class(status_code: int) -> str:
    """Bucket an HTTP status code into its class.

    Args:
        status_code: The HTTP status code to classify.

    Returns:
        The status-code class label, such as ``"2xx"`` or ``"5xx"``.
    """

    if status_code >= 500:
        return "5xx"
    if status_code >= 400:
        return "4xx"
    if status_code >= 300:
        return "3xx"
    if status_code >= 200:
        return "2xx"
    return "1xx"


@contextlib.contextmanager
def request_context_scope(
    *,
    component: str,
    transport: str | None = None,
    request_id: str | None | object = REQUEST_CONTEXT_UNSET,
    correlation_id: str | None | object = REQUEST_CONTEXT_UNSET,
) -> Iterator[None]:
    """Set the current observability request context for a code block.

    Args:
        component: The logical component handling the request.
        transport: The transport label to record for the request, if any.
        request_id: The active request identifier, when one exists.
        correlation_id: The parent or local correlation identifier.

    Yields:
        ``None`` while the request context is active.
    """

    token_component = _CURRENT_COMPONENT.set(component)
    token_transport = _CURRENT_TRANSPORT.set(transport)
    token_request = None
    token_correlation = None
    if request_id is not REQUEST_CONTEXT_UNSET:
        token_request = _CURRENT_REQUEST_ID.set(request_id)
    if correlation_id is not REQUEST_CONTEXT_UNSET:
        token_correlation = _CURRENT_CORRELATION_ID.set(correlation_id)
    try:
        yield
    finally:
        if token_correlation is not None:
            _CURRENT_CORRELATION_ID.reset(token_correlation)
        if token_request is not None:
            _CURRENT_REQUEST_ID.reset(token_request)
        _CURRENT_COMPONENT.reset(token_component)
        _CURRENT_TRANSPORT.reset(token_transport)


def current_component() -> str | None:
    """Return the active observability component name.

    Returns:
        The current component label, or ``None`` when no request context is set.
    """

    return _CURRENT_COMPONENT.get()


def current_transport() -> str | None:
    """Return the active observability transport name.

    Returns:
        The current transport label, or ``None`` when no request context is set.
    """

    return _CURRENT_TRANSPORT.get()


def current_request_id() -> str | None:
    """Return the active request identifier."""

    value = _CURRENT_REQUEST_ID.get()
    if value is REQUEST_CONTEXT_UNSET:
        return None
    return value


def current_correlation_id() -> str | None:
    """Return the active correlation identifier."""

    value = _CURRENT_CORRELATION_ID.get()
    if value is REQUEST_CONTEXT_UNSET:
        return None
    return value


def new_request_id() -> str:
    """Return a fresh request identifier."""

    return uuid4().hex
