"""Phase 1 import compatibility tests for Git collector indexing types."""

from platform_context_graph.collectors.git.types import (
    RepositoryParseSnapshot as NewRepositoryParseSnapshot,
)
from platform_context_graph.tools.graph_builder_indexing_types import (
    RepositoryParseSnapshot as LegacyRepositoryParseSnapshot,
)


def test_git_collector_types_move_to_collectors_package() -> None:
    """Expose repository parse snapshot types from the collectors package."""
    assert NewRepositoryParseSnapshot.__module__ == (
        "platform_context_graph.collectors.git.types"
    )


def test_legacy_git_collector_types_reexport_new_api() -> None:
    """Keep legacy Git collector type imports working during Phase 1."""
    assert LegacyRepositoryParseSnapshot is NewRepositoryParseSnapshot
