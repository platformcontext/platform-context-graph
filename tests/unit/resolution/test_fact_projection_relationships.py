"""Tests for relationship projection from stored facts."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.resolution.projection.relationships import (
    project_relationship_facts,
)


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for projection tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


def test_project_relationship_facts_reuses_existing_graph_relationship_builders() -> (
    None
):
    """Relationship projection should forward fact-derived payloads to graph builders."""

    builder = SimpleNamespace()
    fact_records = [
        FactRecordRow(
            fact_id="fact:repo",
            fact_type="RepositoryObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path=None,
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={"is_dependency": False},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={"imports_map": {"handler": ["/tmp/service/src/app.py"]}},
        ),
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={
                "language": "python",
                "is_dependency": False,
                "parsed_file_data": {
                    "path": "/tmp/service/src/app.py",
                    "repo_path": "/tmp/service",
                    "lang": "python",
                    "imports": [],
                    "classes": [{"name": "Handler", "bases": ["BaseHandler"]}],
                    "function_calls": [
                        {"name": "helper", "line_number": 10, "args": []}
                    ],
                },
            },
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        ),
    ]
    captured: dict[str, object] = {}

    def _create_all_function_calls(
        graph_builder: object,
        all_file_data: list[dict[str, object]],
        imports_map: dict[str, list[str]],
        **_kwargs: object,
    ) -> dict[str, float]:
        captured["calls"] = (graph_builder, all_file_data, imports_map)
        return {"resolved": 1.0}

    def _create_all_inheritance_links(
        graph_builder: object,
        all_file_data: list[dict[str, object]],
        imports_map: dict[str, list[str]],
    ) -> None:
        captured["inheritance"] = (graph_builder, all_file_data, imports_map)

    metrics = project_relationship_facts(
        builder=builder,
        fact_records=fact_records,
        create_all_function_calls_fn=_create_all_function_calls,
        create_all_inheritance_links_fn=_create_all_inheritance_links,
        debug_log_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    assert metrics == {
        "files": 1,
        "imports": 1,
        "call_metrics": {"resolved": 1.0},
    }
    expected_file_data = [dict(fact_records[1].payload["parsed_file_data"])]
    expected_file_data[0]["is_dependency"] = False
    expected_imports_map = {"handler": ["/tmp/service/src/app.py"]}

    assert captured["calls"] == (builder, expected_file_data, expected_imports_map)
    assert captured["inheritance"] == (
        builder,
        expected_file_data,
        expected_imports_map,
    )
