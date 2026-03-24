from __future__ import annotations

import pytest

from platform_context_graph.tools import graph_builder_persistence_unwind


def test_entity_props_for_unwind_caps_oversized_value_preview(monkeypatch) -> None:
    """Oversized entity values should be truncated before they reach Neo4j."""

    monkeypatch.setattr(
        graph_builder_persistence_unwind,
        "get_config_value",
        lambda key: "10" if key == "PCG_MAX_ENTITY_VALUE_LENGTH" else None,
    )

    row = graph_builder_persistence_unwind.entity_props_for_unwind(
        "Variable",
        {
            "name": "buildConfig",
            "line_number": 12,
            "value": "abcdefghijklmnop",
            "source": "full source should stay intact",
            "docstring": "docs should stay intact",
        },
        "/tmp/example.js",
        False,
    )

    assert row["value"] == "abcdefghij [truncated]"
    assert row["source"] == "full source should stay intact"
    assert row["docstring"] == "docs should stay intact"


def test_entity_props_for_unwind_keeps_small_value_preview(monkeypatch) -> None:
    """Short entity values should pass through unchanged."""

    monkeypatch.setattr(
        graph_builder_persistence_unwind,
        "get_config_value",
        lambda key: "20" if key == "PCG_MAX_ENTITY_VALUE_LENGTH" else None,
    )

    row = graph_builder_persistence_unwind.entity_props_for_unwind(
        "Variable",
        {
            "name": "buildConfig",
            "line_number": 12,
            "value": "short-value",
        },
        "/tmp/example.js",
        False,
    )

    assert row["value"] == "short-value"


def test_run_entity_unwind_rejects_invalid_extra_property_keys() -> None:
    """Dynamic Cypher property keys must be validated before interpolation."""

    class _Tx:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def run(self, query: str, **kwargs) -> None:
            self.calls.append((query, kwargs))

    tx = _Tx()

    with pytest.raises(ValueError, match="Invalid Cypher property key"):
        graph_builder_persistence_unwind.run_entity_unwind(
            tx,
            "Function",
            [
                {
                    "file_path": "/tmp/example.py",
                    "name": "handler",
                    "line_number": 12,
                    "bad-key": "boom",
                }
            ],
        )

    assert tx.calls == []


def test_run_entity_unwind_returns_batch_summary(monkeypatch) -> None:
    """Entity unwind should report row counts and elapsed time for diagnostics."""

    class _Tx:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def run(self, query: str, **kwargs) -> None:
            self.calls.append((query, kwargs))

    tx = _Tx()
    perf_counter_values = iter([10.0, 12.5])
    monkeypatch.setattr(
        graph_builder_persistence_unwind.time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )

    summary = graph_builder_persistence_unwind.run_entity_unwind(
        tx,
        "Variable",
        [
            {
                "file_path": "/tmp/example.py",
                "name": "uid-backed",
                "line_number": 1,
                "uid": "var-1",
                "use_uid_identity": True,
            },
            {
                "file_path": "/tmp/example.py",
                "name": "name-backed",
                "line_number": 2,
            },
        ],
    )

    assert summary == pytest.approx(
        {
            "total_rows": 2,
            "uid_rows": 1,
            "name_rows": 1,
            "duration_seconds": 2.5,
        }
    )
    assert len(tx.calls) == 2


def test_run_entity_unwind_optimizes_single_file_chunks() -> None:
    """Single-file chunks should match the containing File node once."""

    class _Tx:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def run(self, query: str, **kwargs) -> None:
            self.calls.append((query, kwargs))

    tx = _Tx()

    graph_builder_persistence_unwind.run_entity_unwind(
        tx,
        "Variable",
        [
            {
                "file_path": "/tmp/example.py",
                "name": "first",
                "line_number": 1,
                "uid": "var-1",
                "use_uid_identity": True,
            },
            {
                "file_path": "/tmp/example.py",
                "name": "second",
                "line_number": 2,
                "uid": "var-2",
                "use_uid_identity": True,
            },
        ],
    )

    assert len(tx.calls) == 1
    query, params = tx.calls[0]
    assert "MATCH (f:File {path: $file_path})" in query
    assert "row.file_path" not in query
    assert params["file_path"] == "/tmp/example.py"
