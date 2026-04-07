"""Observability coverage for the service investigation query wrapper."""

from __future__ import annotations

import importlib
from typing import cast

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


def _metric_points(
    reader: InMemoryMetricReader,
) -> list[tuple[str, dict[str, object], object]]:
    """Collect metric data points from the in-memory OTEL reader."""

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


def test_investigate_service_emits_span_attributes_and_quality_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The investigation query should stamp spans and metrics with quality data."""

    observability = importlib.import_module("platform_context_graph.observability")
    observability.reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    observability.initialize_observability(
        component="api",
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
            "summary": ["dual deployment detected"],
            "repositories_considered": [
                {
                    "repo_id": "repository:r_app",
                    "repo_name": "api-node-boats",
                    "reason": "primary_service_repository",
                    "evidence_families": ["service_runtime"],
                },
                {
                    "repo_id": "repository:r_tf",
                    "repo_name": "terraform-stack-node10",
                    "reason": "oidc_role_subject",
                    "evidence_families": ["iac_infrastructure"],
                },
            ],
            "repositories_with_evidence": [
                {
                    "repo_id": "repository:r_tf",
                    "repo_name": "terraform-stack-node10",
                    "reason": "oidc_role_subject",
                    "evidence_families": ["iac_infrastructure"],
                }
            ],
            "evidence_families_found": [
                "service_runtime",
                "deployment_controller",
                "gitops_config",
                "iac_infrastructure",
                "ci_cd_pipeline",
            ],
            "coverage_summary": {
                "searched_repository_count": 2,
                "repositories_with_evidence_count": 1,
                "searched_evidence_families": [
                    "service_runtime",
                    "deployment_controller",
                    "gitops_config",
                    "iac_infrastructure",
                    "ci_cd_pipeline",
                ],
                "found_evidence_families": [
                    "service_runtime",
                    "deployment_controller",
                    "gitops_config",
                    "iac_infrastructure",
                    "ci_cd_pipeline",
                ],
                "missing_evidence_families": [],
                "deployment_mode": "multi_plane",
                "deployment_planes": [
                    {
                        "name": "gitops_controller_plane",
                        "evidence_families": ["deployment_controller", "gitops_config"],
                    },
                    {
                        "name": "iac_infrastructure_plane",
                        "evidence_families": ["iac_infrastructure"],
                    },
                ],
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

    result = investigation_query.investigate_service(
        object(),
        service_name="api-node-boats",
        environment="bg-qa",
        intent="deployment",
        question="Explain the dual deployment flow.",
    )

    assert result["coverage_summary"]["deployment_mode"] == "multi_plane"

    finished_spans = span_exporter.get_finished_spans()
    investigation_span = next(
        span for span in finished_spans if span.name == "pcg.query.investigate_service"
    )
    attributes = dict(investigation_span.attributes or {})
    assert attributes["pcg.investigation.service_name"] == "api-node-boats"
    assert attributes["pcg.investigation.intent"] == "deployment"
    assert attributes["pcg.investigation.environment"] == "bg-qa"
    assert attributes["pcg.investigation.deployment_mode"] == "multi_plane"
    assert attributes["pcg.investigation.repositories_considered_count"] == 2
    assert attributes["pcg.investigation.repositories_with_evidence_count"] == 1
    assert attributes["pcg.investigation.evidence_families_found_count"] == 5
    assert attributes["pcg.investigation.missing_evidence_families_count"] == 0
    assert (
        attributes["pcg.investigation.evidence_families_found"]
        == "service_runtime,deployment_controller,gitops_config,iac_infrastructure,ci_cd_pipeline"
    )

    points = _metric_points(metric_reader)
    assert any(
        metric_name == "pcg_investigations_total"
        and attrs.get("pcg.investigation.intent") == "deployment"
        and attrs.get("pcg.investigation.deployment_mode") == "multi_plane"
        and attrs.get("pcg.investigation.outcome") == "success"
        for metric_name, attrs, _value in points
    )
    assert any(
        metric_name == "pcg_investigation_duration_seconds"
        and attrs.get("pcg.investigation.intent") == "deployment"
        and attrs.get("pcg.investigation.deployment_mode") == "multi_plane"
        for metric_name, attrs, _value in points
    )
    assert any(
        metric_name == "pcg_investigation_coverage_total"
        and attrs.get("pcg.investigation.intent") == "deployment"
        and attrs.get("pcg.investigation.deployment_mode") == "multi_plane"
        and attrs.get("pcg.investigation.has_missing_evidence") == "false"
        for metric_name, attrs, _value in points
    )
    assert any(
        metric_name == "pcg_investigation_repositories_considered"
        and attrs.get("pcg.investigation.intent") == "deployment"
        and attrs.get("pcg.investigation.deployment_mode") == "multi_plane"
        for metric_name, attrs, _value in points
    )
    assert any(
        metric_name == "pcg_investigation_repositories_with_evidence"
        and attrs.get("pcg.investigation.intent") == "deployment"
        and attrs.get("pcg.investigation.deployment_mode") == "multi_plane"
        for metric_name, attrs, _value in points
    )
