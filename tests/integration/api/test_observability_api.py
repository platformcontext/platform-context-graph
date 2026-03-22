from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest

pytest.importorskip("httpx")
pytest.importorskip("opentelemetry.sdk")
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.testclient import TestClient


def _metric_points(
    reader: InMemoryMetricReader,
) -> list[tuple[str, dict[str, object], object]]:
    points: list[tuple[str, dict[str, object], object]] = []
    metrics_data = reader.get_metrics_data()
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                for point in metric.data.data_points:
                    points.append(
                        (
                            metric.name,
                            dict(point.attributes),
                            getattr(point, "value", None),
                        )
                    )
    return points


def test_create_app_emits_http_spans_and_skips_health_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "http://otel-collector.monitoring.svc.cluster.local:4317",
    )

    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    observability.configure_test_exporters(
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )

    api_app = importlib.import_module("platform_context_graph.api.app")

    services = SimpleNamespace(
        database=object(),
        repositories=SimpleNamespace(
            get_repository_context=lambda _database, **_kwargs: {
                "repository": {"id": "repository:r_ab12cd34", "name": "payments-api"}
            },
            get_repository_stats=lambda _database, **_kwargs: {
                "success": True,
                "stats": {"files": 10},
            },
        ),
    )

    app = api_app.create_app(query_services_dependency=lambda: services)
    with TestClient(app) as client:
        assert client.get("/api/v0/health").status_code == 200
        assert (
            client.get("/api/v0/repositories/repository:r_ab12cd34/context").status_code
            == 200
        )

    spans = span_exporter.get_finished_spans()
    span_names = [span.name for span in spans]
    assert "GET /api/v0/repositories/{repo_id:path}/context" in span_names
    assert "GET /api/v0/health" not in span_names
    assert any(
        metric_name == "pcg_http_requests_total"
        and attrs.get("http.route") == "/api/v0/repositories/{repo_id:path}/context"
        for metric_name, attrs, _value in _metric_points(metric_reader)
    )
