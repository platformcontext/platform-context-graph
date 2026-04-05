from __future__ import annotations

import importlib
import inspect
from collections.abc import Iterable
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader


def _metric_points(
    reader: InMemoryMetricReader,
) -> list[tuple[str, dict[str, object], object]]:
    """Collect metric points from an in-memory reader."""

    points: list[tuple[str, dict[str, object], object]] = []
    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                for point in metric.data.data_points:
                    point_attributes = point.attributes or {}
                    attrs = {
                        str(key): cast(object, value)
                        for key, value in point_attributes.items()
                    }
                    value = getattr(point, "value", None)
                    if value is None:
                        value = getattr(point, "sum", None)
                    points.append((metric.name, attrs, value))
    return points


def _matching_values(
    points: Iterable[tuple[str, dict[str, object], object]],
    name: str,
    **expected_attrs: object,
) -> list[object]:
    """Return metric values whose name and attributes match the expectation."""

    values: list[object] = []
    for metric_name, attrs, value in points:
        if metric_name != name:
            continue
        if all(attrs.get(key) == expected for key, expected in expected_attrs.items()):
            values.append(value)
    return values


def test_initialize_observability_skips_instrumentation_when_sdk_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disable instrumentation when the OTEL SDK is explicitly disabled."""

    pytest.importorskip("opentelemetry.sdk")
    from fastapi import FastAPI

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    app = FastAPI()
    with pytest.MonkeyPatch.context() as patch_ctx:
        patch_ctx.setattr(
            "platform_context_graph.observability.FastAPIInstrumentor.instrument_app",
            lambda *args, **kwargs: pytest.fail(
                "FastAPI should not be instrumented when OTEL is disabled"
            ),
        )
        runtime = observability.initialize_observability(component="api", app=app)

    assert runtime.enabled is False


def test_package_version_returns_raw_semver_for_otel_resource() -> None:
    """Keep the OTEL service.version resource attribute semver-like."""

    otel = importlib.import_module("platform_context_graph.observability.otel")

    with pytest.MonkeyPatch.context() as patch_ctx:
        patch_ctx.setattr(otel, "pkg_version", lambda _name: "0.0.46")
        assert otel.package_version() == "0.0.46"


def test_package_version_falls_back_to_zero_when_distribution_missing() -> None:
    """Use an unprefixed fallback when package metadata is unavailable."""

    otel = importlib.import_module("platform_context_graph.observability.otel")

    def _raise_missing(_name: str) -> str:
        raise PackageNotFoundError

    with pytest.MonkeyPatch.context() as patch_ctx:
        patch_ctx.setattr(otel, "pkg_version", _raise_missing)
        assert otel.package_version() == "0.0.0"


def test_initialize_observability_instruments_fastapi_once_and_honors_exclusions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Instrument FastAPI once and pass the expected excluded routes."""

    pytest.importorskip("opentelemetry.sdk")
    from fastapi import FastAPI
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    app = FastAPI()
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    instrument_calls: list[dict[str, object]] = []

    def _capture_instrument_call(*_args: object, **kwargs: object) -> None:
        instrument_calls.append(kwargs)

    with pytest.MonkeyPatch.context() as patch_ctx:
        patch_ctx.setattr(
            "platform_context_graph.observability.FastAPIInstrumentor.instrument_app",
            _capture_instrument_call,
        )
        first = observability.initialize_observability(
            component="api",
            app=app,
            span_exporter=span_exporter,
            metric_reader=metric_reader,
        )
        second = observability.initialize_observability(
            component="api",
            app=app,
            span_exporter=span_exporter,
            metric_reader=metric_reader,
        )

    assert first is second
    assert first.enabled is True
    assert len(instrument_calls) == 1
    assert "/api/v0/openapi.json" in str(instrument_calls[0]["excluded_urls"])
    assert "/health" in str(instrument_calls[0]["excluded_urls"])


def test_initialize_observability_enables_prometheus_metrics_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create a Prometheus reader and start the scrape server when enabled."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    observability = importlib.import_module("platform_context_graph.observability")
    state = importlib.import_module("platform_context_graph.observability.state")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("PCG_PROMETHEUS_METRICS_ENABLED", "true")
    monkeypatch.setenv("PCG_PROMETHEUS_METRICS_PORT", "9470")
    monkeypatch.setenv("PCG_PROMETHEUS_METRICS_HOST", "0.0.0.0")

    sentinel_reader = InMemoryMetricReader()
    started_servers: list[tuple[str, int]] = []

    monkeypatch.setattr(
        state,
        "_create_prometheus_reader",
        lambda: sentinel_reader,
    )
    monkeypatch.setattr(
        state,
        "_start_prometheus_http_server",
        lambda *, host, port: (
            started_servers.append((host, port)),
            object(),
        )[1],
    )

    runtime = observability.initialize_observability(component="resolution-engine")

    assert runtime.enabled is True
    assert started_servers == [("0.0.0.0", 9470)]


