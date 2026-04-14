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

    loop = asyncio.new_event_loop()
    try:
        builder = graph_builder_module.GraphBuilder(
            _DummyDBManager(),
            SimpleNamespace(),
            loop,
        )

        assert not hasattr(builder, "parsers")
    finally:
        loop.close()


def test_graph_builder_no_longer_exposes_legacy_python_parse_entrypoint(
    monkeypatch,
) -> None:
    """GraphBuilder should not retain the legacy Python parse-file facade."""

    monkeypatch.setattr(
        graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None
    )

    loop = asyncio.new_event_loop()
    try:
        builder = graph_builder_module.GraphBuilder(
            _DummyDBManager(),
            SimpleNamespace(),
            loop,
        )

        assert not hasattr(builder, "parse_file")
        assert "TreeSitterParser" not in graph_builder_module.__all__
    finally:
        loop.close()


def test_graph_builder_no_longer_exposes_python_discovery_helpers(
    monkeypatch,
) -> None:
    """GraphBuilder should not keep Python-only discovery convenience helpers."""

    monkeypatch.setattr(
        graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None
    )

    loop = asyncio.new_event_loop()
    try:
        builder = graph_builder_module.GraphBuilder(
            _DummyDBManager(),
            SimpleNamespace(),
            loop,
        )

        assert not hasattr(builder, "parsers")
        assert not hasattr(builder, "_collect_supported_files")
        assert not hasattr(builder, "estimate_processing_time")
    finally:
        loop.close()


def test_graph_builder_no_longer_exposes_dead_python_persistence_facade(
    monkeypatch,
) -> None:
    """GraphBuilder should not retain dead per-file Python persistence helpers."""

    monkeypatch.setattr(
        graph_builder_module, "_create_schema", lambda *_args, **_kwargs: None
    )

    loop = asyncio.new_event_loop()
    try:
        builder = graph_builder_module.GraphBuilder(
            _DummyDBManager(),
            SimpleNamespace(),
            loop,
        )

        assert not hasattr(builder, "add_repository_to_graph")
        assert not hasattr(builder, "add_file_to_graph")
        assert not hasattr(builder, "commit_file_batch_to_graph")
        assert not hasattr(builder, "delete_file_from_graph")
        assert not hasattr(builder, "_safe_run_create")
        assert not hasattr(builder, "_create_function_calls")
        assert not hasattr(builder, "_create_all_function_calls")
        assert not hasattr(builder, "_create_all_infra_links")
        assert not hasattr(builder, "_create_all_sql_relationships")
        assert not hasattr(builder, "_create_inheritance_links")
        assert not hasattr(builder, "_create_csharp_inheritance_and_interfaces")
        assert not hasattr(builder, "_create_all_inheritance_links")
        assert not hasattr(builder, "_name_from_symbol")
    finally:
        loop.close()
