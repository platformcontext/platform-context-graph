"""Tests for MCP tool instrumentation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

if TYPE_CHECKING:
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )


def _metric_points(
    reader: InMemoryMetricReader,
) -> list[tuple[str, dict[str, object], object]]:
    """Collect metric points from an in-memory reader."""
    from typing import cast

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
    points: list[tuple[str, dict[str, object], object]],
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


def _span_names(exporter: InMemorySpanExporter) -> list[str]:
    """Return all span names from the exporter."""
    return [span.name for span in exporter.get_finished_spans()]


def _span_attributes(
    exporter: InMemorySpanExporter,
    span_name: str,
) -> dict[str, object]:
    """Return attributes for the first matching span."""
    for span in exporter.get_finished_spans():
        if span.name == span_name:
            return dict(span.attributes or {})
    return {}


def test_mcp_tool_instrumentation_records_spans_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MCP tool calls should create spans and emit duration/count metrics."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    import importlib

    observability = importlib.import_module("platform_context_graph.observability")
    mcp_instruments = importlib.import_module(
        "platform_context_graph.observability.mcp_instruments"
    )
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    metric_reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()
    runtime = observability.initialize_observability(
        component="mcp",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    def sample_tool_handler(**kwargs: object) -> dict[str, object]:
        """Sample MCP tool handler."""
        time.sleep(0.001)
        return {"success": True, "result": "data"}

    with mcp_instruments.instrument_mcp_tool(
        runtime,
        tool_name="find_code",
        handler=sample_tool_handler,
    ):
        result = sample_tool_handler(query="test")

    assert result == {"success": True, "result": "data"}

    points = _metric_points(metric_reader)
    span_names = _span_names(span_exporter)

    assert "pcg.mcp.tool_call" in span_names
    attrs = _span_attributes(span_exporter, "pcg.mcp.tool_call")
    assert attrs.get("pcg.mcp.tool_name") == "find_code"
    assert attrs.get("pcg.component") == "mcp"
    assert attrs.get("pcg.transport") == "mcp"

    assert _matching_values(
        points,
        "pcg_mcp_tool_calls_total",
        tool_name="find_code",
        status="succeeded",
    )
    durations = _matching_values(
        points,
        "pcg_mcp_tool_duration_seconds",
        tool_name="find_code",
    )
    assert len(durations) == 1
    assert isinstance(durations[0], (int, float))
    assert durations[0] > 0


def test_mcp_tool_instrumentation_records_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MCP tool failures should increment error counters."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    import importlib

    observability = importlib.import_module("platform_context_graph.observability")
    mcp_instruments = importlib.import_module(
        "platform_context_graph.observability.mcp_instruments"
    )
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    metric_reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()
    runtime = observability.initialize_observability(
        component="mcp",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    def failing_tool_handler(**kwargs: object) -> dict[str, object]:
        """Failing MCP tool handler."""
        raise ValueError("Tool execution failed")

    with pytest.raises(ValueError, match="Tool execution failed"):
        with mcp_instruments.instrument_mcp_tool(
            runtime,
            tool_name="analyze_code_relationships",
            handler=failing_tool_handler,
        ):
            failing_tool_handler()

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_mcp_tool_calls_total",
        tool_name="analyze_code_relationships",
        status="failed",
    )


def test_mcp_tool_instrumentation_completes_without_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MCP tool instrumentation should complete successfully and emit logs."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    import importlib

    observability = importlib.import_module("platform_context_graph.observability")
    mcp_instruments = importlib.import_module(
        "platform_context_graph.observability.mcp_instruments"
    )
    observability.reset_observability_for_tests()

    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    metric_reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()
    runtime = observability.initialize_observability(
        component="mcp",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    def sample_tool_handler(**kwargs: object) -> dict[str, object]:
        """Sample MCP tool handler."""
        return {"success": True}

    # Verify instrumentation completes successfully
    with mcp_instruments.instrument_mcp_tool(
        runtime,
        tool_name="get_file_content",
        handler=sample_tool_handler,
    ):
        result = sample_tool_handler()

    assert result == {"success": True}
