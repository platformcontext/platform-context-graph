"""Unit tests for batch finalization stage selection and progress callbacks."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.tools.graph_builder_indexing_finalize import (
    finalize_index_batch,
)


def test_finalize_index_batch_filters_to_requested_stages_and_reports_progress() -> None:
    """Requested stages should run in order and emit structured progress details."""

    calls: list[str] = []
    progress_events: list[tuple[str, dict[str, object]]] = []

    builder = SimpleNamespace(
        _create_all_inheritance_links=lambda *_args, **_kwargs: calls.append(
            "inheritance"
        ),
        _create_all_function_calls=lambda *_args, **_kwargs: calls.append(
            "function_calls"
        ),
        _create_all_infra_links=lambda *_args, **_kwargs: calls.append("infra_links"),
        _materialize_workloads=lambda: calls.append("workloads"),
        _resolve_repository_relationships=lambda repo_paths, run_id=None: calls.append(
            f"relationship_resolution:{len(repo_paths)}:{run_id}"
        ),
    )

    timings = finalize_index_batch(
        builder,
        committed_repo_paths=[Path("/repos/payments-api")],
        iter_snapshot_file_data_fn=lambda _path: iter([]),
        merged_imports_map={},
        info_logger_fn=lambda *_args, **_kwargs: None,
        stage_progress_callback=lambda stage, **kwargs: progress_events.append(
            (stage, kwargs)
        ),
        run_id="refinalize-run-123",
        stages=["workloads", "relationship_resolution"],
    )

    assert calls == [
        "workloads",
        "relationship_resolution:1:refinalize-run-123",
    ]
    assert set(timings) == {"workloads", "relationship_resolution"}
    assert progress_events[0] == (
        "workloads",
        {
            "status": "started",
            "repo_count": 1,
            "run_id": "refinalize-run-123",
        },
    )
    assert progress_events[-1][0] == "relationship_resolution"
    assert progress_events[-1][1]["status"] == "completed"
    assert progress_events[-1][1]["run_id"] == "refinalize-run-123"

