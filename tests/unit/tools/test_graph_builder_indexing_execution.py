"""Unit tests for graph-builder indexing execution helpers."""

from __future__ import annotations

from types import SimpleNamespace

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
    assert recorded["infra_links"] == [{"path": "/tmp/example/main.py", "functions": []}]
    assert recorded["workloads"] is True
