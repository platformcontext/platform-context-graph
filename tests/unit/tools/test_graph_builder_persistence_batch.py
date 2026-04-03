from __future__ import annotations

from pathlib import Path

from platform_context_graph.graph.persistence import (
    batching as graph_builder_persistence_batch,
)


def test_flush_write_batches_chunks_variable_rows(monkeypatch) -> None:
    """Variable rows should flush in smaller internal chunks."""

    observed_chunk_sizes: list[int] = []
    info_lines: list[str] = []
    debug_lines: list[str] = []

    def _fake_run_entity_unwind(_tx, label: str, rows: list[dict[str, object]]):
        observed_chunk_sizes.append(len(rows))
        return {
            "total_rows": len(rows),
            "uid_rows": len(rows),
            "name_rows": 0,
            "duration_seconds": 0.25,
        }

    monkeypatch.setattr(
        graph_builder_persistence_batch,
        "run_entity_unwind",
        _fake_run_entity_unwind,
    )
    monkeypatch.setattr(
        graph_builder_persistence_batch,
        "debug_logger",
        debug_lines.append,
        raising=False,
    )

    rows = [
        {
            "file_path": "/tmp/example.py",
            "name": f"var_{index}",
            "line_number": index,
            "uid": f"var-{index}",
            "use_uid_identity": True,
        }
        for index in range(501)
    ]

    metrics = graph_builder_persistence_batch.flush_write_batches(
        object(),
        {
            "entities_by_label": {"Variable": rows},
            "params_rows": [],
            "module_rows": [],
            "nested_fn_rows": [],
            "class_fn_rows": [],
            "module_inclusion_rows": [],
            "js_import_rows": [],
            "generic_import_rows": [],
        },
        info_logger_fn=info_lines.append,
        debug_logger_fn=debug_lines.append,
    )

    assert observed_chunk_sizes == [100, 100, 100, 100, 100, 1]
    assert metrics["entity:Variable"] == {
        "total_rows": 501,
        "uid_rows": 501,
        "name_rows": 0,
        "duration_seconds": 1.5,
        "chunk_count": 6,
        "max_chunk_rows": 100,
    }
    assert debug_lines == [
        "Graph write batch entity start label=Variable chunk=1/6 rows=100",
        "Graph write batch entity done label=Variable chunk=1/6 rows=100 duration=0.25s",
        "Graph write batch entity start label=Variable chunk=2/6 rows=100",
        "Graph write batch entity done label=Variable chunk=2/6 rows=100 duration=0.25s",
        "Graph write batch entity start label=Variable chunk=3/6 rows=100",
        "Graph write batch entity done label=Variable chunk=3/6 rows=100 duration=0.25s",
        "Graph write batch entity start label=Variable chunk=4/6 rows=100",
        "Graph write batch entity done label=Variable chunk=4/6 rows=100 duration=0.25s",
        "Graph write batch entity start label=Variable chunk=5/6 rows=100",
        "Graph write batch entity done label=Variable chunk=5/6 rows=100 duration=0.25s",
        "Graph write batch entity start label=Variable chunk=6/6 rows=1",
        "Graph write batch entity done label=Variable chunk=6/6 rows=1 duration=0.25s",
        "Graph write batch entity label=Variable rows=501 uid_rows=501 name_rows=0 chunks=6 max_chunk_rows=100 duration=1.50s",
    ]
    assert info_lines == []


def test_flush_write_batches_keeps_non_variable_rows_in_one_chunk(
    monkeypatch,
) -> None:
    """Non-variable labels should keep the current single-query behavior."""

    observed_chunk_sizes: list[tuple[str, int]] = []

    def _fake_run_entity_unwind(_tx, label: str, rows: list[dict[str, object]]):
        observed_chunk_sizes.append((label, len(rows)))
        return {
            "total_rows": len(rows),
            "uid_rows": 0,
            "name_rows": len(rows),
            "duration_seconds": 0.1,
        }

    monkeypatch.setattr(
        graph_builder_persistence_batch,
        "run_entity_unwind",
        _fake_run_entity_unwind,
    )

    rows = [
        {
            "file_path": "/tmp/example.py",
            "name": f"func_{index}",
            "line_number": index,
        }
        for index in range(600)
    ]

    metrics = graph_builder_persistence_batch.flush_write_batches(
        object(),
        {
            "entities_by_label": {"Function": rows},
            "params_rows": [],
            "module_rows": [],
            "nested_fn_rows": [],
            "class_fn_rows": [],
            "module_inclusion_rows": [],
            "js_import_rows": [],
            "generic_import_rows": [],
        },
    )

    assert observed_chunk_sizes == [("Function", 600)]
    assert metrics["entity:Function"] == {
        "total_rows": 600,
        "uid_rows": 0,
        "name_rows": 600,
        "duration_seconds": 0.1,
        "chunk_count": 1,
        "max_chunk_rows": 600,
    }


def test_flush_write_batches_logs_non_entity_summaries_at_debug_only(
    monkeypatch,
) -> None:
    """Non-entity batch summaries should not emit through the info logger."""

    debug_lines: list[str] = []
    info_lines: list[str] = []

    monkeypatch.setattr(
        graph_builder_persistence_batch,
        "run_parameter_unwind",
        lambda *_args, **_kwargs: None,
    )

    metrics = graph_builder_persistence_batch.flush_write_batches(
        object(),
        {
            "entities_by_label": {},
            "params_rows": [{"name": "foo"} for _ in range(4)],
            "module_rows": [],
            "nested_fn_rows": [],
            "class_fn_rows": [],
            "module_inclusion_rows": [],
            "js_import_rows": [],
            "generic_import_rows": [],
        },
        info_logger_fn=info_lines.append,
        debug_logger_fn=debug_lines.append,
    )

    assert metrics["parameters"]["rows"] == 4
    assert info_lines == []
    assert debug_lines == ["Graph write batch type=parameters rows=4 duration=0.00s"]


def test_summarize_entity_source_files_uses_repo_relative_top_files() -> None:
    """Large label summaries should identify their heaviest source files."""

    repo_root = Path("/repo")
    rows = (
        [
            {"file_path": str(repo_root / "src" / "heavy.php"), "uid": f"heavy-{index}"}
            for index in range(5)
        ]
        + [
            {
                "file_path": str(repo_root / "src" / "medium.php"),
                "uid": f"medium-{index}",
            }
            for index in range(3)
        ]
        + [{"file_path": str(repo_root / "vendor" / "small.php"), "uid": "small-1"}]
    )

    summary = graph_builder_persistence_batch.summarize_entity_source_files(
        rows,
        repo_root=repo_root,
        limit=2,
    )

    assert summary == {
        "file_count": 3,
        "top_files": [("src/heavy.php", 5), ("src/medium.php", 3)],
    }
