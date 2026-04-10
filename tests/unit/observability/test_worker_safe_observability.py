"""Focused regressions for worker-safe observability initialization."""

from __future__ import annotations

import importlib

import pytest


def test_initialize_observability_skips_prometheus_in_worker_safe_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker-safe mode should not create Prometheus readers or listeners."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    observability = importlib.import_module("platform_context_graph.observability")
    state = importlib.import_module("platform_context_graph.observability.state")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("PCG_PROMETHEUS_METRICS_ENABLED", "true")

    created_metric_exporters: list[object] = []
    sentinel_metric_reader = InMemoryMetricReader()

    monkeypatch.setattr(
        state,
        "OTLPMetricExporter",
        lambda: created_metric_exporters.append(object())
        or created_metric_exporters[-1],
    )
    monkeypatch.setattr(
        state,
        "PeriodicExportingMetricReader",
        lambda exporter: (
            sentinel_metric_reader
            if exporter in created_metric_exporters
            else pytest.fail("unexpected metric exporter")
        ),
    )
    monkeypatch.setattr(
        state,
        "_create_prometheus_reader",
        lambda: pytest.fail("worker-safe mode must not create a Prometheus reader"),
    )
    monkeypatch.setattr(
        state,
        "_start_prometheus_http_server",
        lambda **_kwargs: pytest.fail(
            "worker-safe mode must not start a Prometheus listener"
        ),
    )

    runtime = observability.initialize_observability(
        component="repository",
        allow_prometheus_scrape=False,
    )

    assert runtime.enabled is True
    assert runtime.metric_reader is sentinel_metric_reader
