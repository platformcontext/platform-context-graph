"""Unit tests for graph-builder content-store dual writes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.tools.graph_builder_persistence import (
    BatchCommitResult,
    _begin_transaction,
    add_file_to_graph,
    commit_file_batch_to_graph,
)


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
    assert any(
        "uid: row.uid" in query for query in tx_queries
    ), f"Expected uid-based UNWIND merge in tx queries. Got: {tx_queries}"


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
            if (
                "MATCH (r:Repository {path: $repo_path})" in query
                and not self._repo_lookup_done
            ):
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
    entity_calls = [
        call
        for call in tx_calls
        if "UNWIND $rows AS row" in call[0] and "Function" in call[0]
    ]
    assert (
        entity_calls
    ), f"Expected UNWIND Function query in tx calls. Got: {[c[0][:80] for c in tx_calls]}"
    _, params = entity_calls[0]
    rows = params.get("rows", [])
    assert rows, "Expected non-empty rows in UNWIND query"
    assert rows[0]["parameters"] == ["context", "reactInstanceManager"]


def test_commit_file_batch_uses_single_transaction_with_unwind(
    tmp_path, monkeypatch
) -> None:
    """Large tx limits should preserve the single-transaction fast path."""

    repo_path = tmp_path / "batch-repo"
    repo_path.mkdir()
    files = []
    for i in range(3):
        fp = repo_path / "src" / f"mod_{i}.py"
        fp.parent.mkdir(exist_ok=True)
        fp.write_text(f"def func_{i}(): pass\n", encoding="utf-8")
        files.append(
            {
                "path": str(fp),
                "repo_path": str(repo_path),
                "lang": "python",
                "functions": [
                    {"name": f"func_{i}", "line_number": 1, "args": ["x", "y"]}
                ],
                "imports": [{"name": f"os_{i}", "line_number": 1}],
                "function_calls": [],
            }
        )

    repo_row = {
        "id": "repository:r_batch",
        "name": "batch-repo",
        "path": str(repo_path.resolve()),
        "local_path": str(repo_path.resolve()),
        "remote_url": "https://github.com/platformcontext/batch-repo",
        "repo_slug": "platformcontext/batch-repo",
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
            self.committed = False

        def run(self, query, parameters=None, **kwargs):
            merged = dict(parameters or {}, **kwargs)
            self.calls.append((query, merged))
            return _Result()

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

    class _Session:
        def __init__(self) -> None:
            self.tx = _Tx()
            self.begin_transaction_count = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, parameters=None, **kwargs):
            return _Result(repo_row)

        def begin_transaction(self):
            self.begin_transaction_count += 1
            return self.tx

    session = _Session()
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session)),
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.get_postgres_content_provider",
        lambda: None,
    )
    monkeypatch.setenv("PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE", "100")

    commit_file_batch_to_graph(
        builder,
        files,
        Path(repo_path),
        debug_log_fn=lambda *_a, **_kw: None,
        info_logger_fn=lambda *_a, **_kw: None,
        warning_logger_fn=lambda *_a, **_kw: None,
    )

    # Single transaction for the whole batch
    assert session.begin_transaction_count == 1
    assert session.tx.committed

    # UNWIND queries were used for entities and params
    tx_queries = [call[0] for call in session.tx.calls]
    unwind_queries = [q for q in tx_queries if "UNWIND" in q]
    assert len(unwind_queries) >= 2, (
        f"Expected at least 2 UNWIND queries (entities + params). Got {len(unwind_queries)}: "
        f"{[q[:60] for q in unwind_queries]}"
    )
    assert any("Function" in q for q in unwind_queries)
    assert any("Parameter" in q or "HAS_PARAMETER" in q for q in unwind_queries)


def test_commit_file_batch_splits_large_batches_into_multiple_transactions(
    tmp_path, monkeypatch
) -> None:
    """Large coordinator batches should be broken into smaller write transactions."""

    repo_path = tmp_path / "batch-repo"
    repo_path.mkdir()
    files = []
    for i in range(4):
        fp = repo_path / "src" / f"mod_{i}.py"
        fp.parent.mkdir(exist_ok=True)
        fp.write_text(f"def func_{i}(): pass\n", encoding="utf-8")
        files.append(
            {
                "path": str(fp),
                "repo_path": str(repo_path),
                "lang": "python",
                "functions": [{"name": f"func_{i}", "line_number": 1, "args": []}],
                "imports": [],
                "function_calls": [],
            }
        )

    repo_row = {
        "id": "repository:r_batch",
        "name": "batch-repo",
        "path": str(repo_path.resolve()),
        "local_path": str(repo_path.resolve()),
        "remote_url": "https://github.com/platformcontext/batch-repo",
        "repo_slug": "platformcontext/batch-repo",
        "has_remote": True,
    }

    class _Result:
        def __init__(self, row=None) -> None:
            self._row = row

        def single(self):
            if self._row is None:
                return None
            return SimpleNamespace(data=lambda: self._row)

        def consume(self):
            return None

    class _Tx:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []
            self.committed = False

        def run(self, query, parameters=None, **kwargs):
            merged = dict(parameters or {}, **kwargs)
            self.calls.append((query, merged))
            return _Result()

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

    class _Session:
        def __init__(self) -> None:
            self.transactions: list[_Tx] = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, parameters=None, **kwargs):
            _ = dict(parameters or {}, **kwargs)
            return _Result(repo_row)

        def begin_transaction(self):
            tx = _Tx()
            self.transactions.append(tx)
            return tx

    session = _Session()
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session)),
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.get_postgres_content_provider",
        lambda: None,
    )
    monkeypatch.setenv("PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE", "2")

    commit_file_batch_to_graph(
        builder,
        files,
        Path(repo_path),
        debug_log_fn=lambda *_a, **_kw: None,
        info_logger_fn=lambda *_a, **_kw: None,
        warning_logger_fn=lambda *_a, **_kw: None,
    )

    assert len(session.transactions) == 2
    assert all(tx.committed for tx in session.transactions)


def test_commit_file_batch_logs_top_files_for_large_variable_batches(
    tmp_path, monkeypatch
) -> None:
    """Large prepared variable batches should log the heaviest source files."""

    repo_path = tmp_path / "batch-repo"
    repo_path.mkdir()
    files = []
    for name in ("heavy.php", "medium.php", "small.php"):
        file_path = repo_path / "src" / name
        file_path.parent.mkdir(exist_ok=True)
        file_path.write_text("<?php\n", encoding="utf-8")
        files.append(
            {
                "path": str(file_path),
                "repo_path": str(repo_path),
                "lang": "php",
                "functions": [],
                "imports": [],
                "variables": [],
                "function_calls": [],
            }
        )

    repo_row = {
        "id": "repository:r_batch",
        "name": "batch-repo",
        "path": str(repo_path.resolve()),
        "local_path": str(repo_path.resolve()),
        "remote_url": "https://github.com/platformcontext/batch-repo",
        "repo_slug": "platformcontext/batch-repo",
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
            self.committed = False

        def run(self, query, parameters=None, **kwargs):
            merged = dict(parameters or {}, **kwargs)
            self.calls.append((query, merged))
            return _Result()

        def commit(self):
            self.committed = True

        def rollback(self):
            pass

    class _Session:
        def __init__(self) -> None:
            self.tx = _Tx()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, parameters=None, **kwargs):
            return _Result(repo_row)

        def begin_transaction(self):
            return self.tx

    session = _Session()
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session)),
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.get_postgres_content_provider",
        lambda: None,
    )

    def _fake_collect_file_write_data(file_data, file_path_str, **_kwargs):
        if file_path_str.endswith("heavy.php"):
            variable_count = 800
        elif file_path_str.endswith("medium.php"):
            variable_count = 150
        else:
            variable_count = 50
        return {
            "entities_by_label": {
                "Variable": [
                    {
                        "file_path": file_path_str,
                        "name": f"var_{index}",
                        "line_number": index + 1,
                        "uid": f"{Path(file_path_str).name}:{index}",
                        "use_uid_identity": True,
                    }
                    for index in range(variable_count)
                ]
            },
            "params_rows": [],
            "module_rows": [],
            "nested_fn_rows": [],
            "class_fn_rows": [],
            "module_inclusion_rows": [],
            "js_import_rows": [],
            "generic_import_rows": [],
        }

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.collect_file_write_data",
        _fake_collect_file_write_data,
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.flush_write_batches",
        lambda *_args, **_kwargs: {},
    )

    info_logs: list[str] = []
    debug_logs: list[str] = []
    commit_file_batch_to_graph(
        builder,
        files,
        Path(repo_path),
        debug_log_fn=debug_logs.append,
        info_logger_fn=info_logs.append,
        warning_logger_fn=lambda *_a, **_kw: None,
    )

    assert any(
        (
            "Prepared graph entity batch detail" in line
            and "label=Variable" in line
            and "files=3" in line
            and "src/heavy.php(800)" in line
            and "src/medium.php(150)" in line
            and "src/small.php(50)" in line
        )
        for line in debug_logs
    ), debug_logs
    assert not any("Prepared graph entity batch detail" in line for line in info_logs)


def test_begin_transaction_falls_back_when_driver_raises_runtime_error() -> None:
    """Drivers that raise RuntimeError should fall back to session auto-commit."""

    class _Session:
        def begin_transaction(self):
            raise RuntimeError("transactions unsupported")

    session = _Session()

    tx, is_explicit = _begin_transaction(session)

    assert tx is session
    assert is_explicit is False


def test_begin_transaction_falls_back_when_driver_raises_not_implemented() -> None:
    """Drivers that raise NotImplementedError should fall back to auto-commit."""

    class _Session:
        def begin_transaction(self):
            raise NotImplementedError("transactions unsupported")

    session = _Session()

    tx, is_explicit = _begin_transaction(session)

    assert tx is session
    assert is_explicit is False


def test_commit_file_batch_returns_partial_result_after_single_file_fallback(
    tmp_path, monkeypatch
) -> None:
    """Chunk rollback should retry per-file and report committed vs failed paths."""

    repo_path = tmp_path / "batch-repo"
    repo_path.mkdir()
    file_paths = []
    files = []
    for name in ("a.py", "b.py", "c.py"):
        path = repo_path / "src" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"def {path.stem}(): pass\n", encoding="utf-8")
        file_paths.append(str(path.resolve()))
        files.append(
            {
                "path": str(path),
                "repo_path": str(repo_path),
                "lang": "python",
                "functions": [{"name": path.stem, "line_number": 1, "args": []}],
                "imports": [],
                "function_calls": [],
            }
        )

    repo_row = {
        "id": "repository:r_batch",
        "name": "batch-repo",
        "path": str(repo_path.resolve()),
        "local_path": str(repo_path.resolve()),
        "remote_url": "https://github.com/platformcontext/batch-repo",
        "repo_slug": "platformcontext/batch-repo",
        "has_remote": True,
    }

    class _Result:
        def __init__(self, row=None) -> None:
            self._row = row

        def single(self):
            if self._row is None:
                return None
            return SimpleNamespace(data=lambda: self._row)

        def consume(self):
            return None

    class _Tx:
        def __init__(self, failure_suffixes: tuple[str, ...]) -> None:
            self.failure_suffixes = failure_suffixes
            self.committed = False
            self.rolled_back = False

        def run(self, query, parameters=None, **kwargs):
            merged = dict(parameters or {}, **kwargs)
            file_path = merged.get("file_path")
            if isinstance(file_path, str) and file_path.endswith(self.failure_suffixes):
                raise RuntimeError(f"boom:{file_path}")
            return _Result()

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    class _Session:
        def __init__(self) -> None:
            self._transactions = iter(
                [
                    _Tx(("b.py",)),
                    _Tx(()),
                    _Tx(("b.py",)),
                    _Tx(()),
                ]
            )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, query, parameters=None, **kwargs):
            _ = dict(parameters or {}, **kwargs)
            return _Result(repo_row)

        def begin_transaction(self):
            return next(self._transactions)

    session = _Session()
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session)),
    )
    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.get_postgres_content_provider",
        lambda: None,
    )
    monkeypatch.setenv("PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE", "3")

    warnings: list[str] = []
    result = commit_file_batch_to_graph(
        builder,
        files,
        Path(repo_path),
        debug_log_fn=lambda *_a, **_kw: None,
        info_logger_fn=lambda *_a, **_kw: None,
        warning_logger_fn=warnings.append,
    )

    assert result == BatchCommitResult(
        committed_file_paths=(file_paths[0], file_paths[2]),
        failed_file_paths=(file_paths[1],),
    )
    assert any("retrying files individually" in message.lower() for message in warnings)
