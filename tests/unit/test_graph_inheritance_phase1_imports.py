"""Phase 1 import compatibility tests for inheritance relationship helpers."""

from platform_context_graph.graph.persistence.inheritance import (
    create_all_inheritance_links as new_create_all_inheritance_links,
)
from platform_context_graph.graph.persistence.inheritance import (
    create_csharp_inheritance_and_interfaces as new_create_csharp_inheritance_and_interfaces,
)
from platform_context_graph.graph.persistence.inheritance import (
    create_inheritance_links as new_create_inheritance_links,
)
from platform_context_graph.tools.graph_builder_type_relationships import (
    create_all_inheritance_links as legacy_create_all_inheritance_links,
)
from platform_context_graph.tools.graph_builder_type_relationships import (
    create_csharp_inheritance_and_interfaces as legacy_create_csharp_inheritance_and_interfaces,
)
from platform_context_graph.tools.graph_builder_type_relationships import (
    create_inheritance_links as legacy_create_inheritance_links,
)


def test_inheritance_helpers_move_to_graph_persistence_package() -> None:
    """Expose inheritance helpers from canonical graph persistence modules."""
    assert new_create_inheritance_links.__module__ == (
        "platform_context_graph.graph.persistence.inheritance"
    )
    assert new_create_csharp_inheritance_and_interfaces.__module__ == (
        "platform_context_graph.graph.persistence.inheritance"
    )
    assert new_create_all_inheritance_links.__module__ == (
        "platform_context_graph.graph.persistence.inheritance"
    )


def test_legacy_inheritance_imports_reexport_canonical_api() -> None:
    """Keep legacy inheritance imports working during Phase 1."""
    assert legacy_create_inheritance_links is new_create_inheritance_links
    assert (
        legacy_create_csharp_inheritance_and_interfaces
        is new_create_csharp_inheritance_and_interfaces
    )
    assert legacy_create_all_inheritance_links is new_create_all_inheritance_links
