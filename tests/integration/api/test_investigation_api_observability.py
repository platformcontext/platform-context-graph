"""Integration coverage for investigation route telemetry."""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from typing import cast

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from starlette.testclient import TestClient


def _metric_points(
    reader: InMemoryMetricReader,
) -> list[tuple[str, dict[str, object], object]]:
    """Collect metric data points from an in-memory reader."""

    points: list[tuple[str, dict[str, object], object]] = []
    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None
    for resource_metric in metrics_data.resource_metrics:
        for scope_metric in resource_metric.scope_metrics:
            for metric in scope_metric.metrics:
                for point in metric.data.data_points:
                    attrs = {
                        str(key): cast(object, value)
                        for key, value in (point.attributes or {}).items()
                    }
                    value = getattr(point, "value", None)
                    if value is None:
                        value = getattr(point, "sum", None)
                    points.append((metric.name, attrs, value))
    return points


def test_investigation_route_emits_query_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The investigation API route should emit investigation query telemetry."""

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

    investigation_query = importlib.import_module(
        "platform_context_graph.query.investigation"
    )

    def fake_investigation_query(
        _database: object, **_kwargs: object
    ) -> dict[str, object]:
        return {
            "summary": ["sparse deployment evidence"],
            "repositories_considered": [
                {
                    "repo_id": "repository:r_app",
                    "repo_name": "api-node-boats",
                    "reason": "primary_service_repository",
                    "evidence_families": ["service_runtime"],
                }
            ],
            "repositories_with_evidence": [],
            "evidence_families_found": ["service_runtime"],
            "coverage_summary": {
                "searched_repository_count": 1,
                "repositories_with_evidence_count": 0,
                "searched_evidence_families": ["service_runtime", "gitops_config"],
                "found_evidence_families": ["service_runtime"],
                "missing_evidence_families": ["gitops_config"],
                "deployment_mode": "sparse",
                "deployment_planes": [],
                "graph_completeness": "partial",
                "content_completeness": "partial",
            },
            "investigation_findings": [],
            "limitations": [],
            "recommended_next_steps": [],
            "recommended_next_calls": [],
        }

    monkeypatch.setattr(
        "platform_context_graph.query.investigation.investigate_service_query",
        fake_investigation_query,
    )

    api_app = importlib.import_module("platform_context_graph.api.app")
    services = SimpleNamespace(
        database=object(),
        investigation=SimpleNamespace(
            investigate_service=investigation_query.investigate_service
        ),
    )

    app = api_app.create_app(query_services_dependency=lambda: services)
    with TestClient(app) as client:
        response = client.get(
            "/api/v0/investigations/services/api-node-boats"
            "?environment=bg-qa&intent=deployment"
        )

    assert response.status_code == 200
    spans = span_exporter.get_finished_spans()
    span_names = [span.name for span in spans]
    assert "pcg.query.investigate_service" in span_names

    investigation_span = next(
        span for span in spans if span.name == "pcg.query.investigate_service"
    )
    attributes = dict(investigation_span.attributes or {})
    assert attributes["pcg.investigation.deployment_mode"] == "sparse"
    assert attributes["pcg.investigation.missing_evidence_families_count"] == 1

    points = _metric_points(metric_reader)
    assert any(
        metric_name == "pcg_investigation_coverage_total"
        and attrs.get("pcg.investigation.deployment_mode") == "sparse"
        and attrs.get("pcg.investigation.has_missing_evidence") == "true"
        for metric_name, attrs, _value in points
    )
