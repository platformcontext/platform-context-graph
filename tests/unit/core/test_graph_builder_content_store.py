"""Unit tests for graph-builder content-store dual writes."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.tools.graph_builder_persistence import add_file_to_graph


def test_add_file_to_graph_dual_writes_content_and_uses_uid_merges(
    tmp_path, monkeypatch
) -> None:
    """Persist file and entity content while merging content-bearing nodes by UID."""

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    file_path = repo_path / "src" / "payments.py"
    file_path.parent.mkdir()
    file_path.write_text(
        "def process_payment():\n    return True\n",
        encoding="utf-8",
    )

    tx = MagicMock()
    session = MagicMock()
    session.__enter__.return_value = session
    session.__exit__.return_value = False
    session.begin_transaction.return_value = tx
    session.run.side_effect = [
        SimpleNamespace(
            single=lambda: SimpleNamespace(
                data=lambda: {
                    "id": "repository:r_ab12cd34",
                    "name": "payments-api",
                    "path": str(repo_path.resolve()),
                    "local_path": str(repo_path.resolve()),
                    "remote_url": "https://github.com/platformcontext/payments-api",
                    "repo_slug": "platformcontext/payments-api",
                    "has_remote": True,
                }
            )
        ),
    ]

    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session)),
        db_manager=SimpleNamespace(get_backend_type=lambda: "neo4j"),
    )
    content_provider = MagicMock(enabled=True)
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.get_postgres_content_provider",
        lambda: content_provider,
    )

    add_file_to_graph(
        builder,
        {
            "path": str(file_path),
            "repo_path": str(repo_path),
            "lang": "python",
            "functions": [
                {
                    "name": "process_payment",
                    "line_number": 1,
                    "end_line": 2,
                    "source": "def process_payment():\n    return True\n",
                    "args": [],
                    "uid": "repository:r_ab12cd34:payments.py:Function:process_payment:1",
                }
            ],
            "function_calls": [],
        },
        repo_name="payments-api",
        imports_map={},
        debug_log_fn=lambda *_args, **_kwargs: None,
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    content_provider.upsert_file.assert_called_once()
    content_provider.upsert_entities.assert_called_once()
    # Entity writes now go through tx.run via UNWIND; check for uid-based merge
    tx_queries = [call.args[0] for call in tx.run.call_args_list]
    assert any("uid: row.uid" in query for query in tx_queries), (
        f"Expected uid-based UNWIND merge in tx queries. Got: {tx_queries}"
    )


def test_add_file_to_graph_passes_reserved_parameter_names_as_mapping(
    tmp_path, monkeypatch
) -> None:
    """Entity payload keys like `parameters` must not collide with Neo4j `run()` args."""

    repo_path = tmp_path / "java-api"
    repo_path.mkdir()
    file_path = repo_path / "src" / "Main.java"
    file_path.parent.mkdir()
    file_path.write_text("class Main {}", encoding="utf-8")

    repo_row = {
        "id": "repository:r_java1234",
        "name": "java-api",
        "path": str(repo_path.resolve()),
        "local_path": str(repo_path.resolve()),
        "remote_url": "https://github.com/platformcontext/java-api",
        "repo_slug": "platformcontext/java-api",
        "has_remote": True,
    }

    class _Result:
        def __init__(self, row=None) -> None:
            self._row = row

        def single(self):
            if self._row is None:
                return None
            return SimpleNamespace(data=lambda: self._row)

    class _Tx:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def run(self, query, parameters=None, **kwargs):
            merged = dict(parameters or {}, **kwargs)
            self.calls.append((query, merged))
            return _Result()

        def commit(self):
            pass

        def rollback(self):
            pass

    class _Session:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []
            self._repo_lookup_done = False
            self.tx = _Tx()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, parameters=None, **kwargs):
            merged = dict(parameters or {}, **kwargs)
            self.calls.append((query, merged))
            if "MATCH (r:Repository {path: $repo_path})" in query and not self._repo_lookup_done:
                self._repo_lookup_done = True
                return _Result(repo_row)
            return _Result()

        def begin_transaction(self):
            return self.tx

    session = _Session()
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
            "lang": "java",
            "functions": [
                {
                    "name": "initializeFlipper",
                    "line_number": 1,
                    "end_line": 2,
                    "parameters": ["context", "reactInstanceManager"],
                    "context": "Main",
                    "class_context": "Main",
                }
            ],
            "function_calls": [],
        },
        repo_name="java-api",
        imports_map={},
        debug_log_fn=lambda *_args, **_kwargs: None,
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=lambda *_args, **_kwargs: None,
    )

    # Entity writes go through tx.run via UNWIND; the rows list contains the entity props.
    tx_calls = session.tx.calls
    entity_calls = [call for call in tx_calls if "UNWIND $rows AS row" in call[0] and "Function" in call[0]]
    assert entity_calls, f"Expected UNWIND Function query in tx calls. Got: {[c[0][:80] for c in tx_calls]}"
    _, params = entity_calls[0]
    rows = params.get("rows", [])
    assert rows, "Expected non-empty rows in UNWIND query"
    assert rows[0]["parameters"] == ["context", "reactInstanceManager"]
