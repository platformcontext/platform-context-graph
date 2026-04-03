"""Tests for file and parsed-entity projection from stored facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.resolution.projection import project_git_fact_records
from platform_context_graph.resolution.projection.entities import (
    project_parsed_entity_facts,
)
from platform_context_graph.resolution.projection.files import project_file_facts


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for projection tests."""

    return datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


@dataclass
class _FakeResult:
    """Minimal result object that supports eager consumption."""

    def consume(self) -> None:
        """Mimic the Neo4j result API used by write helpers."""


class _FakeSession:
    """Capture write queries issued during projection."""

    def __init__(self) -> None:
        """Initialize an empty write log."""

        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> "_FakeSession":
        """Enter the fake session context."""

        return self

    def __exit__(self, *_args: object) -> bool:
        """Exit the fake session context without suppressing errors."""

        return False

    def execute_write(self, write_fn: Any) -> None:
        """Run one managed write callback."""

        write_fn(self)

    def run(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _FakeResult:
        """Record a Cypher write call."""

        params = parameters if parameters is not None else kwargs
        self.calls.append((query, params))
        return _FakeResult()


class _FakeDriver:
    """Expose one reusable fake session via the driver interface."""

    def __init__(self, session: _FakeSession) -> None:
        """Bind the fake driver to one captured session."""

        self._session = session

    def session(self) -> _FakeSession:
        """Return the captured fake session."""

        return self._session


def test_project_git_fact_records_merges_files_and_entities() -> None:
    """File and entity facts should recreate file and CONTAINS graph state."""

    session = _FakeSession()
    builder = type(
        "FakeBuilder",
        (),
        {"driver": _FakeDriver(session)},
    )()
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
            provenance={},
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
            payload={"language": "python", "is_dependency": False},
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        ),
        FactRecordRow(
            fact_id="fact:entity",
            fact_type="ParsedEntityObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={
                "entity_kind": "Function",
                "entity_name": "handler",
                "start_line": 10,
                "end_line": 20,
                "language": "python",
            },
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        ),
    ]
    expected_file_path = str((Path("/tmp/service").resolve() / "src/app.py"))

    project_git_fact_records(builder=builder, fact_records=fact_records)

    assert any(
        "MERGE (f:File {path: $file_path})" in query
        and params["file_path"] == expected_file_path
        and params["relative_path"] == "src/app.py"
        for query, params in session.calls
    )
    assert any(
        "MERGE (r)-[:REPO_CONTAINS]->(f)" in query
        and any(
            row["file_path"] == expected_file_path for row in params.get("rows", [])
        )
        for query, params in session.calls
    )
    assert any(
        "MERGE (n:Function" in query
        and params["name"] == "handler"
        and params["file_path"] == expected_file_path
        and params["line_number"] == 10
        for query, params in session.calls
    )


def test_project_parsed_entity_facts_uses_full_parsed_file_payload_when_available() -> (
    None
):
    """Projection should reuse stored parsed file payloads for rich entity labels."""

    captured: dict[str, Any] = {}
    fact_records = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="github.com/acme/service",
            checkout_path="/tmp/service",
            relative_path="infra/app.yaml",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={
                "language": "yaml",
                "is_dependency": False,
                "parsed_file_data": {
                    "lang": "yaml",
                    "k8s_resources": [
                        {
                            "name": "orders",
                            "line_number": 3,
                            "kind": "Deployment",
                        }
                    ],
                },
            },
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]

    def _collect_file_write_data(
        file_data: dict[str, Any],
        file_path: str,
        *,
        max_entity_value_length: int | None = None,
    ) -> dict[str, Any]:
        captured["file_data"] = file_data
        captured["file_path"] = file_path
        captured["max_entity_value_length"] = max_entity_value_length
        return {
            "entities_by_label": {"K8sResource": [{"name": "orders"}]},
            "params_rows": [],
            "module_rows": [],
            "nested_fn_rows": [],
            "class_fn_rows": [],
            "module_inclusion_rows": [],
            "js_import_rows": [],
            "generic_import_rows": [],
        }

    def _flush_write_batches(
        tx: object,
        write_data: dict[str, Any],
    ) -> dict[str, Any]:
        captured["tx"] = tx
        captured["write_data"] = write_data
        return {"entity:K8sResource": {"total_rows": 1}}

    projected = project_parsed_entity_facts(
        object(),
        fact_records,
        collect_file_write_data_fn=_collect_file_write_data,
        flush_write_batches_fn=_flush_write_batches,
    )

    assert projected == 1
    assert captured["file_path"] == str(Path("/tmp/service/infra/app.yaml"))
    assert captured["file_data"]["k8s_resources"][0]["kind"] == "Deployment"
    assert captured["write_data"]["entities_by_label"]["K8sResource"] == [
        {"name": "orders"}
    ]


def test_project_file_facts_dual_writes_content_for_parsed_file_payload() -> None:
    """File projection should repopulate the content store from stored file facts."""

    captured: dict[str, Any] = {}
    fact_records = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="repository:r_service",
            checkout_path="/tmp/service",
            relative_path="src/app.py",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={
                "language": "python",
                "is_dependency": False,
                "parsed_file_data": {
                    "lang": "python",
                    "path": "/tmp/service/src/app.py",
                    "repo_path": "/tmp/service",
                    "functions": [{"name": "handler", "line_number": 10}],
                },
            },
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]

    def _content_dual_write(
        file_data: dict[str, Any],
        file_name: str,
        repository: dict[str, Any],
        warning_logger_fn: Any,
    ) -> None:
        del warning_logger_fn
        captured["file_data"] = file_data
        captured["file_name"] = file_name
        captured["repository"] = repository

    session = _FakeSession()
    projected = project_file_facts(
        session,
        fact_records,
        content_dual_write_fn=_content_dual_write,
        collect_directory_chain_rows_fn=lambda *_args, **_kwargs: ([], []),
        flush_directory_chain_rows_fn=lambda *_args, **_kwargs: None,
    )

    assert projected == 1
    assert captured["file_name"] == "app.py"
    assert captured["file_data"]["path"] == "/tmp/service/src/app.py"
    assert captured["repository"]["id"] == "repository:r_service"
    assert captured["repository"]["local_path"] == str(Path("/tmp/service").resolve())
