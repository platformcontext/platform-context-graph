"""Phase 1 import compatibility tests for repository persistence helpers."""

from platform_context_graph.graph.persistence.repositories import (
    add_repository_to_graph as new_add_repository_to_graph,
)
from platform_context_graph.graph.persistence.repositories import (
    read_repository_metadata as new_read_repository_metadata,
)
from platform_context_graph.tools.graph_builder_persistence_helpers import (
    add_repository_to_graph as legacy_add_repository_to_graph,
)
from platform_context_graph.tools.graph_builder_persistence_helpers import (
    read_repository_metadata as legacy_read_repository_metadata,
)


def test_graph_repository_helpers_move_to_graph_persistence_package() -> None:
    """Expose repository helpers from the graph persistence package."""
    assert new_add_repository_to_graph.__module__ == (
        "platform_context_graph.graph.persistence.repositories"
    )


def test_legacy_repository_helper_imports_reexport_new_api() -> None:
    """Keep legacy repository helper imports working during Phase 1."""
    assert legacy_add_repository_to_graph is new_add_repository_to_graph
    assert legacy_read_repository_metadata is new_read_repository_metadata
