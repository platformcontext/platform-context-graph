"""Tests for independent queue sampling telemetry."""

from __future__ import annotations

from typing import cast

import pytest

from platform_context_graph.facts.work_queue.models import FactWorkQueueSnapshotRow
from platform_context_graph.observability import get_observability
from platform_context_graph.observability import initialize_observability
from platform_context_graph.observability import reset_observability_for_tests
from platform_context_graph.resolution.orchestration import runtime as runtime_mod


def _metric_points(reader) -> list[tuple[str, dict[str, object], object]]:
    """Collect metric points from an in-memory reader."""

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


class _SamplerQueue:
    """Queue stub exposing backlog and pool telemetry refresh hooks."""

    def list_queue_snapshot(self) -> list[FactWorkQueueSnapshotRow]:
        return [
            FactWorkQueueSnapshotRow(
                work_type="project-git-facts",
                status="pending",
                depth=3,
                oldest_age_seconds=42.0,
            )
        ]

    def refresh_pool_metrics(self, *, component: str) -> None:
        get_observability().set_fact_postgres_pool_stats(
            component=component,
            pool_name="fact_queue",
            size=4,
            available=2,
            waiting=1,
        )


def test_run_queue_metrics_sampler_once_emits_queue_and_pool_gauges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Independent queue sampling should emit backlog and pool gauges."""

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

    runtime_mod.run_queue_metrics_sampler_once(queue=_SamplerQueue())

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_fact_queue_depth",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.queue_status": "pending",
        },
    )
    assert _matching_values(
        points,
        "pcg_fact_postgres_pool_size",
        **{"pcg.component": "resolution-engine", "pcg.pool": "fact_queue"},
    )
    assert _matching_values(
        points,
        "pcg_fact_postgres_pool_waiting",
        **{"pcg.component": "resolution-engine", "pcg.pool": "fact_queue"},
    )


def test_run_queue_metrics_sampler_once_emits_skipped_queue_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Independent queue sampling should expose skipped queue status separately."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    class _SkippedQueue:
        def list_queue_snapshot(self) -> list[FactWorkQueueSnapshotRow]:
            return [
                FactWorkQueueSnapshotRow(
                    work_type="project-git-facts",
                    status="skipped",
                    depth=2,
                    oldest_age_seconds=7.0,
                )
            ]

        def refresh_pool_metrics(self, *, component: str) -> None:
            del component

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="resolution-engine",
        metric_reader=metric_reader,
    )

    runtime_mod.run_queue_metrics_sampler_once(queue=_SkippedQueue())

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_fact_queue_depth",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.queue_status": "skipped",
        },
    )


def test_start_resolution_engine_starts_independent_sampler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Resolution Engine should start the independent sampler thread."""

    started: dict[str, bool] = {}

    class _FakeThread:
        def __init__(self, *, target, kwargs, name, daemon) -> None:  # type: ignore[no-untyped-def]
            del target, name, daemon
            self._kwargs = kwargs

        def start(self) -> None:
            started["started"] = True
            runtime_mod.run_queue_metrics_sampler_once(queue=self._kwargs["queue"])

        def join(self, timeout=None) -> None:  # noqa: ANN001
            del timeout
            started["joined"] = True

    monkeypatch.setattr(runtime_mod.threading, "Thread", _FakeThread)
    monkeypatch.setattr(
        runtime_mod,
        "run_resolution_iteration",
        lambda **_kwargs: False,
    )

    with pytest.raises(RuntimeError, match="stop after idle"):
        runtime_mod.start_resolution_engine(
            queue=_SamplerQueue(),
            run_once=False,
            queue_metrics_refresh_seconds=0.1,
            sleep_fn=lambda _seconds: (_ for _ in ()).throw(
                RuntimeError("stop after idle")
            ),
        )

    assert started == {"started": True, "joined": True}
