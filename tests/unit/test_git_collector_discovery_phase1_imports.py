"""Phase 1 import compatibility tests for Git discovery helper moves."""

from platform_context_graph.collectors.git.discovery import (
    collect_supported_files as new_collect_supported_files,
)
from platform_context_graph.collectors.git.discovery import (
    estimate_processing_time as new_estimate_processing_time,
)
from platform_context_graph.tools.graph_builder_indexing_discovery import (
    collect_supported_files as legacy_collect_supported_files,
)
from platform_context_graph.tools.graph_builder_indexing_discovery import (
    estimate_processing_time as legacy_estimate_processing_time,
)


def test_git_discovery_moves_to_collectors_package() -> None:
    """Expose Git discovery helpers from the collectors package."""
    assert new_collect_supported_files.__module__ == (
        "platform_context_graph.collectors.git.discovery"
    )


def test_legacy_git_discovery_imports_reexport_new_api() -> None:
    """Keep legacy Git discovery imports working during Phase 1."""
    assert legacy_collect_supported_files is new_collect_supported_files
    assert legacy_estimate_processing_time is new_estimate_processing_time
