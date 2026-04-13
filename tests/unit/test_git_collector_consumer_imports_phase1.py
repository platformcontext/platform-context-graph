"""Phase 1 import checks for discovery helper consumers."""

from __future__ import annotations

import platform_context_graph.runtime.ingester.git_sync_ops as git_sync_ops_module


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
