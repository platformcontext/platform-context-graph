"""Phase 1 import-compat tests for graph persistence file helpers."""

from __future__ import annotations

from platform_context_graph.graph.persistence.files import (
    add_file_to_graph as canonical_add_file_to_graph,
)
from platform_context_graph.tools.graph_builder_persistence import add_file_to_graph


def test_add_file_to_graph_canonical_module_is_graph_persistence() -> None:
    """Canonical file-write helper should live under graph.persistence."""

    assert (
        canonical_add_file_to_graph.__module__
        == "platform_context_graph.graph.persistence.files"
    )


def test_legacy_add_file_to_graph_wrapper_remains_callable() -> None:
    """Legacy tools import path should remain available during the transition."""

    assert callable(add_file_to_graph)
