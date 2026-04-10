"""Observability coverage for shared-projection backlog telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from platform_context_graph.observability import initialize_observability
from platform_context_graph.observability import reset_observability_for_tests
from platform_context_graph.resolution.orchestration import runtime as runtime_mod


def _metric_points(reader) -> list[tuple[str, dict[str, object], object]]:
    """Collect metric points from an in-memory reader."""

    points: list[tuple[str, dict[str, object], object]] = []
    metrics_data = reader.get_metrics_data()
    if metrics_data is None:
        return points
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


def _matching_values(
    points: list[tuple[str, dict[str, object], object]],
    name: str,
    **expected_attrs: object,
) -> list[object]:
    """Return metric values with matching names and attributes."""

    return [
        value
        for metric_name, attrs, value in points
        if metric_name == name
        and all(attrs.get(key) == expected for key, expected in expected_attrs.items())
    ]


@dataclass(frozen=True, slots=True)
class _SharedBacklogRow:
    """One shared-projection backlog snapshot row for tests."""

    projection_domain: str
    pending_depth: int
    oldest_age_seconds: float


class _SharedProjectionStore:
    """Mutable test double exposing backlog snapshots."""

    def __init__(self, rows: list[_SharedBacklogRow]) -> None:
        """Store the current backlog rows."""

        self.rows = rows

    def list_pending_backlog_snapshot(self) -> list[_SharedBacklogRow]:
        """Return the current backlog snapshot."""

        return list(self.rows)


class _Queue:
    """Minimal queue stub for queue-metrics sampling."""

    def list_queue_snapshot(self) -> list[object]:
        """Return no queue rows for this focused telemetry test."""

        return []

    def refresh_pool_metrics(self, *, component: str) -> None:
        """Ignore pool refreshes for this focused telemetry test."""

        del component


def test_run_queue_metrics_sampler_once_emits_shared_projection_backlog_gauges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared backlog snapshots should surface as bounded domain gauges."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="resolution-engine",
        metric_reader=metric_reader,
    )

    store = _SharedProjectionStore(
        [
            _SharedBacklogRow(
                projection_domain="platform_runtime",
                pending_depth=3,
                oldest_age_seconds=21.0,
            ),
            _SharedBacklogRow(
                projection_domain="workload_dependency",
                pending_depth=1,
                oldest_age_seconds=8.5,
            ),
        ]
    )
    monkeypatch.setattr(
        runtime_mod,
        "get_shared_projection_intent_store",
        lambda: store,
        raising=False,
    )

    runtime_mod.run_queue_metrics_sampler_once(queue=_Queue())

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_shared_projection_pending_intents",
        **{
            "pcg.component": "resolution-engine",
            "pcg.projection_domain": "platform_runtime",
        },
    ) == [3]
    assert _matching_values(
        points,
        "pcg_shared_projection_oldest_pending_age_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.projection_domain": "workload_dependency",
        },
    ) == [8.5]


def test_run_queue_metrics_sampler_once_clears_stale_shared_projection_gauges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty backlog snapshots should remove stale shared-projection gauges."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="resolution-engine",
        metric_reader=metric_reader,
    )

    store = _SharedProjectionStore(
        [
            _SharedBacklogRow(
                projection_domain="platform_runtime",
                pending_depth=2,
                oldest_age_seconds=14.0,
            )
        ]
    )
    monkeypatch.setattr(
        runtime_mod,
        "get_shared_projection_intent_store",
        lambda: store,
        raising=False,
    )

    runtime_mod.run_queue_metrics_sampler_once(queue=_Queue())
    store.rows = []
    runtime_mod.run_queue_metrics_sampler_once(queue=_Queue())

    points = _metric_points(metric_reader)

    assert (
        _matching_values(
            points,
            "pcg_shared_projection_pending_intents",
            **{
                "pcg.component": "resolution-engine",
                "pcg.projection_domain": "platform_runtime",
            },
        )
        == []
    )
    assert (
        _matching_values(
            points,
            "pcg_shared_projection_oldest_pending_age_seconds",
            **{
                "pcg.component": "resolution-engine",
                "pcg.projection_domain": "platform_runtime",
            },
        )
        == []
    )
