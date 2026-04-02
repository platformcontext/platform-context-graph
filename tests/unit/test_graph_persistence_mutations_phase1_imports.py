"""Phase 1 import compatibility tests for the graph mutations package move."""

from platform_context_graph.graph.persistence import (
    delete_file_from_graph as new_delete_file_from_graph,
)
from platform_context_graph.graph.persistence.mutations import (
    delete_repository_from_graph as new_delete_repository_from_graph,
)
from platform_context_graph.graph.persistence.mutations import (
    update_file_in_graph as new_update_file_in_graph,
)
from platform_context_graph.tools.graph_builder_mutations import (
    delete_file_from_graph as legacy_delete_file_from_graph,
)
from platform_context_graph.tools.graph_builder_mutations import (
    delete_repository_from_graph as legacy_delete_repository_from_graph,
)
from platform_context_graph.tools.graph_builder_mutations import (
    update_file_in_graph as legacy_update_file_in_graph,
)


def test_graph_mutations_move_to_graph_persistence_package() -> None:
    """Expose graph mutations from the new graph.persistence package."""
    assert (
        new_delete_repository_from_graph.__module__
        == "platform_context_graph.graph.persistence.mutations"
    )


def test_legacy_graph_mutation_imports_reexport_new_api() -> None:
    """Keep legacy graph mutation imports working during Phase 1."""
    assert legacy_delete_file_from_graph is new_delete_file_from_graph
    assert legacy_delete_repository_from_graph is new_delete_repository_from_graph
    assert legacy_update_file_in_graph is new_update_file_in_graph
