"""Phase 1 import compatibility tests for the SCIP helper move."""

from platform_context_graph.parsers.scip import (
    build_graph_from_scip as new_build_graph_from_scip,
)
from platform_context_graph.tools.graph_builder_scip import (
    build_graph_from_scip as legacy_build_graph_from_scip,
)


def test_scip_helper_moves_to_parsers_package() -> None:
    """Expose the SCIP entrypoint from the new parsers package."""
    assert new_build_graph_from_scip.__module__ == (
        "platform_context_graph.parsers.scip.indexing"
    )


def test_legacy_scip_import_reexports_new_api() -> None:
    """Keep legacy SCIP imports working during Phase 1."""
    assert legacy_build_graph_from_scip is new_build_graph_from_scip
