"""Tests for projecting framework semantics onto File nodes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

from platform_context_graph.facts.storage.models import FactRecordRow
from platform_context_graph.resolution.projection.files import project_file_facts


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for projection tests."""

    return datetime(2026, 4, 8, 12, 0, tzinfo=timezone.utc)


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


def test_project_file_facts_persists_framework_semantics_on_file_nodes() -> None:
    """File projection should keep framework facts on the File node."""

    session = _FakeSession()
    fact_records = [
        FactRecordRow(
            fact_id="fact:file",
            fact_type="FileObserved",
            repository_id="repository:r_service",
            checkout_path="/tmp/service",
            relative_path="app/orders/page.tsx",
            source_system="git",
            source_run_id="run-123",
            source_snapshot_id="snapshot-abc",
            payload={
                "language": "typescript",
                "is_dependency": False,
                "parsed_file_data": {
                    "lang": "typescript",
                    "path": "/tmp/service/app/orders/page.tsx",
                    "repo_path": "/tmp/service",
                    "framework_semantics": {
                        "frameworks": ["nextjs", "react"],
                        "react": {
                            "boundary": "client",
                            "component_exports": ["default"],
                            "hooks_used": ["useState"],
                        },
                        "nextjs": {
                            "module_kind": "page",
                            "route_verbs": [],
                            "metadata_exports": "dynamic",
                            "route_segments": ["orders"],
                            "runtime_boundary": "client",
                            "request_response_apis": ["NextResponse"],
                        },
                        "express": {
                            "route_methods": ["GET"],
                            "route_paths": ["/orders"],
                            "server_symbols": ["router"],
                        },
                        "hapi": {
                            "route_methods": ["POST"],
                            "route_paths": ["/orders/{id}"],
                            "server_symbols": [],
                        },
                    },
                },
            },
            observed_at=_utc_now(),
            ingested_at=_utc_now(),
            provenance={},
        )
    ]

    projected = project_file_facts(
        session,
        fact_records,
        content_dual_write_fn=lambda *_args, **_kwargs: None,
        content_dual_write_batch_fn=lambda *_args, **_kwargs: None,
        collect_directory_chain_rows_fn=lambda *_args, **_kwargs: ([], []),
        flush_directory_chain_rows_fn=lambda *_args, **_kwargs: None,
        file_batch_size=10,
    )

    expected_file_path = str((Path("/tmp/service").resolve() / "app/orders/page.tsx"))

    assert projected == 1
    assert any(
        "MERGE (f:File {path: $file_path})" in query
        and params["file_path"] == expected_file_path
        and params["frameworks"] == ["nextjs", "react"]
        and params["react_boundary"] == "client"
        and params["react_component_exports"] == ["default"]
        and params["react_hooks_used"] == ["useState"]
        and params["next_module_kind"] == "page"
        and params["next_route_verbs"] == []
        and params["next_metadata_exports"] == "dynamic"
        and params["next_route_segments"] == ["orders"]
        and params["next_runtime_boundary"] == "client"
        and params["next_request_response_apis"] == ["NextResponse"]
        and params["express_route_methods"] == ["GET"]
        and params["express_route_paths"] == ["/orders"]
        and params["express_server_symbols"] == ["router"]
        and params["hapi_route_methods"] == ["POST"]
        and params["hapi_route_paths"] == ["/orders/{id}"]
        and params["hapi_server_symbols"] == []
        for query, params in session.calls
    )