def test_index_metrics_record_hidden_dir_skips_and_active_repo_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Record index-run gauges and hidden-directory counters."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    metric_reader = InMemoryMetricReader()
    runtime = observability.initialize_observability(
        component="bootstrap-index",
        metric_reader=metric_reader,
        span_exporter=InMemorySpanExporter(),
    )

    with runtime.index_run(mode="bootstrap", source="filesystem", repo_count=3):
        runtime.record_hidden_directory_skip(".terraform")
        runtime.record_hidden_directory_skip(".terragrunt-cache")
        points_during_run = _metric_points(metric_reader)

    points_after_run = _metric_points(metric_reader)

    assert _matching_values(
        points_during_run,
        "pcg_index_active_repositories",
        component="bootstrap-index",
        mode="bootstrap",
        source="filesystem",
    )
    assert _matching_values(
        points_after_run,
        "pcg_hidden_dirs_skipped_total",
        component="bootstrap-index",
        kind=".terraform",
    )
    assert _matching_values(
        points_after_run,
        "pcg_hidden_dirs_skipped_total",
        component="bootstrap-index",
        kind=".terragrunt-cache",
    )
    assert _matching_values(
        points_after_run,
        "pcg_index_runs_total",
        component="bootstrap-index",
        mode="bootstrap",
        source="filesystem",
        status="completed",
    )


def test_content_provider_metrics_record_hits_and_workspace_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Record content-provider backend metrics for cache hits and fallbacks."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    metric_reader = InMemoryMetricReader()
    runtime = observability.initialize_observability(
        component="api",
        metric_reader=metric_reader,
        span_exporter=InMemorySpanExporter(),
    )

    runtime.record_content_provider_result(
        operation="get_file_content",
        backend="postgres",
        success=True,
        hit=True,
        duration_seconds=0.01,
    )
    runtime.record_content_provider_result(
        operation="get_file_content",
        backend="workspace",
        success=True,
        hit=True,
        duration_seconds=0.02,
    )
    runtime.record_content_workspace_fallback(operation="get_file_content")

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_content_provider_requests_total",
        **{
            "pcg.component": "api",
            "pcg.content.operation": "get_file_content",
            "pcg.content.backend": "postgres",
            "pcg.content.success": "true",
            "pcg.content.hit": "true",
        },
    )
    assert _matching_values(
        points,
        "pcg_content_workspace_fallback_total",
        **{
            "pcg.component": "api",
            "pcg.content.operation": "get_file_content",
        },
    )


def test_ingester_scan_request_metrics_and_service_name_use_ingester_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository ingester control events should emit on the ingester service."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    observability = importlib.import_module("platform_context_graph.observability")
    otel = importlib.import_module("platform_context_graph.observability.otel")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    metric_reader = InMemoryMetricReader()
    runtime = observability.initialize_observability(
        component="repository",
        metric_reader=metric_reader,
        span_exporter=InMemorySpanExporter(),
    )
    runtime.record_ingester_scan_request(
        ingester="repository",
        phase="claimed",
        requested_by="api",
        accepted=True,
    )

    points = _metric_points(metric_reader)

    assert (
        otel.service_name_for_component("repository")
        == "platform-context-graph-ingester"
    )
    assert _matching_values(
        points,
        "pcg_ingester_scan_requests_total",
        ingester="repository",
        phase="claimed",
        requested_by="api",
        accepted="true",
    )


def test_graph_write_batch_metrics_record_duration_and_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graph write batches should emit duration and row metrics by batch type."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    metric_reader = InMemoryMetricReader()
    runtime = observability.initialize_observability(
        component="repository",
        metric_reader=metric_reader,
        span_exporter=InMemorySpanExporter(),
    )

    runtime.record_graph_write_batch(
        batch_type="entity",
        label="Variable",
        rows=7244,
        duration_seconds=0.25,
    )
    runtime.record_graph_write_batch(
        batch_type="parameters",
        label=None,
        rows=260,
        duration_seconds=0.13,
    )

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_graph_write_batch_rows",
        **{
            "pcg.component": "repository",
            "pcg.graph.batch_type": "entity",
            "pcg.graph.label": "Variable",
        },
    )
    assert _matching_values(
        points,
        "pcg_graph_write_batch_duration_seconds",
        **{
            "pcg.component": "repository",
            "pcg.graph.batch_type": "parameters",
            "pcg.graph.label": "none",
        },
    )


def test_observability_public_api_has_docstrings() -> None:
    """Expose docstrings on the public observability module and API."""

    observability = importlib.import_module("platform_context_graph.observability")

    public_names = (
        "ObservabilityRuntime",
        "configure_test_exporters",
        "current_component",
        "current_transport",
        "get_observability",
        "initialize_observability",
        "reset_observability_for_tests",
        "trace_query",
    )

    assert inspect.getdoc(observability)
    for name in public_names:
        assert inspect.getdoc(getattr(observability, name)), name


def test_observability_modules_stay_within_line_budget() -> None:
    """Keep each observability module within the agreed line budget."""

    package_dir = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "platform_context_graph"
        / "observability"
    )
    observability_modules = sorted(package_dir.glob("*.py"))

    assert observability_modules
    for module_path in observability_modules:
        assert (
            sum(1 for _line in module_path.open(encoding="utf-8")) <= 500
        ), module_path
