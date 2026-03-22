"""Query helpers for runtime ingester status and control."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from ..observability import get_observability, trace_query
from ..runtime.status_store import (
    get_runtime_status_store,
    request_ingester_scan,
)

__all__ = [
    "KNOWN_INGESTERS",
    "get_ingester_status",
    "list_ingesters",
    "request_ingester_scan_control",
]

KNOWN_INGESTERS = ("repository",)
_TIMESTAMP_FIELDS = (
    "last_attempt_at",
    "last_success_at",
    "next_retry_at",
    "scan_requested_at",
    "scan_started_at",
    "scan_completed_at",
    "updated_at",
)


def _default_status(ingester: str) -> dict[str, Any]:
    """Return the default ingester status payload when no row exists yet."""

    return {
        "runtime_family": "ingester",
        "ingester": ingester,
        "provider": ingester,
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


def _normalize_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert status-store timestamps to stable ISO-8601 strings."""

    normalized = dict(payload)
    for field in _TIMESTAMP_FIELDS:
        value = normalized.get(field)
        if isinstance(value, datetime):
            normalized[field] = value.isoformat()
    return normalized


def list_ingesters(_database: Any) -> list[dict[str, Any]]:
    """Return the current status for each known ingester."""

    with trace_query("runtime_list_ingesters"):
        return [get_ingester_status(_database, ingester=name) for name in KNOWN_INGESTERS]


def get_ingester_status(
    _database: Any,
    *,
    ingester: str = "repository",
) -> dict[str, Any]:
    """Return persisted runtime status for one ingester."""

    with trace_query("runtime_ingester_status"):
        store = get_runtime_status_store()
        if store is not None and store.enabled:
            result = store.get_runtime_status(ingester=ingester)
            if result is not None:
                return _normalize_status_payload(result)
        return _default_status(ingester)


def request_ingester_scan_control(
    _database: Any,
    *,
    ingester: str = "repository",
    requested_by: str = "api",
) -> dict[str, Any]:
    """Persist a manual ingester scan request and return its accepted state."""

    with trace_query("runtime_request_ingester_scan"):
        result = request_ingester_scan(ingester=ingester, requested_by=requested_by)
        telemetry = get_observability()
        if result is None:
            telemetry.record_ingester_scan_request(
                ingester=ingester,
                phase="requested",
                requested_by=requested_by,
                accepted=False,
            )
            return {
                "runtime_family": "ingester",
                "ingester": ingester,
                "provider": ingester,
                "accepted": False,
                "scan_request_token": "",
                "scan_request_state": "unavailable",
                "scan_requested_at": None,
                "scan_requested_by": requested_by,
            }
        telemetry.record_ingester_scan_request(
            ingester=ingester,
            phase="requested",
            requested_by=requested_by,
            accepted=True,
        )
        return _normalize_status_payload(
            {
                "runtime_family": "ingester",
                "ingester": result["ingester"],
                "provider": result["ingester"],
                "accepted": True,
                "scan_request_token": result["scan_request_token"],
                "scan_request_state": result["scan_request_state"],
                "scan_requested_at": result["scan_requested_at"],
                "scan_requested_by": result.get("scan_requested_by"),
            }
        )
