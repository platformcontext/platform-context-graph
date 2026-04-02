"""Phase 1 import compatibility tests for the Git parse worker move."""

from platform_context_graph.collectors.git.parse_worker import (
    init_parse_worker as new_init_parse_worker,
)
from platform_context_graph.collectors.git.parse_worker import (
    parse_file_in_worker as new_parse_file_in_worker,
)
from platform_context_graph.tools.parse_worker import (
    init_parse_worker as legacy_init_parse_worker,
)
from platform_context_graph.tools.parse_worker import (
    parse_file_in_worker as legacy_parse_file_in_worker,
)


def test_git_parse_worker_moves_to_collectors_package() -> None:
    """Expose the Git parse worker entrypoints from the collector package."""
    assert new_init_parse_worker.__module__ == (
        "platform_context_graph.collectors.git.parse_worker"
    )
    assert new_parse_file_in_worker.__module__ == (
        "platform_context_graph.collectors.git.parse_worker"
    )


def test_legacy_git_parse_worker_imports_reexport_new_api() -> None:
    """Keep legacy parse worker imports working during Phase 1."""
    assert legacy_init_parse_worker is new_init_parse_worker
    assert legacy_parse_file_in_worker is new_parse_file_in_worker
