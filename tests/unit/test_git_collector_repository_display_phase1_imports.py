"""Phase 1 import compatibility tests for Git repository display helpers."""

from platform_context_graph.collectors.git.display import (
    repository_display_name as new_repository_display_name,
)
from platform_context_graph.tools.repository_display import (
    repository_display_name as legacy_repository_display_name,
)


def test_repository_display_moves_to_git_collector_package() -> None:
    """Expose repository display helpers from the Git collector package."""
    assert new_repository_display_name.__module__ == (
        "platform_context_graph.collectors.git.display"
    )


def test_legacy_repository_display_import_reexports_new_api() -> None:
    """Keep legacy repository display imports working during Phase 1."""
    assert legacy_repository_display_name is new_repository_display_name
