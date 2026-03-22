"""Query helpers for runtime worker status."""

from __future__ import annotations

import os
from typing import Any

from ..observability import trace_query
from ..runtime.status_store import get_runtime_status_store

__all__ = ["get_index_status"]


def get_index_status(_database: Any, *, component: str = "repo-sync") -> dict[str, Any]:
    """Return persisted runtime status for one worker component."""

    with trace_query("runtime_index_status"):
        store = get_runtime_status_store()
        if store is not None and store.enabled:
            result = store.get_runtime_status(component=component)
            if result is not None:
                return result
        return {
            "component": component,
            "source_mode": os.getenv("PCG_REPO_SOURCE_MODE"),
            "status": "bootstrap_pending",
            "active_run_id": None,
            "last_attempt_at": None,
            "last_success_at": None,
            "next_retry_at": None,
            "last_error_kind": None,
            "last_error_message": None,
            "repository_count": 0,
            "pending_repositories": 0,
            "completed_repositories": 0,
            "failed_repositories": 0,
            "updated_at": None,
        }
