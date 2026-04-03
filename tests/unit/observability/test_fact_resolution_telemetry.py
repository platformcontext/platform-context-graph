"""Observability coverage for facts-first emission and resolution runtime paths."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.facts.storage.models import FactRunRow
from platform_context_graph.facts.storage.postgres import PostgresFactStore
from platform_context_graph.facts.work_queue.models import FactWorkItemRow
from platform_context_graph.facts.work_queue.models import FactWorkQueueSnapshotRow
from platform_context_graph.facts.work_queue.postgres import PostgresFactWorkQueue
from platform_context_graph.indexing.coordinator_facts import (
    emit_repository_snapshot_facts,
)
from platform_context_graph.observability import initialize_observability
from platform_context_graph.observability import reset_observability_for_tests
from platform_context_graph.resolution.orchestration.engine import project_work_item
from platform_context_graph.resolution.orchestration.runtime import (
    run_resolution_iteration,
    start_resolution_engine,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for observability tests."""

    return datetime(2026, 4, 3, 10, 0, tzinfo=timezone.utc)


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


class _InMemoryFactStore:
    """Minimal fact store for OTEL coverage tests."""

    enabled = True

    def __init__(self) -> None:
        self.records: list[FactRecordRow] = []

    def upsert_fact_run(self, _entry) -> None:  # type: ignore[no-untyped-def]
        return None

    def upsert_facts(self, entries: list[FactRecordRow]) -> None:
        self.records = list(entries)

    def list_facts(
        self,
        *,
        repository_id: str,
        source_run_id: str,
    ) -> list[FactRecordRow]:
        return [
            record
            for record in self.records
            if record.repository_id == repository_id
            and record.source_run_id == source_run_id
        ]


class _InMemoryWorkQueue:
    """Minimal queue for emission and resolution telemetry tests."""

    enabled = True

    def __init__(self) -> None:
        self.item: FactWorkItemRow | None = None

    def enqueue_work_item(self, entry: FactWorkItemRow) -> None:
        self.item = entry

    def claim_work_item(
        self,
        *,
        lease_owner: str,
        lease_ttl_seconds: int,
    ) -> FactWorkItemRow | None:
        del lease_ttl_seconds
        if self.item is None:
            return None
        self.item = FactWorkItemRow(
            work_item_id=self.item.work_item_id,
            work_type=self.item.work_type,
            repository_id=self.item.repository_id,
            source_run_id=self.item.source_run_id,
            lease_owner=lease_owner,
            lease_expires_at=_utc_now(),
            status="leased",
            attempt_count=1,
            created_at=self.item.created_at,
            updated_at=self.item.updated_at,
        )
        return self.item

    def complete_work_item(self, *, work_item_id: str) -> None:
        assert self.item is not None
        assert self.item.work_item_id == work_item_id

    def fail_work_item(
        self,
        *,
        work_item_id: str,
        error_message: str,
        terminal: bool,
        **_kwargs,
    ) -> None:
        raise AssertionError(
            f"Unexpected fail_work_item({work_item_id}, {error_message}, {terminal})"
        )

    def list_queue_snapshot(self) -> list[FactWorkQueueSnapshotRow]:
        """Return one stable queue snapshot row for gauge coverage tests."""

        return [
            FactWorkQueueSnapshotRow(
                work_type="project-git-facts",
                status="pending",
                depth=1 if self.item is not None else 0,
                oldest_age_seconds=12.0 if self.item is not None else 0.0,
            )
        ]


def test_emit_repository_snapshot_facts_emits_otel_spans_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fact emission should produce spans and metrics for collector observability."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="ingester",
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )

    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=1,
        imports_map={},
        file_data=[
            {
                "path": "/tmp/service/src/app.py",
                "repo_path": "/tmp/service",
                "lang": "python",
                "functions": [{"name": "handler", "line_number": 1}],
            }
        ],
    )

    emit_repository_snapshot_facts(
        source_run_id="run-123",
        repo_path=Path(snapshot.repo_path),
        snapshot=snapshot,
        is_dependency=False,
        fact_store=_InMemoryFactStore(),
        work_queue=_InMemoryWorkQueue(),
        observed_at_fn=_utc_now,
    )

    span_names = {span.name for span in span_exporter.get_finished_spans()}
    points = _metric_points(metric_reader)

    assert "pcg.facts.emit_snapshot" in span_names
    assert _matching_values(
        points,
        "pcg_fact_records_total",
        **{"pcg.component": "ingester", "pcg.source_system": "git"},
    )
    assert _matching_values(
        points,
        "pcg_fact_emission_duration_seconds",
        **{"pcg.component": "ingester", "pcg.source_system": "git"},
    )
    assert _matching_values(
        points,
        "pcg_fact_work_items_total",
        **{
            "pcg.component": "ingester",
            "pcg.work_type": "project-git-facts",
            "pcg.outcome": "enqueued",
        },
    )


