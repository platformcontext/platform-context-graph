"""Phase 1 import compatibility tests for graph entity helper moves."""

from platform_context_graph.graph.persistence.entities import (
    build_entity_merge_statement as new_build_entity_merge_statement,
)
from platform_context_graph.tools.graph_builder_entities import (
    build_entity_merge_statement as legacy_build_entity_merge_statement,
)


def test_graph_entities_move_to_graph_persistence_package() -> None:
    """Expose graph entity helpers from the graph persistence package."""
    assert new_build_entity_merge_statement.__module__ == (
        "platform_context_graph.graph.persistence.entities"
    )


def test_legacy_graph_entities_imports_reexport_new_api() -> None:
    """Keep legacy graph entity helper imports working during Phase 1."""
    assert legacy_build_entity_merge_statement is new_build_entity_merge_statement
