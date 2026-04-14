"""Unit tests for direct repository-to-file containment edges."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.graph.persistence.files import add_file_to_graph


class _Result:
    """Minimal Neo4j result stub for repository lookups and writes."""

    def __init__(self, row=None) -> None:
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
        self.repo_row = repo_row
        self.tx = _Tx()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, parameters=None, **kwargs):
        _ = (query, parameters, kwargs)
        return _Result(self.repo_row)

    def begin_transaction(self):
        return self.tx


def _builder_for_repo(repo_path: Path) -> tuple[SimpleNamespace, _Session]:
    """Create a graph builder/session pair for one repository."""

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
    return builder, session


def test_add_file_to_graph_creates_repo_contains_for_nested_files(
    tmp_path, monkeypatch
) -> None:
    """Nested files should get a direct REPO_CONTAINS edge from the repo."""

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    file_path = repo_path / "src" / "routes" / "payments.py"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("def process():\n    return True\n", encoding="utf-8")

    builder, session = _builder_for_repo(repo_path)
    add_file_to_graph(
        builder,
        {
            "path": str(file_path),
            "repo_path": str(repo_path),
            "lang": "python",
            "functions": [],
            "function_calls": [],
        },
        repo_name=repo_path.name,
        imports_map={},
        debug_log_fn=lambda *_args, **_kwargs: None,
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
        content_dual_write_fn=lambda *_args, **_kwargs: None,
    )

    tx_queries = [call[0] for call in session.tx.calls]
    assert any("REPO_CONTAINS" in query for query in tx_queries), tx_queries


def test_add_file_to_graph_creates_repo_contains_for_root_files(
    tmp_path, monkeypatch
) -> None:
    """Root-level files should also get a direct REPO_CONTAINS edge."""

    repo_path = tmp_path / "docs-site"
    repo_path.mkdir()
    file_path = repo_path / "README.md"
    file_path.write_text("# docs\n", encoding="utf-8")

    builder, session = _builder_for_repo(repo_path)
    add_file_to_graph(
        builder,
        {
            "path": str(file_path),
            "repo_path": str(repo_path),
            "lang": "markdown",
            "functions": [],
            "function_calls": [],
        },
        repo_name=repo_path.name,
        imports_map={},
        debug_log_fn=lambda *_args, **_kwargs: None,
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
        content_dual_write_fn=lambda *_args, **_kwargs: None,
    )

    tx_queries = [call[0] for call in session.tx.calls]
    assert any("REPO_CONTAINS" in query for query in tx_queries), tx_queries
