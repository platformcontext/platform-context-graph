"""Phase 1 import compatibility tests for infrastructure link dispatch."""

from platform_context_graph.relationships.infra_links import (
    create_all_infra_links as new_create_all_infra_links,
)
from platform_context_graph.tools.graph_builder_type_relationships import (
    create_all_infra_links as legacy_create_all_infra_links,
)


def test_infra_link_dispatch_moves_to_relationships_package() -> None:
    """Expose infra-link dispatch from the canonical relationships package."""
    assert new_create_all_infra_links.__module__ == (
        "platform_context_graph.relationships.infra_links"
    )


def test_legacy_infra_link_import_reexports_canonical_api() -> None:
    """Keep legacy infra-link imports working during Phase 1."""
    assert legacy_create_all_infra_links is new_create_all_infra_links
