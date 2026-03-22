"""Shared helpers for PostgreSQL-backed runtime ingester status persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

STATUS_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_ingester_status (
    ingester TEXT PRIMARY KEY,
    source_mode TEXT,
    status TEXT NOT NULL,
    active_run_id TEXT,
    last_attempt_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    next_retry_at TIMESTAMPTZ,
    last_error_kind TEXT,
    last_error_message TEXT,
    repository_count INTEGER NOT NULL DEFAULT 0,
    pulled_repositories INTEGER NOT NULL DEFAULT 0,
    in_sync_repositories INTEGER NOT NULL DEFAULT 0,
    pending_repositories INTEGER NOT NULL DEFAULT 0,
    completed_repositories INTEGER NOT NULL DEFAULT 0,
    failed_repositories INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL
);
"""

CONTROL_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_ingester_control (
    ingester TEXT PRIMARY KEY,
    scan_request_token TEXT,
    scan_request_state TEXT NOT NULL DEFAULT 'idle',
    scan_requested_at TIMESTAMPTZ,
    scan_requested_by TEXT,
    scan_started_at TIMESTAMPTZ,
    scan_completed_at TIMESTAMPTZ,
    scan_error_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL
);
"""


def utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def idle_scan_control(ingester: str) -> dict[str, Any]:
    """Return the default idle scan-control payload for one ingester."""

    return {
        "runtime_family": "ingester",
        "ingester": ingester,
        "provider": ingester,
        "scan_request_token": None,
        "scan_request_state": "idle",
        "scan_requested_at": None,
        "scan_requested_by": None,
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
    }
