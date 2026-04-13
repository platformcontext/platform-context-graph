"""Tests for query-layer instrumentation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

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


def test_query_instrumentation_records_spans_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query operations should create spans and emit duration/count metrics."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    import importlib

    observability = importlib.import_module("platform_context_graph.observability")
    query_instruments = importlib.import_module(
        "platform_context_graph.observability.query_instruments"
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
        component="query",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    with query_instruments.instrument_query(
        runtime,
        query_type="investigate_service",
        db_system="neo4j",
    ):
        time.sleep(0.001)

    points = _metric_points(metric_reader)
    span_names = _span_names(span_exporter)

    assert "pcg.query.execute" in span_names
    attrs = _span_attributes(span_exporter, "pcg.query.execute")
    assert attrs.get("pcg.query.type") == "investigate_service"
    assert attrs.get("pcg.component") == "query"
    assert attrs.get("db.system") == "neo4j"

    assert _matching_values(
        points,
        "pcg_query_total",
        query_type="investigate_service",
        db_system="neo4j",
        status="succeeded",
    )
    durations = _matching_values(
        points,
        "pcg_query_duration_seconds",
        query_type="investigate_service",
        db_system="neo4j",
    )
    assert len(durations) == 1
    assert isinstance(durations[0], (int, float))
    assert durations[0] > 0


def test_query_instrumentation_records_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query failures should increment error counters."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    import importlib

    observability = importlib.import_module("platform_context_graph.observability")
    query_instruments = importlib.import_module(
        "platform_context_graph.observability.query_instruments"
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
        component="query",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    with pytest.raises(ValueError, match="Query failed"):
        with query_instruments.instrument_query(
            runtime,
            query_type="get_entity_context",
            db_system="postgresql",
        ):
            raise ValueError("Query failed")

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_query_total",
        query_type="get_entity_context",
        db_system="postgresql",
        status="failed",
    )


def test_query_instrumentation_supports_multiple_db_systems(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query instrumentation should tag metrics by database system."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    import importlib

    observability = importlib.import_module("platform_context_graph.observability")
    query_instruments = importlib.import_module(
        "platform_context_graph.observability.query_instruments"
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
        component="api",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    with query_instruments.instrument_query(
        runtime,
        query_type="find_code",
        db_system="neo4j",
    ):
        pass

    with query_instruments.instrument_query(
        runtime,
        query_type="get_file_content",
        db_system="postgresql",
    ):
        pass

    points = _metric_points(metric_reader)

    neo4j_queries = _matching_values(
        points,
        "pcg_query_total",
        query_type="find_code",
        db_system="neo4j",
        status="succeeded",
    )
    postgres_queries = _matching_values(
        points,
        "pcg_query_total",
        query_type="get_file_content",
        db_system="postgresql",
        status="succeeded",
    )

    assert len(neo4j_queries) == 1
    assert len(postgres_queries) == 1
