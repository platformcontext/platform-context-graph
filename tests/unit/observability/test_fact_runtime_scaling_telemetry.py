"""Scaling-oriented telemetry coverage for facts-first runtime components."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import platform_context_graph.facts.storage.postgres as fact_store_mod
import platform_context_graph.facts.work_queue.postgres as fact_queue_mod
from platform_context_graph.facts.storage.postgres import PostgresFactStore
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.facts.work_queue.postgres import PostgresFactWorkQueue
from platform_context_graph.observability import initialize_observability
from platform_context_graph.observability import reset_observability_for_tests
from platform_context_graph.resolution.orchestration.runtime import (
    run_resolution_iteration,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for telemetry tests."""

    return datetime(2026, 4, 3, 11, 0, tzinfo=timezone.utc)


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
                        str(key): value
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


class _RetryQueue:
    """Minimal queue that returns one leased retried work item."""

    def __init__(self, *, attempt_count: int) -> None:
        self._attempt_count = attempt_count
        self.fail_calls: list[tuple[str, str, bool]] = []

    def claim_work_item(
        self,
        *,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        del lease_ttl_seconds
        return FactWorkItemRow(
            work_item_id="work-1",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
            lease_owner=lease_owner,
            lease_expires_at=_utc_now(),
            status="leased",
            attempt_count=self._attempt_count,
            created_at=datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc),
            updated_at=_utc_now(),
        )

    def complete_work_item(self, *, work_item_id: str) -> None:
        raise AssertionError(f"Unexpected completion for {work_item_id}")

    def fail_work_item(
        self,
        *,
        work_item_id: str,
        error_message: str,
        terminal: bool,
    ) -> None:
        self.fail_calls.append((work_item_id, error_message, terminal))

    def list_queue_snapshot(self):  # noqa: ANN202
        return []


def _make_pool_and_cursor():
    """Return a fake psycopg pool, connection, and cursor triple."""

    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=cursor)
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    pool = MagicMock()
    pool.connection.return_value.__enter__ = MagicMock(return_value=conn)
    pool.connection.return_value.__exit__ = MagicMock(return_value=False)
    pool.get_stats.return_value = {
        "pool_size": 4,
        "pool_available": 3,
        "requests_waiting": 1,
    }
    return pool, conn, cursor


def test_resolution_runtime_emits_retry_age_and_dead_letter_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retried work should emit retry-age and dead-letter telemetry."""

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

    queue = _RetryQueue(attempt_count=3)

    processed = run_resolution_iteration(
        queue=queue,
        projector=lambda _row: (_ for _ in ()).throw(RuntimeError("boom")),
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
        max_attempts=3,
    )

    points = _metric_points(metric_reader)

    assert processed is True
    assert queue.fail_calls == [("work-1", "boom", True)]
    assert _matching_values(
        points,
        "pcg_fact_queue_retry_age_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
        },
    )
    assert _matching_values(
        points,
        "pcg_fact_queue_dead_letters_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.error_class": "RuntimeError",
        },
    )
    assert _matching_values(
        points,
        "pcg_fact_queue_dead_letter_age_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
        },
    )


def test_fact_store_pool_acquire_emits_duration_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fact-store pool checkout should emit acquire telemetry."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    initialize_observability(component="ingester", metric_reader=metric_reader)

    pool, conn, _cursor = _make_pool_and_cursor()
    monkeypatch.setattr(fact_store_mod, "_ConnectionPool", MagicMock(return_value=pool))

    store = PostgresFactStore("postgresql://example")
    monkeypatch.setattr(store, "_ensure_schema", lambda _conn: None)

    with store._cursor():
        pass

    points = _metric_points(metric_reader)
    assert conn.cursor.called
    assert _matching_values(
        points,
        "pcg_fact_postgres_pool_acquire_duration_seconds",
        **{
            "pcg.component": "ingester",
            "pcg.pool": "fact_store",
            "pcg.outcome": "success",
        },
    )


def test_fact_queue_pool_acquire_emits_duration_metric(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fact-queue pool checkout should emit acquire telemetry."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    initialize_observability(component="resolution-engine", metric_reader=metric_reader)

    pool, conn, _cursor = _make_pool_and_cursor()
    monkeypatch.setattr(fact_queue_mod, "_ConnectionPool", MagicMock(return_value=pool))

    queue = PostgresFactWorkQueue("postgresql://example")
    monkeypatch.setattr(queue, "_ensure_schema", lambda _conn: None)

    with queue._cursor():
        pass

    points = _metric_points(metric_reader)
    assert conn.cursor.called
    assert _matching_values(
        points,
        "pcg_fact_postgres_pool_acquire_duration_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.pool": "fact_queue",
            "pcg.outcome": "success",
        },
    )
