"""Lazy exports for repository ingester runtime entrypoints."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "RepoSyncConfig",
    "RepoSyncResult",
    "build_workspace_plan",
    "run_bootstrap_index",
    "run_repo_sync_cycle",
    "run_repo_sync_loop",
    "run_workspace_sync",
]

_ATTRIBUTE_MODULES = {
    "RepoSyncConfig": "platform_context_graph.runtime.ingester.config",
    "RepoSyncResult": "platform_context_graph.runtime.ingester.config",
    "build_workspace_plan": "platform_context_graph.runtime.ingester.git",
    "run_bootstrap_index": "platform_context_graph.runtime.ingester.bootstrap",
    "run_repo_sync_cycle": "platform_context_graph.runtime.ingester.sync",
    "run_repo_sync_loop": "platform_context_graph.runtime.ingester.sync",
    "run_workspace_sync": "platform_context_graph.runtime.ingester.git",
}


def __getattr__(name: str) -> Any:
    """Resolve ingester exports lazily to avoid eager dependency loading."""

    module_name = _ATTRIBUTE_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    module = import_module(module_name)
    return getattr(module, name)
