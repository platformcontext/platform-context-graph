"""Phase 1 import compatibility tests for package resolution helpers."""

from platform_context_graph.platform.package_resolver import (
    get_local_package_path as new_get_local_package_path,
)
from platform_context_graph.tools.package_resolver import (
    get_local_package_path as legacy_get_local_package_path,
)


def test_package_resolver_moves_to_platform_package() -> None:
    """Expose package resolution helpers from the canonical platform package."""
    assert new_get_local_package_path.__module__ == (
        "platform_context_graph.platform.package_resolver"
    )


def test_legacy_package_resolver_import_reexports_canonical_api() -> None:
    """Keep legacy package resolver imports working during Phase 1."""
    assert legacy_get_local_package_path is new_get_local_package_path
