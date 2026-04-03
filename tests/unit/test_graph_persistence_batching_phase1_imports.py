"""Phase 1 import compatibility tests for graph persistence batching helpers."""

from platform_context_graph.graph.persistence.batching import (
    collect_file_write_data as new_collect_file_write_data,
)
from platform_context_graph.graph.persistence.batching import (
    flush_write_batches as new_flush_write_batches,
)
from platform_context_graph.tools.graph_builder_persistence_batch import (
    collect_file_write_data as legacy_collect_file_write_data,
)
from platform_context_graph.tools.graph_builder_persistence_batch import (
    flush_write_batches as legacy_flush_write_batches,
)


def test_graph_persistence_batching_moves_to_graph_package() -> None:
    """Expose batching helpers from the graph persistence package."""
    assert new_flush_write_batches.__module__ == (
        "platform_context_graph.graph.persistence.batching"
    )


def test_legacy_graph_persistence_batching_imports_reexport_new_api() -> None:
    """Keep legacy batching imports working during Phase 1."""
    assert legacy_collect_file_write_data is new_collect_file_write_data
    assert legacy_flush_write_batches is new_flush_write_batches
