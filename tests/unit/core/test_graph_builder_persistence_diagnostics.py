"""Diagnostics coverage for graph-builder persistence helpers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from platform_context_graph.graph.persistence.files import (
    add_file_to_graph,
)
from platform_context_graph.graph.persistence.repositories import (
    _merge_directory_chain,
)


class _Result:
    def __init__(self, row=None) -> None:
        self._row = row

    def single(self):
        if self._row is None:
            return None
        return SimpleNamespace(data=lambda: self._row)

    def consume(self):
        return None


class _RecordingTx:
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


class _RecordingSession:
    def __init__(self, repo_row: dict[str, object]) -> None:
        self._repo_row = repo_row
        self.tx = _RecordingTx()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, parameters=None, **kwargs):
        _ = dict(parameters or {}, **kwargs)
        return _Result(self._repo_row)

    def begin_transaction(self):
        return self.tx


def test_add_file_to_graph_warns_when_relative_path_falls_back_to_basename(
    tmp_path, monkeypatch
) -> None:
    """Path fallback should emit a warning with both repo and file context."""

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    external_dir = tmp_path / "external"
    external_dir.mkdir()
    file_path = external_dir / "detached.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    repo_row = {
        "id": "repository:r_ab12cd34",
        "name": "payments-api",
        "path": str(repo_path.resolve()),
        "local_path": str(repo_path.resolve()),
        "remote_url": "https://github.com/platformcontext/payments-api",
        "repo_slug": "platformcontext/payments-api",
        "has_remote": True,
    }
    session = _RecordingSession(repo_row)
    builder = SimpleNamespace(
        driver=SimpleNamespace(session=MagicMock(return_value=session)),
    )
    warning_logs: list[str] = []
    add_file_to_graph(
        builder,
        {
            "path": str(file_path),
            "repo_path": str(repo_path),
            "lang": "python",
            "functions": [],
            "function_calls": [],
        },
        repo_name="payments-api",
        imports_map={},
        debug_log_fn=lambda *_args, **_kwargs: None,
        info_logger_fn=lambda *_args, **_kwargs: None,
        warning_logger_fn=warning_logs.append,
        content_dual_write_fn=lambda *_args, **_kwargs: None,
    )

    assert warning_logs
    assert "relative path fallback" in warning_logs[0].lower()
    assert str(repo_path.resolve()) in warning_logs[0]
    assert str(file_path.resolve()) in warning_logs[0]
    file_query_params = session.tx.calls[0][1]
    assert file_query_params["relative_path"] == file_path.name


def test_merge_directory_chain_re_raises_with_directory_context(tmp_path: Path) -> None:
    """Directory merge failures should include the specific directory path."""

    repo_path = tmp_path / "payments-api"
    file_path = repo_path / "src" / "handlers" / "payments.py"

    class _FailingTx:
        def run(self, query, parameters=None, **kwargs):
            merged = dict(parameters or {}, **kwargs)
            if "MERGE (d:Directory" in query:
                raise RuntimeError(f"boom:{merged['current_path']}")
            return _Result()

    with pytest.raises(RuntimeError, match="handlers") as exc_info:
        _merge_directory_chain(
            _FailingTx(),
            file_path,
            repo_path,
            str(file_path),
        )

    assert str(file_path) in str(exc_info.value)
