from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.tools.graph_builder_persistence import (
    commit_file_batch_to_graph,
)


def test_commit_file_batch_to_graph_flushes_incrementally_when_buffer_grows(
    monkeypatch,
) -> None:
    """Large repo batches should flush mid-transaction to cap peak memory."""

    repo_path = "/repo"
    files = [
        {
            "path": f"{repo_path}/src/file_{index}.php",
            "repo_path": repo_path,
            "lang": "php",
            "functions": [],
            "imports": [],
        }
        for index in range(3)
    ]
    repo_row = {
        "id": "repository:r_test",
        "name": "repo",
        "path": repo_path,
        "local_path": repo_path,
        "remote_url": "https://github.com/example/repo",
        "repo_slug": "example/repo",
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
            self.committed = False

        def run(self, _query, parameters=None, **kwargs):
            _ = dict(parameters or {}, **kwargs)
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

        def run(self, _query, parameters=None, **kwargs):
            _ = dict(parameters or {}, **kwargs)
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
        return {
            "entities_by_label": {
                "Variable": [
                    {
                        "file_path": file_path_str,
                        "name": f"{Path(file_data['path']).name}:{index}",
                        "line_number": index + 1,
                        "uid": f"{Path(file_data['path']).name}:{index}",
                        "use_uid_identity": True,
                    }
                    for index in range(2)
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
        "platform_context_graph.tools.graph_builder_persistence_batch._WRITE_BATCH_FLUSH_ROW_THRESHOLD",
        3,
    )

    observed_flush_sizes: list[int] = []

    def _fake_flush_write_batches(_tx, batches, **_kwargs):
        observed_flush_sizes.append(len(batches["entities_by_label"]["Variable"]))
        return {}

    monkeypatch.setattr(
        "platform_context_graph.tools.graph_builder_persistence.flush_write_batches",
        _fake_flush_write_batches,
    )

    commit_file_batch_to_graph(
        builder,
        files,
        Path(repo_path),
        debug_log_fn=lambda *_a, **_kw: None,
        info_logger_fn=lambda *_a, **_kw: None,
        warning_logger_fn=lambda *_a, **_kw: None,
    )

    assert observed_flush_sizes == [4, 2]
    assert session.tx.committed is True
