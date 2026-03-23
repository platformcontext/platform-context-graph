"""Unit tests for graph-builder indexing execution helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from platform_context_graph.tools.graph_builder_indexing_execution import (
    finalize_index_batch,
)
from platform_context_graph.tools.graph_builder_indexing_types import (
    RepositoryParseSnapshot,
)


def test_finalize_index_batch_accepts_snapshot_objects() -> None:
    """Finalize should accept repository snapshot objects without subscripting them."""
    recorded: dict[str, object] = {}

    def _record_inheritance(file_data: object, imports_map: object) -> None:
        recorded["inheritance"] = (file_data, imports_map)

    builder = SimpleNamespace(
        _create_all_inheritance_links=_record_inheritance,
        _create_all_function_calls=lambda file_data, imports_map: recorded.setdefault(
            "function_calls", (file_data, imports_map)
        ),
        _create_all_infra_links=lambda file_data: recorded.setdefault(
            "infra_links", file_data
        ),
        _materialize_workloads=lambda: recorded.setdefault("workloads", True),
    )
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/example",
        file_count=1,
        imports_map={"foo": ["bar"]},
        file_data=[{"path": "/tmp/example/main.py", "functions": []}],
    )

    finalize_index_batch(
        builder,
        snapshots=[snapshot],
        merged_imports_map={"foo": ["bar"]},
        info_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert recorded["inheritance"] == (
        [{"path": "/tmp/example/main.py", "functions": []}],
        {"foo": ["bar"]},
    )
    assert recorded["function_calls"] == (
        [{"path": "/tmp/example/main.py", "functions": []}],
        {"foo": ["bar"]},
    )
    assert recorded["infra_links"] == [
        {"path": "/tmp/example/main.py", "functions": []}
    ]
    assert recorded["workloads"] is True


def test_finalize_index_batch_logs_stage_timings(monkeypatch) -> None:
    """Finalize should emit per-stage timing diagnostics for large repos."""

    messages: list[str] = []
    stages: list[str] = []
    monotonic_values = iter(
        [10.0, 10.0, 11.5, 11.5, 14.0, 14.0, 14.2, 14.2, 15.0, 15.0]
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_indexing_execution.time.monotonic",
        lambda: next(monotonic_values),
    )

    builder = SimpleNamespace(
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_function_calls=lambda *_args, **_kwargs: None,
        _create_all_infra_links=lambda *_args, **_kwargs: None,
        _materialize_workloads=lambda: None,
    )
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/example",
        file_count=1,
        imports_map={},
        file_data=[{"path": "/tmp/example/main.py", "functions": []}],
    )

    stage_timings = finalize_index_batch(
        builder,
        snapshots=[snapshot],
        merged_imports_map={},
        info_logger_fn=messages.append,
        stage_progress_callback=stages.append,
    )

    assert stage_timings == pytest.approx(
        {
            "inheritance": 1.5,
            "function_calls": 2.5,
            "infra_links": 0.2,
            "workloads": 0.8,
        }
    )
    assert stages == [
        "inheritance",
        "function_calls",
        "infra_links",
        "workloads",
    ]
    assert any("Finalization timings:" in message for message in messages)
