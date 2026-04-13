from __future__ import annotations

# ruff: noqa: E402

import importlib
import sys
import asyncio
from pathlib import Path
from types import ModuleType


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

import platform_context_graph.tools.graph_builder as graph_builder_module


_SEAM_MODULES = (
    "platform_context_graph.collectors.git.indexing",
    "platform_context_graph.collectors.git.parse_execution",
    "platform_context_graph.parsers.registry",
    "platform_context_graph.parsers.scip",
    "platform_context_graph.parsers.scip.indexing",
    "platform_context_graph.parsers.scip.parser",
)


def _clear_modules() -> None:
    for name in _SEAM_MODULES:
        sys.modules.pop(name, None)


def test_graph_builder_import_does_not_load_legacy_parse_or_scip_modules() -> None:
    """Importing GraphBuilder should not eagerly load Python parse fallback stacks."""

    _clear_modules()
    importlib.reload(graph_builder_module)

    assert "platform_context_graph.collectors.git.parse_execution" not in sys.modules
    assert "platform_context_graph.parsers.registry" not in sys.modules
    assert "platform_context_graph.parsers.scip" not in sys.modules
    assert "platform_context_graph.parsers.scip.indexing" not in sys.modules
    assert "platform_context_graph.parsers.scip.parser" not in sys.modules
    assert not hasattr(graph_builder_module.GraphBuilder, "_build_graph_from_scip")


class _DummyDBManager:
    def get_driver(self) -> object:
        return object()


def test_graph_builder_discovery_paths_do_not_load_legacy_parser_registry(
    monkeypatch, tmp_path: Path
) -> None:
    """Discovery and estimation should stay on Go-owned metadata, not Python parsers."""

    _clear_modules()
    importlib.reload(graph_builder_module)
    monkeypatch.setattr(
        graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None
    )

    builder = graph_builder_module.GraphBuilder(
        _DummyDBManager(),
        object(),
        asyncio.new_event_loop(),
    )
    python_file = tmp_path / "main.py"
    python_file.write_text("print('ok')\n", encoding="utf-8")
    dockerfile = tmp_path / "Dockerfile"
    dockerfile.write_text("FROM python:3.12-slim\n", encoding="utf-8")

    files = builder._collect_supported_files(tmp_path)
    estimate = builder.estimate_processing_time(tmp_path)

    assert files == [dockerfile, python_file]
    assert estimate == (2, 0.1)
    assert "platform_context_graph.parsers.registry" not in sys.modules
