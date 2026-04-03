"""Phase 1 import compatibility tests for graph persistence unwind helpers."""

from platform_context_graph.graph.persistence.unwind import (
    run_entity_unwind as new_run_entity_unwind,
)
from platform_context_graph.graph.persistence.unwind import (
    validate_cypher_label as new_validate_cypher_label,
)
from platform_context_graph.tools.graph_builder_persistence_unwind import (
    run_entity_unwind as legacy_run_entity_unwind,
)
from platform_context_graph.tools.graph_builder_persistence_unwind import (
    validate_cypher_label as legacy_validate_cypher_label,
)


def test_graph_persistence_unwind_moves_to_graph_package() -> None:
    """Expose unwind helpers from the graph persistence package."""
    assert new_run_entity_unwind.__module__ == (
        "platform_context_graph.graph.persistence.unwind"
    )


def test_legacy_graph_persistence_unwind_imports_reexport_new_api() -> None:
    """Keep legacy unwind imports working during Phase 1."""
    assert legacy_run_entity_unwind is new_run_entity_unwind
    assert legacy_validate_cypher_label is new_validate_cypher_label
