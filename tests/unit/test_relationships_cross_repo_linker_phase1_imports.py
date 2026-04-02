"""Phase 1 import compatibility tests for cross-repo linker moves."""

from platform_context_graph.relationships.cross_repo_linker import (
    CrossRepoLinker as NewCrossRepoLinker,
)
from platform_context_graph.relationships.cross_repo_linker_support import (
    clean_text as new_clean_text,
)
from platform_context_graph.tools.cross_repo_linker import (
    CrossRepoLinker as LegacyCrossRepoLinker,
)
from platform_context_graph.tools.cross_repo_linker_support import (
    clean_text as legacy_clean_text,
)


def test_cross_repo_linker_moves_to_relationships_package() -> None:
    """Expose the cross-repo linker from the relationships package."""
    assert NewCrossRepoLinker.__module__ == (
        "platform_context_graph.relationships.cross_repo_linker"
    )
    assert new_clean_text.__module__ == (
        "platform_context_graph.relationships.cross_repo_linker_support"
    )


def test_legacy_cross_repo_linker_imports_reexport_new_api() -> None:
    """Keep legacy cross-repo linker imports working during Phase 1."""
    assert LegacyCrossRepoLinker is NewCrossRepoLinker
    assert legacy_clean_text is new_clean_text
