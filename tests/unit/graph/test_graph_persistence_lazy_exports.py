"""Tests for lazy graph-persistence package exports."""

from __future__ import annotations

import importlib


def test_graph_persistence_lazy_exports_import_lightweight_helpers() -> None:
    """The package should expose safe helpers without eager heavy imports."""

    module = importlib.import_module("platform_context_graph.graph.persistence")

    assert callable(module.create_all_function_calls)
    assert callable(module.create_all_inheritance_links)
    assert callable(module.collect_directory_chain_rows)