def test_resolution_iteration_and_projection_emit_runtime_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolution iteration should emit queue and projection telemetry."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="resolution-engine",
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )

    fact_store = _InMemoryFactStore()
    fact_store.records = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={"language": "python"},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]
    queue = _InMemoryWorkQueue()
    queue.item = FactWorkItemRow(
        work_item_id="work-1",
        work_type="project-git-facts",
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )

    run_resolution_iteration(
        queue=queue,
        projector=lambda row: project_work_item(
            row,
            builder=object(),
            fact_store=fact_store,
            fact_projector=lambda **_kwargs: {"repositories": 1},
            relationship_projector=lambda **_kwargs: {"files": 1},
            workload_projector=lambda **_kwargs: {"workloads_projected": 1},
            platform_projector=lambda **_kwargs: {
                "infrastructure_platform_edges_projected": 1
            },
        ),
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )

    span_names = {span.name for span in span_exporter.get_finished_spans()}
    points = _metric_points(metric_reader)

    assert "pcg.resolution.iteration" in span_names
    assert "pcg.resolution.project_work_item" in span_names
    assert "pcg.resolution.load_facts" in span_names
    assert _matching_values(
        points,
        "pcg_resolution_work_items_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.outcome": "completed",
        },
    )
    assert _matching_values(
        points,
        "pcg_resolution_claim_duration_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.outcome": "claimed",
        },
    )
    assert _matching_values(
        points,
        "pcg_resolution_workers_active",
        **{"pcg.component": "resolution-engine"},
    )
    assert _matching_values(
        points,
        "pcg_resolution_stage_duration_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.stage": "load_facts",
        },
    )
    assert _matching_values(
        points,
        "pcg_resolution_stage_output_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.stage": "project_facts",
        },
    )
    assert _matching_values(
        points,
        "pcg_fact_queue_depth",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.queue_status": "pending",
        },
    )


def test_resolution_stage_failures_emit_error_class_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stage failures should emit low-cardinality error-class counters."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="resolution-engine",
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )

    fact_store = _InMemoryFactStore()
    fact_store.records = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={"language": "python"},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]

    with pytest.raises(RuntimeError, match="stage-boom"):
        project_work_item(
            FactWorkItemRow(
                work_item_id="work-2",
                work_type="project-git-facts",
                repository_id="github.com/acme/service",
                source_run_id="run-123",
            ),
            builder=object(),
            fact_store=fact_store,
            fact_projector=lambda **_kwargs: {"repositories": 1},
            relationship_projector=lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("stage-boom")
            ),
            workload_projector=lambda **_kwargs: {"workloads_projected": 1},
            platform_projector=lambda **_kwargs: {
                "infrastructure_platform_edges_projected": 1
            },
        )

    points = _metric_points(metric_reader)
    assert _matching_values(
        points,
        "pcg_resolution_stage_failures_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.stage": "project_relationships",
            "pcg.error_class": "RuntimeError",
        },
    )


