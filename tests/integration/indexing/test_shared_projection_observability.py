"""Integration checks for shared-projection backlog observability."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import cast

import pytest

from platform_context_graph.observability import initialize_observability
from platform_context_graph.observability import reset_observability_for_tests
from platform_context_graph.resolution.orchestration import runtime as runtime_mod
from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionBacklogSnapshotRow,
)
from platform_context_graph.resolution.shared_projection.models import (
    SharedProjectionIntentRow,
)
from platform_context_graph.resolution.shared_projection.models import (
    build_shared_projection_intent,
)
from platform_context_graph.resolution.shared_projection.runtime import (
    process_dependency_partition_once,
)


def _utc_now(minute: int = 0) -> datetime:
    """Return a stable UTC timestamp for shared-projection telemetry tests."""

    return datetime(2026, 4, 10, 10, minute, tzinfo=timezone.utc)


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


class _InMemorySharedIntentStore:
    """In-memory shared intent store for telemetry convergence tests."""

    def __init__(self, rows: list[SharedProjectionIntentRow]) -> None:
        self.rows = list(rows)
        self.completed_ids: list[str] = []

    def claim_partition_lease(self, **_kwargs: object) -> bool:
        return True

    def release_partition_lease(self, **_kwargs: object) -> None:
        return None

    def list_pending_domain_intents(
        self,
        *,
        projection_domain: str,
        limit: int = 100,
    ) -> list[SharedProjectionIntentRow]:
        return [
            row
            for row in self.rows
            if row.projection_domain == projection_domain
            and row.completed_at is None
            and row.intent_id not in self.completed_ids
        ][:limit]

    def mark_intents_completed(self, *, intent_ids: list[str]) -> None:
        self.completed_ids.extend(intent_ids)

    def count_pending_repository_generation_intents(
        self,
        *,
        repository_id: str,
        source_run_id: str,
        generation_id: str,
        projection_domain: str,
    ) -> int:
        return sum(
            1
            for row in self.rows
            if row.intent_id not in self.completed_ids
            and row.repository_id == repository_id
            and row.source_run_id == source_run_id
            and row.generation_id == generation_id
            and row.projection_domain == projection_domain
        )

    def list_pending_backlog_snapshot(self) -> list[SharedProjectionBacklogSnapshotRow]:
        pending_by_domain: dict[str, int] = {}
        oldest_by_domain: dict[str, float] = {}
        now = _utc_now(10)
        for row in self.rows:
            if row.completed_at is not None or row.intent_id in self.completed_ids:
                continue
            pending_by_domain[row.projection_domain] = (
                pending_by_domain.get(row.projection_domain, 0) + 1
            )
            age_seconds = max((now - row.created_at).total_seconds(), 0.0)
            current_oldest = oldest_by_domain.get(row.projection_domain, 0.0)
            oldest_by_domain[row.projection_domain] = max(current_oldest, age_seconds)
        return [
            SharedProjectionBacklogSnapshotRow(
                projection_domain=projection_domain,
                pending_depth=pending_depth,
                oldest_age_seconds=oldest_by_domain.get(projection_domain, 0.0),
            )
            for projection_domain, pending_depth in sorted(pending_by_domain.items())
        ]


class _Queue:
    """Queue stub for dependency shared-followup telemetry tests."""

    def __init__(self, shared_store: _InMemorySharedIntentStore) -> None:
        self.shared_store = shared_store

    def list_queue_snapshot(self) -> list[object]:
        return []

    def refresh_pool_metrics(self, *, component: str) -> None:
        del component

    def list_shared_projection_acceptances(
        self,
        *,
        projection_domain: str,
        repository_ids: list[str] | None = None,
    ) -> dict[tuple[str, str], str]:
        del projection_domain
        del repository_ids
        return {("repository:r_payments", "run-123"): "snapshot-abc"}

    def complete_shared_projection_domain_by_generation(self, **_kwargs: object) -> None:
        return None

    def list_shared_projection_backlog_snapshot(
        self,
    ) -> list[SharedProjectionBacklogSnapshotRow]:
        return self.shared_store.list_pending_backlog_snapshot()


def test_shared_projection_backlog_metrics_return_to_zero_after_dependency_followup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared backlog gauges should clear once authoritative follow-up drains."""

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

    store = _InMemorySharedIntentStore(
        [
            build_shared_projection_intent(
                projection_domain="repo_dependency",
                partition_key="repo:repository:r_payments->repository:r_users",
                repository_id="repository:r_payments",
                source_run_id="run-123",
                generation_id="snapshot-abc",
                payload={
                    "action": "upsert",
                    "dependency_name": "users",
                    "repo_id": "repository:r_payments",
                    "target_repo_id": "repository:r_users",
                },
                created_at=_utc_now(),
            )
        ]
    )
    queue = _Queue(store)
    monkeypatch.setattr(
        runtime_mod,
        "get_shared_projection_intent_store",
        lambda: None,
        raising=False,
    )

    runtime_mod.run_queue_metrics_sampler_once(queue=queue)
    before_points = _metric_points(metric_reader)

    session = cast(object, type("Session", (), {"run": lambda self, query, **params: []})())
    process_dependency_partition_once(
        session,
        shared_projection_intent_store=store,
        fact_work_queue=queue,
        projection_domain="repo_dependency",
        partition_id=0,
        partition_count=1,
        lease_owner="worker-1",
        lease_ttl_seconds=60,
    )
    runtime_mod.run_queue_metrics_sampler_once(queue=queue)
    after_points = _metric_points(metric_reader)

    assert _matching_values(
        before_points,
        "pcg_shared_projection_pending_intents",
        **{
            "pcg.component": "resolution-engine",
            "pcg.projection_domain": "repo_dependency",
        },
    ) == [1]
    assert _matching_values(
        after_points,
        "pcg_shared_projection_pending_intents",
        **{
            "pcg.component": "resolution-engine",
            "pcg.projection_domain": "repo_dependency",
        },
    ) == []
