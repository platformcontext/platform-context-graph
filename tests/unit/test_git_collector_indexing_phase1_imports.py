"""Phase 1 import compatibility tests for the Git collector indexing move."""

from platform_context_graph.collectors.git.indexing import (
    build_graph_from_path_async as new_build_graph_from_path_async,
)
from platform_context_graph.collectors.git.indexing import (
    collect_supported_files as new_collect_supported_files,
)
from platform_context_graph.tools.graph_builder_indexing import (
    build_graph_from_path_async as legacy_build_graph_from_path_async,
)
from platform_context_graph.tools.graph_builder_indexing import (
    collect_supported_files as legacy_collect_supported_files,
)


def test_git_collector_indexing_moves_to_collectors_package() -> None:
    """Expose Git indexing helpers from the collectors package."""
    assert new_build_graph_from_path_async.__module__ == (
        "platform_context_graph.tools.graph_builder_indexing_execution"
    )


def test_legacy_git_collector_indexing_imports_reexport_new_api() -> None:
    """Keep legacy Git indexing imports working during Phase 1."""
    assert legacy_build_graph_from_path_async is new_build_graph_from_path_async
    assert legacy_collect_supported_files is new_collect_supported_files
