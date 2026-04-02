"""Phase 1 import compatibility tests for graph persistence result types."""

from platform_context_graph.graph.persistence.types import (
    BatchCommitResult as NewBatchCommitResult,
)
from platform_context_graph.tools.graph_builder_persistence import (
    BatchCommitResult as LegacyBatchCommitResult,
)


def test_graph_persistence_types_move_to_graph_package() -> None:
    """Expose persistence result types from the graph persistence package."""
    assert NewBatchCommitResult.__module__ == (
        "platform_context_graph.graph.persistence.types"
    )


def test_legacy_graph_persistence_type_imports_reexport_new_api() -> None:
    """Keep legacy persistence type imports working during Phase 1."""
    assert LegacyBatchCommitResult is NewBatchCommitResult
