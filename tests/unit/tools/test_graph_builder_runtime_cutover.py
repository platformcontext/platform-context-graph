from __future__ import annotations

# ruff: noqa: E402

import asyncio
from pathlib import Path
from types import SimpleNamespace
from types import ModuleType
import sys


def _install_runtime_shims() -> None:
    roles_module = ModuleType("platform_context_graph.runtime.roles")
    roles_module.get_runtime_role = lambda: "combined"
    roles_module.runtime_supports_mutations = lambda: True
    roles_module.workspace_fallback_enabled = lambda: True
    sys.modules.setdefault("platform_context_graph.runtime.roles", roles_module)

    status_store_module = ModuleType("platform_context_graph.runtime.status_store")
    status_store_module.PostgresRuntimeStatusStore = object
    status_store_module.get_runtime_status_store = lambda: None
    status_store_module.get_repository_coverage = lambda **_kwargs: None
    status_store_module.list_repository_coverage = lambda **_kwargs: []
    status_store_module.request_ingester_reindex = lambda **_kwargs: None
    status_store_module.request_ingester_scan = lambda **_kwargs: None
    sys.modules.setdefault(
        "platform_context_graph.runtime.status_store", status_store_module
    )


_install_runtime_shims()

from platform_context_graph.tools import graph_builder as graph_builder_module


class _DummyDBManager:
    def get_driver(self) -> object:
        return object()


def test_graph_builder_init_does_not_build_parser_registry(monkeypatch) -> None:
    """Normal runtime startup should not retain parser-registry state."""

    monkeypatch.setattr(
        graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None
    )

    builder = graph_builder_module.GraphBuilder(
        _DummyDBManager(),
        SimpleNamespace(),
        asyncio.new_event_loop(),
    )

    assert not hasattr(builder, "parsers")


def test_graph_builder_no_longer_exposes_legacy_python_parse_entrypoint(
    monkeypatch,
) -> None:
    """GraphBuilder should not retain the legacy Python parse-file facade."""

    monkeypatch.setattr(
        graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None
    )

    builder = graph_builder_module.GraphBuilder(
        _DummyDBManager(),
        SimpleNamespace(),
        asyncio.new_event_loop(),
    )

    assert not hasattr(builder, "parse_file")
    assert "TreeSitterParser" not in graph_builder_module.__all__


def test_collect_supported_files_uses_go_aligned_support_without_python_registry(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """File discovery should not need the Python parser registry anymore."""

    monkeypatch.setattr(
        graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None
    )

    builder = graph_builder_module.GraphBuilder(
        _DummyDBManager(),
        SimpleNamespace(),
        asyncio.new_event_loop(),
    )
    python_file = tmp_path / "service.py"
    python_file.write_text("print('ok')\n", encoding="utf-8")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\n", encoding="utf-8")

    files = builder._collect_supported_files(tmp_path)

    assert files == [dockerfile, python_file]
    assert not hasattr(builder, "parsers")
