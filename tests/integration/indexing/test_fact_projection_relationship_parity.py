"""Integration test for reconstructing relationship inputs from emitted facts."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.collectors.git.types import RepositoryParseSnapshot
from platform_context_graph.facts.emission.git_snapshot import emit_git_snapshot_facts
from platform_context_graph.resolution.projection.relationships import (
    project_git_relationship_fact_records,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for projection tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_emitted_git_facts_preserve_relationship_projection_inputs() -> None:
    """Snapshot facts should reconstruct the same relationship inputs later."""

    fact_store = MagicMock()
    work_queue = MagicMock()
    snapshot = RepositoryParseSnapshot(
        repo_path="/tmp/service",
        file_count=1,
        imports_map={"Base": ["/tmp/service/src/base.py"]},
        file_data=[
            {
                "path": "/tmp/service/src/app.py",
                "repo_path": "/tmp/service",
                "lang": "python",
                "imports": [{"name": "base.Base", "alias": "Base"}],
                "classes": [
                    {
                        "name": "Child",
                        "line_number": 5,
                        "bases": ["Base"],
                    }
                ],
                "function_calls": [
                    {
                        "caller": "handler",
                        "name": "helper",
                        "line_number": 12,
                    }
                ],
            }
        ],
    )

    emit_git_snapshot_facts(
        snapshot=snapshot,
        repository_id="github.com/acme/service",
        source_run_id="run-123",
        source_snapshot_id="snapshot-abc",
        is_dependency=False,
        fact_store=fact_store,
        work_queue=work_queue,
        observed_at=_utc_now(),
    )
    fact_records = fact_store.upsert_facts.call_args.args[0]
    captured: dict[str, object] = {}

    def _capture_calls(builder, all_file_data, imports_map, **kwargs):  # type: ignore[no-untyped-def]
        captured["calls_builder"] = builder
        captured["calls_files"] = all_file_data
        captured["calls_imports"] = imports_map
        captured["calls_kwargs"] = kwargs
        return {"total_rows": 1}

    def _capture_inheritance(builder, all_file_data, imports_map):  # type: ignore[no-untyped-def]
        captured["inheritance_builder"] = builder
        captured["inheritance_files"] = all_file_data
        captured["inheritance_imports"] = imports_map

    metrics = project_git_relationship_fact_records(
        builder=SimpleNamespace(driver=object()),
        fact_records=fact_records,
        create_all_function_calls_fn=_capture_calls,
        create_all_inheritance_links_fn=_capture_inheritance,
        debug_log_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    rebuilt_file = captured["calls_files"][0]
    assert metrics["files"] == 1
    assert rebuilt_file["function_calls"][0]["name"] == "helper"
    assert rebuilt_file["classes"][0]["name"] == "Child"
    assert captured["calls_imports"] == {"Base": ["/tmp/service/src/base.py"]}
