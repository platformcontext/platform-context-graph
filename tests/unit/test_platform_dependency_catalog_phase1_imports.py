"""Phase 1 import compatibility tests for dependency catalog helpers."""

from platform_context_graph.platform.dependency_catalog import (
    dependency_ignore_enabled as new_dependency_ignore_enabled,
)
from platform_context_graph.platform.dependency_catalog import (
    dependency_root_sequences as new_dependency_root_sequences,
)
from platform_context_graph.platform.dependency_catalog import (
    dependency_roots_by_ecosystem as new_dependency_roots_by_ecosystem,
)
from platform_context_graph.platform.dependency_catalog import (
    is_dependency_path as new_is_dependency_path,
)
from platform_context_graph.tools.dependency_catalog import (
    dependency_ignore_enabled as legacy_dependency_ignore_enabled,
)
from platform_context_graph.tools.dependency_catalog import (
    dependency_root_sequences as legacy_dependency_root_sequences,
)
from platform_context_graph.tools.dependency_catalog import (
    dependency_roots_by_ecosystem as legacy_dependency_roots_by_ecosystem,
)
from platform_context_graph.tools.dependency_catalog import (
    is_dependency_path as legacy_is_dependency_path,
)


def test_dependency_catalog_moves_to_platform_package() -> None:
    """Expose dependency catalog helpers from the platform package."""
    assert new_dependency_ignore_enabled.__module__ == (
        "platform_context_graph.platform.dependency_catalog"
    )
    assert new_dependency_root_sequences.__module__ == (
        "platform_context_graph.platform.dependency_catalog"
    )
    assert new_dependency_roots_by_ecosystem.__module__ == (
        "platform_context_graph.platform.dependency_catalog"
    )
    assert new_is_dependency_path.__module__ == (
        "platform_context_graph.platform.dependency_catalog"
    )


def test_legacy_dependency_catalog_imports_reexport_new_api() -> None:
    """Keep legacy dependency catalog imports working during Phase 1."""
    assert legacy_dependency_ignore_enabled is new_dependency_ignore_enabled
    assert legacy_dependency_root_sequences is new_dependency_root_sequences
    assert legacy_dependency_roots_by_ecosystem is new_dependency_roots_by_ecosystem
    assert legacy_is_dependency_path is new_is_dependency_path
