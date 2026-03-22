"""Query helpers for runtime worker status and control."""

from __future__ import annotations

import os
from typing import Any

from ..observability import get_observability, trace_query
from ..runtime.status_store import get_runtime_status_store, request_index_scan

__all__ = ["get_index_status", "request_index_scan_control"]


def _default_status(component: str) -> dict[str, Any]:
    """Return the default worker status payload when no row exists yet."""

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
        "pulled_repositories": 0,
        "in_sync_repositories": 0,
        "pending_repositories": 0,
        "completed_repositories": 0,
        "failed_repositories": 0,
        "scan_request_state": "idle",
        "scan_request_token": None,
        "scan_requested_at": None,
        "scan_requested_by": None,
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
        "updated_at": None,
    }


def get_index_status(_database: Any, *, component: str = "worker") -> dict[str, Any]:
    """Return persisted runtime status for one worker component."""

    with trace_query("runtime_index_status"):
        store = get_runtime_status_store()
        if store is not None and store.enabled:
            result = store.get_runtime_status(component=component)
            if result is not None:
                return result
        if component == "worker":
            store = get_runtime_status_store()
            if store is not None and store.enabled:
                legacy = store.get_runtime_status(component="repo-sync")
                if legacy is not None:
                    legacy = dict(legacy)
                    legacy["component"] = "worker"
                    return legacy
        return _default_status(component)


def request_index_scan_control(
    _database: Any,
    *,
    component: str = "worker",
    requested_by: str = "api",
) -> dict[str, Any]:
    """Persist a manual worker scan request and return its accepted state."""

    with trace_query("runtime_request_scan"):
        result = request_index_scan(component=component, requested_by=requested_by)
        telemetry = get_observability()
        if result is None:
            telemetry.record_worker_scan_request(
                component="api",
                phase="requested",
                requested_by=requested_by,
                accepted=False,
            )
            return {
                "component": component,
                "accepted": False,
                "scan_request_token": "",
                "scan_request_state": "unavailable",
                "scan_requested_at": "",
                "scan_requested_by": requested_by,
            }
        telemetry.record_worker_scan_request(
            component="api",
            phase="requested",
            requested_by=requested_by,
            accepted=True,
        )
        return {
            "component": result["component"],
            "accepted": True,
            "scan_request_token": result["scan_request_token"],
            "scan_request_state": result["scan_request_state"],
            "scan_requested_at": result["scan_requested_at"],
            "scan_requested_by": result.get("scan_requested_by"),
        }
