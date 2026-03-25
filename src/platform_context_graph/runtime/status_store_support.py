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
    active_repository_path TEXT,
    active_phase TEXT,
    active_phase_started_at TIMESTAMPTZ,
    active_current_file TEXT,
    active_last_progress_at TIMESTAMPTZ,
    active_commit_started_at TIMESTAMPTZ,
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
ALTER TABLE runtime_ingester_status
    ADD COLUMN IF NOT EXISTS active_repository_path TEXT;
ALTER TABLE runtime_ingester_status
    ADD COLUMN IF NOT EXISTS active_phase TEXT;
ALTER TABLE runtime_ingester_status
    ADD COLUMN IF NOT EXISTS active_phase_started_at TIMESTAMPTZ;
ALTER TABLE runtime_ingester_status
    ADD COLUMN IF NOT EXISTS active_current_file TEXT;
ALTER TABLE runtime_ingester_status
    ADD COLUMN IF NOT EXISTS active_last_progress_at TIMESTAMPTZ;
ALTER TABLE runtime_ingester_status
    ADD COLUMN IF NOT EXISTS active_commit_started_at TIMESTAMPTZ;
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

COVERAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS runtime_repository_coverage (
    run_id TEXT NOT NULL,
    repo_id TEXT NOT NULL,
    repo_name TEXT NOT NULL,
    repo_path TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT,
    finalization_status TEXT,
    discovered_file_count INTEGER NOT NULL DEFAULT 0,
    graph_recursive_file_count INTEGER NOT NULL DEFAULT 0,
    content_file_count INTEGER NOT NULL DEFAULT 0,
    content_entity_count INTEGER NOT NULL DEFAULT 0,
    root_file_count INTEGER NOT NULL DEFAULT 0,
    root_directory_count INTEGER NOT NULL DEFAULT 0,
    top_level_function_count INTEGER NOT NULL DEFAULT 0,
    class_method_count INTEGER NOT NULL DEFAULT 0,
    total_function_count INTEGER NOT NULL DEFAULT 0,
    class_count INTEGER NOT NULL DEFAULT 0,
    graph_available BOOLEAN NOT NULL DEFAULT FALSE,
    server_content_available BOOLEAN NOT NULL DEFAULT FALSE,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    commit_finished_at TIMESTAMPTZ,
    finalization_finished_at TIMESTAMPTZ,
    PRIMARY KEY (run_id, repo_id)
);
CREATE INDEX IF NOT EXISTS idx_runtime_repository_coverage_repo
    ON runtime_repository_coverage (repo_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_runtime_repository_coverage_run
    ON runtime_repository_coverage (run_id, updated_at DESC);
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
