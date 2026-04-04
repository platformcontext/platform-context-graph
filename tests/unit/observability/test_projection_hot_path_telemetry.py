"""Observability coverage for projection and performance hot paths."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import importlib
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock

import pytest

from platform_context_graph.content.models import ContentFileEntry
from platform_context_graph.content.postgres import PostgresContentProvider
from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.graph.persistence.call_prefilter import (
    build_known_callable_names_by_family,
)
from platform_context_graph.graph.persistence.call_row_prep import prepare_call_rows
from platform_context_graph.graph.persistence.inheritance import (
    create_all_inheritance_links,
)
from platform_context_graph.observability import initialize_observability
from platform_context_graph.observability import reset_observability_for_tests
from platform_context_graph.resolution.projection.files import project_file_facts


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for telemetry tests."""

    return datetime(2026, 4, 4, 10, 0, tzinfo=timezone.utc)


def _metric_points(reader: Any) -> list[tuple[str, dict[str, object], object]]:
    """Collect OTEL metric points from an in-memory reader."""

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
    """Return metric values whose name and attributes match."""

    return [
        value
        for metric_name, attrs, value in points
        if metric_name == name
        and all(attrs.get(key) == expected for key, expected in expected_attrs.items())
    ]


class _FakeResult:
    """Minimal result object that supports eager consumption."""

    def consume(self) -> None:
        """Mimic the Neo4j result API used by projection writes."""


class _FakeTx:
    """Capture projection write calls made through a fake transaction."""

    def __init__(self) -> None:
        """Initialize the fake transaction."""

        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        """Record one Cypher write call."""

        params = parameters if parameters is not None else kwargs
        self.calls.append((query, params))
        return _FakeResult()


