"""Prometheus scrape helpers for the observability subsystem."""

from __future__ import annotations

import os
from typing import Any

try:
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from prometheus_client import start_http_server
except ImportError:  # pragma: no cover - dependency availability is environment-specific
    PrometheusMetricReader = None  # type: ignore[assignment]
    start_http_server = None  # type: ignore[assignment]


def prometheus_metrics_enabled() -> bool:
    """Return whether the Prometheus scrape endpoint should be started."""

    value = os.getenv("PCG_PROMETHEUS_METRICS_ENABLED", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def prometheus_metrics_host() -> str:
    """Return the host address that should bind the scrape server."""

    return os.getenv("PCG_PROMETHEUS_METRICS_HOST", "0.0.0.0").strip() or "0.0.0.0"


def prometheus_metrics_port() -> int:
    """Return the port that should expose the Prometheus scrape endpoint."""

    raw_value = os.getenv("PCG_PROMETHEUS_METRICS_PORT", "9464").strip()
    try:
        return int(raw_value)
    except ValueError:
        return 9464


def create_prometheus_reader() -> Any | None:
    """Create a Prometheus metric reader when the exporter dependency exists."""

    if PrometheusMetricReader is None:
        return None
    return PrometheusMetricReader()


def start_prometheus_server(*, host: str, port: int) -> Any | None:
    """Start a Prometheus scrape server when the client dependency exists."""

    if start_http_server is None:
        return None
    return start_http_server(port=port, addr=host)