def test_projection_decisions_emit_confidence_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Persisted projection decisions should emit confidence-band metrics."""

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

    fact_store = _InMemoryFactStore()
    fact_store.records = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={"language": "python"},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]
    decision_store = SimpleNamespace(
        upsert_decision=lambda _decision: None,
        insert_evidence=lambda _evidence: None,
    )

    project_work_item(
        FactWorkItemRow(
            work_item_id="work-11",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
        ),
        builder=object(),
        fact_store=fact_store,
        decision_store=decision_store,
        fact_projector=lambda **_kwargs: {"repositories": 1},
        relationship_projector=lambda **_kwargs: {"files": 1},
        workload_projector=lambda **_kwargs: {"workloads_projected": 1},
        platform_projector=lambda **_kwargs: {
            "infrastructure_platform_edges_projected": 1
        },
    )

    points = _metric_points(metric_reader)
    assert _matching_values(
        points,
        "pcg_projection_decisions_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.decision_type": "project_workloads",
            "pcg.confidence_band": "high",
        },
    )
    assert _matching_values(
        points,
        "pcg_projection_confidence_score",
        **{
            "pcg.component": "resolution-engine",
            "pcg.decision_type": "project_platforms",
            "pcg.confidence_band": "high",
        },
    )


def test_resolution_iteration_emits_failure_classification_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Classified failures should emit durable failure-class counters."""

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

    class _FailureQueue:
        def claim_work_item(self, *, lease_owner: str, lease_ttl_seconds: int):
            del lease_ttl_seconds
            return FactWorkItemRow(
                work_item_id="work-12",
                work_type="project-git-facts",
                repository_id="github.com/acme/service",
                source_run_id="run-123",
                lease_owner=lease_owner,
                lease_expires_at=_utc_now(),
                status="leased",
                attempt_count=3,
                created_at=_utc_now(),
                updated_at=_utc_now(),
            )

        def fail_work_item(self, **_kwargs) -> None:
            return None

        def list_queue_snapshot(self):  # noqa: ANN202
            return []

    processed = run_resolution_iteration(
        queue=_FailureQueue(),
        projector=lambda _row: (_ for _ in ()).throw(
            ValueError("invalid fact payload")
        ),
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
        max_attempts=3,
    )

    points = _metric_points(metric_reader)
    assert processed is True
    assert _matching_values(
        points,
        "pcg_resolution_failure_classifications_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.failure_class": "input_invalid",
            "pcg.retry_disposition": "non_retryable",
        },
    )