class _IterableOnlyResult:
    """Expose only iterator semantics to guard against eager `.data()` calls."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        """Store the scan rows."""

        self._rows = rows

    def __iter__(self):
        """Yield the stored rows."""

        return iter(self._rows)

    def data(self) -> list[dict[str, str]]:
        """Fail if a caller tries to materialize all rows eagerly."""

        raise AssertionError("data() should not be called for known-name scans")


class _IterableOnlySession:
    """Return iterable-only results for known-name scans."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        """Store the result rows."""

        self.rows = rows

    def run(
        self,
        _query: str,
        _params: dict[str, object] | None = None,
    ) -> _IterableOnlyResult:
        """Return iterable-only scan results."""

        return _IterableOnlyResult(self.rows)


class _RecordingSession:
    """Capture inheritance write calls."""

    def __init__(self) -> None:
        """Initialize the session recorder."""

        self.calls: list[tuple[str, dict[str, Any]]] = []

    def run(self, query: str, **kwargs: Any) -> None:
        """Record one Cypher write."""

        self.calls.append((query, kwargs))


class _SessionContext:
    """Wrap a recording session in a context manager."""

    def __init__(self, session: _RecordingSession) -> None:
        """Store the recording session."""

        self._session = session

    def __enter__(self) -> _RecordingSession:
        """Return the recording session."""

        return self._session

    def __exit__(self, exc_type, exc, tb) -> None:
        """Do not suppress errors."""

        del exc_type, exc, tb


def test_project_file_facts_emits_batch_metrics_and_span(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File projection should emit hot-path batch metrics and spans."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()
    initialize_observability(
        component="resolution-engine",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    tx = _FakeTx()
    fact_records = [
        FactRecordRow(
            fact_id="fact:file:1",
            fact_type="FileObserved",
            repository_id="repository:r_test",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-1",
            source_snapshot_id="snapshot-1",
            payload={
                "language": "python",
                "parsed_file_data": {
                    "path": "/tmp/service/src/app.py",
                    "repo_path": "/tmp/service",
                    "lang": "python",
                    "functions": [{"name": "handler"}],
                },
            },
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        ),
        FactRecordRow(
            fact_id="fact:file:2",
            fact_type="FileObserved",
            repository_id="repository:r_test",
            checkout_path="/tmp/service",
            relative_path="src/util.py",
            source_system="git",
            source_run_id="run-1",
            source_snapshot_id="snapshot-1",
            payload={
                "language": "python",
                "parsed_file_data": {
                    "path": "/tmp/service/src/util.py",
                    "repo_path": "/tmp/service",
                    "lang": "python",
                    "functions": [{"name": "helper"}],
                },
            },
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        ),
    ]

    project_file_facts(
        tx,
        fact_records,
        content_dual_write_batch_fn=lambda *_args, **_kwargs: None,
        file_batch_size=2,
    )

    points = _metric_points(metric_reader)
    span_names = {span.name for span in span_exporter.get_finished_spans()}

    assert "pcg.resolution.project_file_batch" in span_names
    assert _matching_values(
        points,
        "pcg_resolution_file_projection_batch_duration_seconds",
        **{"pcg.component": "resolution-engine"},
    )
    assert _matching_values(
        points,
        "pcg_resolution_file_projection_batch_files_total",
        **{"pcg.component": "resolution-engine"},
    ) == [2]
    assert _matching_values(
        points,
        "pcg_resolution_directory_flush_rows_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.row_kind": "directory",
        },
    )
    assert _matching_values(
        points,
        "pcg_resolution_directory_flush_rows_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.row_kind": "containment",
        },
    )


def test_postgres_upsert_file_batch_emits_hot_path_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chunked file upserts should emit metrics for batch duration and rows."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()
    initialize_observability(
        component="resolution-engine",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    provider = PostgresContentProvider("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(provider, "_cursor", _cursor)

    provider.upsert_file_batch(
        [
            ContentFileEntry(
                repo_id="repository:r_test",
                relative_path="src/app.py",
                content="print('hello')\n",
                language="python",
                indexed_at=_utc_now(),
            ),
            ContentFileEntry(
                repo_id="repository:r_test",
                relative_path="src/util.py",
                content="print('util')\n",
                language="python",
                indexed_at=_utc_now(),
            ),
        ]
    )

    points = _metric_points(metric_reader)
    span_names = {span.name for span in span_exporter.get_finished_spans()}

    assert "pcg.content.postgres.upsert_file_batch" in span_names
    assert _matching_values(
        points,
        "pcg_content_file_batch_upsert_duration_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.outcome": "success",
        },
    )
    assert _matching_values(
        points,
        "pcg_content_file_batch_upsert_rows_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.outcome": "success",
        },
    ) == [2]


def test_known_name_scan_emits_scan_telemetry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Known-callable scans should emit duration metrics and spans."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()
    initialize_observability(
        component="resolution-engine",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    session = _IterableOnlySession(
        [
            {"name": "render", "lang": "javascript"},
            {"name": "setup", "lang": "typescript"},
        ]
    )

    result = build_known_callable_names_by_family(session)

    points = _metric_points(metric_reader)
    span_names = {span.name for span in span_exporter.get_finished_spans()}

    assert result["javascript"] == frozenset({"render", "setup"})
    assert "pcg.calls.known_name_scan" in span_names
    assert _matching_values(
        points,
        "pcg_call_prefilter_known_name_scan_duration_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.variant": "family",
        },
    )


def test_prepare_call_rows_records_inspected_and_capped_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Call-row prep should expose how many calls were inspected and capped."""

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

    prepare_call_rows(
        {
            "lang": "python",
            "functions": [],
            "classes": [],
            "imports": [],
            "function_calls": [
                {"name": "helper_one", "line_number": 10, "args": []},
                {"name": "helper_two", "line_number": 20, "args": []},
            ],
        },
        {},
        caller_file_path="/tmp/service/src/app.py",
        get_config_value_fn=lambda _key: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
        start_row_id=1,
        max_calls_per_file=1,
    )

    points = _metric_points(metric_reader)

    assert _matching_values(
        points,
        "pcg_call_prep_calls_inspected_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.language": "python",
        },
    ) == [1]
    assert _matching_values(
        points,
        "pcg_call_prep_calls_capped_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.language": "python",
        },
    ) == [1]


def test_inheritance_batches_emit_metrics_and_spans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inheritance batch flushes should emit row and duration telemetry."""

    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    reset_observability_for_tests()
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    metric_reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()
    initialize_observability(
        component="resolution-engine",
        metric_reader=metric_reader,
        span_exporter=span_exporter,
    )

    session = _RecordingSession()
    builder = type(
        "Builder",
        (),
        {
            "driver": type(
                "Driver", (), {"session": lambda self: _SessionContext(session)}
            )()
        },
    )()
    all_file_data = [
        {
            "path": "/tmp/repo/a.py",
            "classes": [{"name": "ChildA", "bases": ["BaseOne"]}],
            "imports": [{"name": "pkg.base_one.BaseOne"}],
        }
    ]
    imports_map = {
        "BaseOne": [str((Path("/tmp/repo/pkg/base_one/BaseOne.py")).resolve())]
    }

    create_all_inheritance_links(builder, all_file_data, imports_map)

    points = _metric_points(metric_reader)
    span_names = {span.name for span in span_exporter.get_finished_spans()}

    assert "pcg.inheritance.flush_batch" in span_names
    assert _matching_values(
        points,
        "pcg_inheritance_batch_duration_seconds",
        **{
            "pcg.component": "resolution-engine",
            "pcg.mode": "inherits",
        },
    )
    assert _matching_values(
        points,
        "pcg_inheritance_batch_rows_total",
        **{
            "pcg.component": "resolution-engine",
            "pcg.mode": "inherits",
        },
    ) == [1]
