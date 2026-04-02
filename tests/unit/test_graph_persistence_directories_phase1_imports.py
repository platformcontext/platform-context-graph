"""Phase 1 import compatibility tests for directory-chain helper moves."""

from platform_context_graph.graph.persistence.directories import (
    collect_directory_chain_rows as new_collect_directory_chain_rows,
)
from platform_context_graph.graph.persistence.directories import (
    flush_directory_chain_rows as new_flush_directory_chain_rows,
)
from platform_context_graph.graph.persistence.directories import (
    merge_directory_chain as new_merge_directory_chain,
)
from platform_context_graph.tools.graph_builder_directory_chain import (
    collect_directory_chain_rows as legacy_collect_directory_chain_rows,
)
from platform_context_graph.tools.graph_builder_directory_chain import (
    flush_directory_chain_rows as legacy_flush_directory_chain_rows,
)
from platform_context_graph.tools.graph_builder_directory_chain import (
    merge_directory_chain as legacy_merge_directory_chain,
)


def test_graph_directory_helpers_move_to_graph_persistence_package() -> None:
    """Expose directory helpers from the new graph persistence package."""
    assert (
        new_merge_directory_chain.__module__
        == "platform_context_graph.graph.persistence.directories"
    )


def test_legacy_directory_helper_imports_reexport_new_api() -> None:
    """Keep legacy directory helper imports working during Phase 1."""
    assert legacy_merge_directory_chain is new_merge_directory_chain
    assert legacy_collect_directory_chain_rows is new_collect_directory_chain_rows
    assert legacy_flush_directory_chain_rows is new_flush_directory_chain_rows