def test_postgres_fact_store_operations_emit_spans_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Postgres fact-store operations should expose SQL telemetry."""

    pytest.importorskip("opentelemetry.sdk")
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="ingester",
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )

    store = PostgresFactStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "fact_id": "fact:file",
            "fact_type": "FileObserved",
            "repository_id": "github.com/acme/service",
            "checkout_path": "/tmp/service",
            "relative_path": "src/app.py",
            "source_system": "git",
            "source_run_id": "run-123",
            "source_snapshot_id": "snapshot-abc",
            "payload": {"language": "python"},
            "observed_at": _utc_now(),
            "ingested_at": _utc_now(),
            "provenance": {},
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_fact_run(
        FactRunRow(
            source_run_id="run-123",
            source_system="git",
            source_snapshot_id="snapshot-abc",
            repository_id="github.com/acme/service",
            status="pending",
            started_at=_utc_now(),
        )
    )
    store.upsert_facts(
        [
            FactRecordRow(
                fact_id="fact:file",
                fact_type="FileObserved",
                repository_id="github.com/acme/service",
                checkout_path="/tmp/service",
                relative_path="src/app.py",
                source_system="git",
                source_run_id="run-123",
                source_snapshot_id="snapshot-abc",
                payload={"language": "python"},
                observed_at=_utc_now(),
                ingested_at=_utc_now(),
                provenance={},
            )
        ]
    )
    store.list_facts(
        repository_id="github.com/acme/service",
        source_run_id="run-123",
    )

    span_names = {span.name for span in span_exporter.get_finished_spans()}
    points = _metric_points(metric_reader)

    assert "pcg.fact_store.upsert_fact_run" in span_names
    assert "pcg.fact_store.upsert_facts" in span_names
    assert "pcg.fact_store.list_facts" in span_names
    assert _matching_values(
        points,
        "pcg_fact_store_operations_total",
        **{
            "pcg.component": "ingester",
            "pcg.backend": "postgres",
            "pcg.operation": "upsert_facts",
            "pcg.outcome": "success",
        },
    )
    assert _matching_values(
        points,
        "pcg_fact_store_operation_duration_seconds",
        **{
            "pcg.component": "ingester",
            "pcg.backend": "postgres",
            "pcg.operation": "list_facts",
            "pcg.outcome": "success",
        },
    )
    assert _matching_values(
        points,
        "pcg_fact_store_rows_total",
        **{
            "pcg.component": "ingester",
            "pcg.backend": "postgres",
            "pcg.operation": "upsert_facts",
        },
    )


def test_postgres_fact_queue_operations_emit_spans_and_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Postgres fact-queue operations should expose SQL telemetry."""

    pytest.importorskip("opentelemetry.sdk")
    from contextlib import contextmanager
    from unittest.mock import MagicMock

    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="resolution-engine",
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )

    queue = PostgresFactWorkQueue("postgresql://example")
    cursor = MagicMock()
    cursor.fetchone.return_value = {
        "work_item_id": "work-1",
        "work_type": "project-git-facts",
        "repository_id": "github.com/acme/service",
        "source_run_id": "run-123",
        "lease_owner": "resolution-worker-1",
        "lease_expires_at": _utc_now(),
        "status": "leased",
        "attempt_count": 1,
        "last_error": None,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
    }
    cursor.fetchall.return_value = [
        {
            "work_type": "project-git-facts",
            "status": "pending",
            "depth": 2,
            "oldest_age_seconds": 30.0,
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(queue, "_cursor", _cursor)

    queue.enqueue_work_item(
        FactWorkItemRow(
            work_item_id="work-1",
            work_type="project-git-facts",
            repository_id="github.com/acme/service",
            source_run_id="run-123",
            status="pending",
            attempt_count=0,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
    )
    queue.claim_work_item(
        lease_owner="resolution-worker-1",
        lease_ttl_seconds=60,
    )
    queue.complete_work_item(work_item_id="work-1")
    queue.list_queue_snapshot()

    span_names = {span.name for span in span_exporter.get_finished_spans()}
    points = _metric_points(metric_reader)

    assert "pcg.fact_queue.enqueue_work_item" in span_names
    assert "pcg.fact_queue.claim_work_item" in span_names
    assert "pcg.fact_queue.complete_work_item" in span_names
    assert "pcg.fact_queue.list_queue_snapshot" in span_names
    assert _matching_values(
        points,
        "pcg_fact_queue_operations_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.backend": "postgres",
            "pcg.operation": "claim_work_item",
            "pcg.outcome": "success",
        },
    )
    assert _matching_values(
        points,
        "pcg_fact_queue_operation_duration_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.backend": "postgres",
            "pcg.operation": "list_queue_snapshot",
            "pcg.outcome": "success",
        },
    )


def test_resolution_engine_emits_claim_idle_and_stage_failure_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolution-engine runtime should expose worker and stage telemetry."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    span_exporter = InMemorySpanExporter()
    metric_reader = InMemoryMetricReader()
    initialize_observability(
        component="resolution-engine",
        span_exporter=span_exporter,
        metric_reader=metric_reader,
    )

    empty_queue = _InMemoryWorkQueue()
    empty_queue.item = None

    with pytest.raises(RuntimeError, match="stop after idle"):
        start_resolution_engine(
            queue=empty_queue,
            sleep_fn=lambda _seconds: (_ for _ in ()).throw(
                RuntimeError("stop after idle")
            ),
            run_once=False,
        )

    fact_store = _InMemoryFactStore()
    fact_store.records = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={"language": "python"},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]

    with pytest.raises(ValueError, match="bad relationship stage"):
        project_work_item(
            FactWorkItemRow(
                work_item_id="work-99",
                work_type="project-git-facts",
                repository_id="github.com/acme/service",
                source_run_id="run-123",
                attempt_count=1,
            ),
            builder=object(),
            fact_store=fact_store,
            fact_projector=lambda **_kwargs: {"repositories": 1, "files": 1},
            relationship_projector=lambda **_kwargs: (_ for _ in ()).throw(
                ValueError("bad relationship stage")
            ),
            workload_projector=lambda **_kwargs: {"workloads_projected": 1},
            platform_projector=lambda **_kwargs: {
                "infrastructure_platform_edges_projected": 1
            },
        )

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_resolution_claim_duration_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "none",
            "pcg.outcome": "empty",
        },
    )
    assert _matching_values(
        points,
        "pcg_resolution_idle_sleep_seconds",
        **{"pcg.component": "resolution-engine"},
    )
    assert _matching_values(
        points,
        "pcg_resolution_stage_output_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.stage": "project_facts",
        },
    )
    assert _matching_values(
        points,
        "pcg_resolution_stage_failures_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.work_type": "project-git-facts",
            "pcg.stage": "project_relationships",
            "pcg.error_class": "ValueError",
        },
    )
