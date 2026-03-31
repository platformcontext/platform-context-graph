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


def test_finalize_index_batch_forwards_workload_progress_details() -> None:
    """Workload-stage progress callbacks should flow through to the caller."""

    progress_events: list[tuple[str, dict[str, object]]] = []

    def _materialize_workloads(
        *,
        committed_repo_paths: list[Path] | None = None,
        progress_callback=None,
    ) -> dict[str, int]:
        assert committed_repo_paths == [Path("/repos/payments-api")]
        assert callable(progress_callback)
        progress_callback(
            status="running",
            operation="gather_completed",
            candidates_processed=1,
            candidates_total=1,
            candidate_repo_count=1,
            targeted_repo_count=1,
        )
        progress_callback(
            status="running",
            operation="cleanup_completed",
            cleanup_pass="instances",
            cleanup_deleted_edges=3,
            cleanup_deleted_nodes=1,
        )
        return {
            "candidate_repo_count": 1,
            "cleanup_deleted_edges": 3,
            "cleanup_deleted_nodes": 1,
            "instances_projected": 2,
            "targeted_repo_count": 1,
            "workloads_projected": 1,
            "write_chunk_count": 4,
        }

    builder = SimpleNamespace(
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_function_calls=lambda *_args, **_kwargs: None,
        _create_all_infra_links=lambda *_args, **_kwargs: None,
        _materialize_workloads=_materialize_workloads,
        _resolve_repository_relationships=lambda *_args, **_kwargs: None,
    )

    finalize_index_batch(
        builder,
        committed_repo_paths=[Path("/repos/payments-api")],
        iter_snapshot_file_data_fn=lambda _path: iter([]),
        merged_imports_map={},
        info_logger_fn=lambda *_args, **_kwargs: None,
        stage_progress_callback=lambda stage, **kwargs: progress_events.append(
            (stage, kwargs)
        ),
        run_id="refinalize-run-456",
        stages=["workloads"],
    )

    assert progress_events[0] == (
        "workloads",
        {
            "status": "started",
            "repo_count": 1,
            "run_id": "refinalize-run-456",
        },
    )
    assert progress_events[1] == (
        "workloads",
        {
            "status": "running",
            "operation": "gather_completed",
            "candidates_processed": 1,
            "candidates_total": 1,
            "candidate_repo_count": 1,
            "targeted_repo_count": 1,
        },
    )
    assert progress_events[2] == (
        "workloads",
        {
            "status": "running",
            "operation": "cleanup_completed",
            "cleanup_pass": "instances",
            "cleanup_deleted_edges": 3,
            "cleanup_deleted_nodes": 1,
        },
    )
    assert progress_events[-1][0] == "workloads"
    assert progress_events[-1][1]["status"] == "completed"
    assert progress_events[-1][1]["workloads_projected"] == 1
    assert progress_events[-1][1]["instances_projected"] == 2
    assert progress_events[-1][1]["cleanup_deleted_edges"] == 3
    assert progress_events[-1][1]["cleanup_deleted_nodes"] == 1
    assert progress_events[-1][1]["write_chunk_count"] == 4


def test_finalize_index_batch_filters_progress_details_for_narrow_callbacks() -> None:
    """Narrow stage callbacks should receive only the keyword subset they accept."""

    progress_events: list[tuple[str, str | None]] = []

    def _materialize_workloads(
        *,
        committed_repo_paths: list[Path] | None = None,
        progress_callback=None,
    ) -> dict[str, int]:
        assert committed_repo_paths == [Path("/repos/payments-api")]
        assert callable(progress_callback)
        progress_callback(
            status="running",
            operation="gather_completed",
            candidates_processed=1,
        )
        return {"workloads_projected": 1}

    builder = SimpleNamespace(
        _create_all_inheritance_links=lambda *_args, **_kwargs: None,
        _create_all_function_calls=lambda *_args, **_kwargs: None,
        _create_all_infra_links=lambda *_args, **_kwargs: None,
        _materialize_workloads=_materialize_workloads,
        _resolve_repository_relationships=lambda *_args, **_kwargs: None,
    )

    def _record_progress(stage: str, status: str | None = None) -> None:
        progress_events.append((stage, status))

    finalize_index_batch(
        builder,
        committed_repo_paths=[Path("/repos/payments-api")],
        iter_snapshot_file_data_fn=lambda _path: iter([]),
        merged_imports_map={},
        info_logger_fn=lambda *_args, **_kwargs: None,
        stage_progress_callback=_record_progress,
        run_id="refinalize-run-789",
        stages=["workloads"],
    )

    assert progress_events == [
        ("workloads", "started"),
        ("workloads", "running"),
        ("workloads", "completed"),
    ]
