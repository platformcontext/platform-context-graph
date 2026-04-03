"""Phase 1 import checks for discovery helper consumers."""

from __future__ import annotations

import platform_context_graph.core.watch_repository as watch_repository_module
import platform_context_graph.indexing.coordinator as coordinator_module
import platform_context_graph.indexing.coordinator_pipeline as coordinator_pipeline_module
import platform_context_graph.runtime.ingester.git_sync_ops as git_sync_ops_module


def test_coordinator_uses_canonical_git_collector_indexing() -> None:
    """Coordinator should import Git collector indexing helpers directly."""

    assert coordinator_module.resolve_repository_file_sets.__module__ == (
        "platform_context_graph.collectors.git.discovery"
    )
    assert coordinator_module.parse_repository_snapshot_async.__module__ == (
        "platform_context_graph.collectors.git.parse_execution"
    )


def test_watch_repository_uses_canonical_git_collector_discovery() -> None:
    """Repository watcher should import discovery helpers from the collector."""

    assert watch_repository_module.discover_index_files.__module__ == (
        "platform_context_graph.collectors.git.discovery"
    )


def test_coordinator_pipeline_uses_canonical_git_collector_indexing() -> None:
    """Coordinator pipeline should use canonical Git collector indexing helpers."""

    assert coordinator_pipeline_module.merge_import_maps.__module__ == (
        "platform_context_graph.collectors.git.discovery"
    )


def test_git_sync_runtime_uses_canonical_gitignore_and_discovery() -> None:
    """Repo sync runtime should use canonical Git collector helpers."""

    assert git_sync_ops_module.honor_gitignore_enabled.__module__ == (
        "platform_context_graph.collectors.git.gitignore"
    )
    assert git_sync_ops_module.is_gitignored_in_repo.__module__ == (
        "platform_context_graph.collectors.git.gitignore"
    )
    assert git_sync_ops_module.find_pcgignore.__module__ == (
        "platform_context_graph.collectors.git.discovery"
    )
