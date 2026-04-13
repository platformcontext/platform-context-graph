"""Lazy runtime exports for ingestion orchestration helpers."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "RepoSyncConfig",
    "RepoSyncResult",
    "run_bootstrap_index",
    "run_repo_sync_cycle",
    "run_repo_sync_loop",
]


def __getattr__(name: str) -> Any:
    """Resolve runtime exports lazily to avoid eager side effects."""

    if name not in __all__:
        raise AttributeError(name)
    module = import_module("platform_context_graph.runtime.ingester")
    return getattr(module, name)
