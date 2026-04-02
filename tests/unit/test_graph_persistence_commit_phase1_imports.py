"""Phase 1 import-compat tests for graph persistence batch commit helpers."""

from __future__ import annotations

from platform_context_graph.graph.persistence.commit import (
    commit_file_batch_to_graph as canonical_commit_file_batch_to_graph,
)
from platform_context_graph.tools.graph_builder_persistence import (
    commit_file_batch_to_graph,
)


def test_commit_file_batch_to_graph_canonical_module_is_graph_persistence() -> None:
    """Canonical batch commit helper should live under graph.persistence."""

    assert (
        canonical_commit_file_batch_to_graph.__module__
        == "platform_context_graph.graph.persistence.commit"
    )


def test_legacy_commit_file_batch_to_graph_wrapper_remains_callable() -> None:
    """Legacy tools import path should remain available during the transition."""

    assert callable(commit_file_batch_to_graph)
