"""Phase 1 import checks for the GraphBuilder facade module."""

from __future__ import annotations

import platform_context_graph.tools.graph_builder as graph_builder_module


def test_graph_builder_facade_uses_canonical_collector_execution() -> None:
    """GraphBuilder should import path indexing from the collector package."""

    assert graph_builder_module._build_graph_from_path_async.__module__ == (
        "platform_context_graph.collectors.git.execution"
    )


def test_graph_builder_facade_uses_canonical_graph_persistence() -> None:
    """GraphBuilder should import persistence entrypoints from graph packages."""

    assert graph_builder_module._add_file_to_graph.__module__ == (
        "platform_context_graph.graph.persistence.files"
    )
    assert graph_builder_module._add_repository_to_graph.__module__ == (
        "platform_context_graph.graph.persistence.repositories"
    )
    assert graph_builder_module._commit_file_batch_to_graph.__module__ == (
        "platform_context_graph.graph.persistence.commit"
    )
