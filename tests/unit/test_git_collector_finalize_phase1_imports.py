"""Phase 1 import compatibility tests for Git finalize helper moves."""

from platform_context_graph.collectors.git.finalize import (
    finalize_index_batch as new_finalize_index_batch,
)
from platform_context_graph.collectors.git.finalize import (
    finalize_single_repository as new_finalize_single_repository,
)
from platform_context_graph.tools.graph_builder_indexing_finalize import (
    finalize_index_batch as legacy_finalize_index_batch,
)
from platform_context_graph.tools.graph_builder_indexing_finalize import (
    finalize_single_repository as legacy_finalize_single_repository,
)


def test_git_finalize_moves_to_collectors_package() -> None:
    """Expose Git finalize helpers from the collectors package."""
    assert new_finalize_index_batch.__module__ == (
        "platform_context_graph.collectors.git.finalize"
    )


def test_legacy_git_finalize_imports_reexport_new_api() -> None:
    """Keep legacy Git finalize imports working during Phase 1."""
    assert legacy_finalize_index_batch is new_finalize_index_batch
    assert legacy_finalize_single_repository is new_finalize_single_repository
