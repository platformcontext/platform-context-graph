"""Tests for direct file persistence of framework semantics."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.tools.graph_builder_persistence import add_file_to_graph


class _Result:
    """Minimal Neo4j result stub for repository lookups and writes."""

    def __init__(self, row=None) -> None:
        """Store an optional row payload."""

        self._row = row

    def single(self):
        """Return the configured row wrapped like a Neo4j record."""

        if self._row is None:
            return None
        return SimpleNamespace(data=lambda: self._row)

    def consume(self):
        """Match the eager-consume contract used by write helpers."""

        return None


class _Tx:
    """Record write queries issued inside one transaction."""

    def __init__(self) -> None:
        """Initialize an empty transaction log."""

        self.calls: list[tuple[str, dict[str, object]]] = []

    def run(self, query, parameters=None, **kwargs):
        """Record the query text and merged parameter payload."""

        merged = dict(parameters or {}, **kwargs)
        self.calls.append((query, merged))
        return _Result()

    def commit(self):
        """Satisfy the explicit transaction interface."""

        return None

    def rollback(self):
        """Satisfy the explicit transaction interface."""

        return None


class _Session:
    """Session stub that returns repository metadata and a transaction."""

    def __init__(self, repo_row: dict[str, object]) -> None:
        """Bind repository lookup data and one transaction."""

        self.repo_row = repo_row
        self.tx = _Tx()

    def __enter__(self):
        """Enter the session context."""

        return self

    def __exit__(self, exc_type, exc, tb):
        """Exit without suppressing errors."""

        return False

    def run(self, query, parameters=None, **kwargs):
        """Return the repository metadata lookup row."""

        _ = (query, parameters, kwargs)
        return _Result(self.repo_row)

    def begin_transaction(self):
        """Return the reusable transaction stub."""

        return self.tx


def test_add_file_to_graph_persists_framework_semantics_on_file_nodes(
    tmp_path,
    monkeypatch,
) -> None:
    """Direct graph writes should persist framework facts on the File node."""

    repo_path = tmp_path / "portal-app"
    repo_path.mkdir()
    file_path = repo_path / "app" / "orders" / "page.tsx"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("export default function Page() { return null; }\n")

    repo_row = {
        "id": "repository:r_repo1234",
        "name": repo_path.name,
        "path": str(repo_path.resolve()),
        "local_path": str(repo_path.resolve()),
        "remote_url": f"https://github.com/platformcontext/{repo_path.name}",
        "repo_slug": f"platformcontext/{repo_path.name}",
        "has_remote": True,
    }
    session = _Session(repo_row)
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session)),
        db_manager=SimpleNamespace(get_backend_type=lambda: "neo4j"),
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.get_postgres_content_provider",
        lambda: None,
    )

    add_file_to_graph(
        builder,
        {
            "path": str(file_path),
            "repo_path": str(repo_path),
            "lang": "typescript",
            "functions": [],
            "function_calls": [],
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
            },
        },
        repo_name=repo_path.name,
        imports_map={},
        debug_log_fn=lambda *_args, **_kwargs: None,
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    tx_calls = session.tx.calls
    assert any(
        "MERGE (f:File {path: $file_path})" in query
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
        for query, params in tx_calls
    ), tx_calls
