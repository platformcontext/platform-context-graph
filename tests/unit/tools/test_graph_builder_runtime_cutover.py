from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.tools import graph_builder as graph_builder_module


class _DummyDBManager:
    def get_driver(self) -> object:
        return object()


def test_graph_builder_init_does_not_build_parser_registry(monkeypatch) -> None:
    """Normal runtime startup should not eagerly bootstrap Python parsers."""

    monkeypatch.setattr(graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None)

    def _unexpected_build(*_args, **_kwargs):
        raise AssertionError("parser registry should not build during GraphBuilder init")

    monkeypatch.setattr(
        graph_builder_module,
        "_build_parser_registry",
        _unexpected_build,
    )

    builder = graph_builder_module.GraphBuilder(
        _DummyDBManager(),
        SimpleNamespace(),
        asyncio.new_event_loop(),
    )

    assert builder.parsers is None


def test_graph_builder_parse_file_builds_parser_registry_lazily(monkeypatch, tmp_path: Path) -> None:
    """Parser registry bootstrap should happen only when Python parsing is invoked."""

    monkeypatch.setattr(graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None)
    build_calls: list[str] = []

    def _build_registry(_config_getter):
        build_calls.append("built")
        return {".py": object()}

    monkeypatch.setattr(
        graph_builder_module,
        "_build_parser_registry",
        _build_registry,
    )
    monkeypatch.setattr(
        graph_builder_module,
        "_parse_file_impl",
        lambda builder, repo_path, path, is_dependency, **_kwargs: {
            "repo_path": str(repo_path),
            "path": str(path),
            "is_dependency": is_dependency,
            "parser_count": len(builder.parsers or {}),
        },
    )

    builder = graph_builder_module.GraphBuilder(
        _DummyDBManager(),
        SimpleNamespace(),
        asyncio.new_event_loop(),
    )
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    file_path = repo_path / "app.py"
    file_path.write_text("print('hello')\n", encoding="utf-8")

    first = builder.parse_file(repo_path, file_path)
    second = builder.parse_file(repo_path, file_path)

    assert first["parser_count"] == 1
    assert second["parser_count"] == 1
    assert build_calls == ["built"]


def test_collect_supported_files_builds_parser_registry_lazily(monkeypatch, tmp_path: Path) -> None:
    """Single-file discovery should bootstrap the parser registry on demand."""

    monkeypatch.setattr(graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        graph_builder_module,
        "_build_parser_registry",
        lambda _config_getter: {".py": object()},
    )

    builder = graph_builder_module.GraphBuilder(
        _DummyDBManager(),
        SimpleNamespace(),
        asyncio.new_event_loop(),
    )
    file_path = tmp_path / "service.py"
    file_path.write_text("print('ok')\n", encoding="utf-8")

    files = builder._collect_supported_files(file_path)

    assert files == [file_path]
    assert builder.parsers is not None
    assert ".py" in builder.parsers
