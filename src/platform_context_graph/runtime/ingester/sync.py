"""Sync loop orchestration for repository ingester runtimes."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Callable

from platform_context_graph.observability import (
    get_observability,
    initialize_observability,
)

from .bootstrap import _request_index
from .config import RepoSyncConfig, RepoSyncResult
from .graph_state import graph_missing_repository_paths
from .git import (
    clone_missing_repositories,
    clone_missing_repositories_detailed,
    count_stale_checkouts,
    filesystem_sync_all,
    git_token,
    repo_checkout_name,
    update_existing_repositories,
    update_existing_repositories_detailed,
)
from .retry import classify_sync_error, retry_after_seconds
from .sync_operations import (
    _run_sync_filesystem as _run_sync_filesystem_impl,
    _run_sync_git as _run_sync_git_impl,
)
from .support import (
    begin_index_cycle,
    fingerprint_tree,
    index_workspace_default,
    resumable_repository_paths,
    log,
    manifest_path,
    record_lock_skip,
    record_phase,
    workspace_lock,
)
from ..status_store import (
    claim_ingester_scan_request,
    complete_ingester_scan_request,
    get_runtime_status_store,
    update_runtime_ingester_status,
)

DEFAULT_INGESTER_CONTROL_POLL_SECONDS = 5

_PRESERVED_STATUS_KEYS = (
    "active_run_id",
    "active_repository_path",
    "active_phase",
    "active_phase_started_at",
    "active_current_file",
    "active_last_progress_at",
    "active_commit_started_at",
    "repository_count",
    "pulled_repositories",
    "in_sync_repositories",
    "pending_repositories",
    "completed_repositories",
    "failed_repositories",
)
_REPOSITORY_COUNT_KEYS = frozenset(
    {
        "repository_count",
        "pulled_repositories",
        "in_sync_repositories",
        "pending_repositories",
        "completed_repositories",
        "failed_repositories",
    }
)
_PATCHABLE_GIT_HELPERS = (clone_missing_repositories, update_existing_repositories)


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _current_ingester_status(component: str) -> dict[str, object]:
    """Return the currently persisted ingester status payload, if any."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return {}
    result = store.get_runtime_status(ingester=component)
    return result or {}


def _normalize_status_value(key: str, value: object | None) -> object | None:
    """Normalize persisted ingester status values before writing them."""

    if key in _REPOSITORY_COUNT_KEYS:
        return int(value) if value is not None else 0
    return value


def _persist_ingester_status(
    config: RepoSyncConfig,
    *,
    status: str,
    **overrides: object,
) -> None:
    """Persist ingester status while preserving the latest published repo counts."""

    current = _current_ingester_status(config.component)
    payload: dict[str, object] = {
        "ingester": config.component,
        "source_mode": config.source_mode,
        "status": status,
    }
    for key in _PRESERVED_STATUS_KEYS:
        payload[key] = _normalize_status_value(
            key,
            overrides.pop(
                key, current.get(key, 0 if key in _REPOSITORY_COUNT_KEYS else None)
            ),
        )
    payload.update(overrides)
    update_runtime_ingester_status(**payload)


def _control_poll_seconds() -> int:
    """Return the ingester control polling interval while idle/backing off."""

    return max(
        1,
        int(
            os.getenv(
                "PCG_INGESTER_CONTROL_POLL_SECONDS",
                str(DEFAULT_INGESTER_CONTROL_POLL_SECONDS),
            )
        ),
    )


def _wait_for_next_cycle(
    component: str, delay_seconds: int
) -> dict[str, object] | None:
    """Sleep until the next cycle, waking early when a manual scan is requested."""

    if delay_seconds <= 0:
        return claim_ingester_scan_request(ingester=component)

    deadline = time.monotonic() + delay_seconds
    poll_seconds = _control_poll_seconds()
    while True:
        claimed = claim_ingester_scan_request(ingester=component)
        if claimed is not None:
            return claimed
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None
        time.sleep(min(poll_seconds, remaining))


def _run_sync_filesystem(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[..., None],
) -> RepoSyncResult:
    """Run a filesystem-backed repo sync cycle."""

    return _run_sync_filesystem_impl(
        config,
        index_workspace=index_workspace,
        fingerprint_tree_fn=fingerprint_tree,
        manifest_path_fn=manifest_path,
        log_fn=log,
        filesystem_sync_all_fn=filesystem_sync_all,
        begin_index_cycle_fn=begin_index_cycle,
        record_phase_fn=record_phase,
        repo_checkout_name_fn=repo_checkout_name,
        request_index_fn=_request_index,
    )


def _run_sync_git(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[..., None],
) -> RepoSyncResult:
    """Run a Git-backed repo sync cycle."""

    return _run_sync_git_impl(
        config,
        index_workspace=index_workspace,
        git_token_fn=git_token,
        clone_missing_repositories_detailed_fn=clone_missing_repositories_detailed,
        update_existing_repositories_detailed_fn=update_existing_repositories_detailed,
        count_stale_checkouts_fn=count_stale_checkouts,
        graph_missing_repository_paths_fn=graph_missing_repository_paths,
        repo_checkout_name_fn=repo_checkout_name,
        resumable_repository_paths_fn=resumable_repository_paths,
        begin_index_cycle_fn=begin_index_cycle,
        record_phase_fn=record_phase,
        request_index_fn=_request_index,
        log_fn=log,
    )


def run_repo_sync_cycle(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[..., None] | None = None,
) -> RepoSyncResult:
    """Run one repository synchronization cycle.

    Args:
        config: Repo sync runtime configuration.
        index_workspace: Optional callable that indexes the workspace directory.

    Returns:
        Result summary for the sync cycle.
    """

    initialize_observability(component=config.component)
    index_workspace = index_workspace or index_workspace_default
    with workspace_lock(config) as acquired:
        if not acquired:
            return record_lock_skip(config, mode="sync")
        if config.source_mode == "filesystem":
            return _run_sync_filesystem(config, index_workspace=index_workspace)
        return _run_sync_git(config, index_workspace=index_workspace)


def run_repo_sync_loop(
    *,
    interval_seconds: int,
    index_workspace: Callable[..., None] | None = None,
) -> None:
    """Run the long-lived repo-sync sidecar loop.

    Args:
        interval_seconds: Delay between sync cycles.
        index_workspace: Optional callable that indexes the workspace directory.
    """

    config = RepoSyncConfig.from_env(component="repository")
    initialize_observability(component=config.component)
    initial_delay_seconds = int(os.getenv("PCG_REPO_SYNC_INITIAL_DELAY_SECONDS", "30"))
    pending_request: dict[str, object] | None = None
    if initial_delay_seconds > 0:
        pending_request = _wait_for_next_cycle(config.component, initial_delay_seconds)
    attempt = 1
    while True:
        started_at = _utc_now()
        claimed_request = pending_request or claim_ingester_scan_request(
            ingester=config.component
        )
        pending_request = None
        if claimed_request is not None:
            get_observability().record_ingester_scan_request(
                ingester=config.component,
                phase="claimed",
                requested_by=str(claimed_request.get("scan_requested_by") or "unknown"),
                accepted=True,
            )
        try:
            _persist_ingester_status(
                config,
                status="syncing",
                last_attempt_at=started_at,
            )
            result = run_repo_sync_cycle(config, index_workspace=index_workspace)
            _persist_ingester_status(
                config,
                status="idle",
                last_attempt_at=started_at,
                last_success_at=_utc_now(),
                next_retry_at=None,
                last_error_kind=None,
                last_error_message=None,
                repository_count=result.discovered
                or int(
                    _current_ingester_status(config.component).get(
                        "repository_count", 0
                    )
                ),
                pulled_repositories=result.discovered
                or int(
                    _current_ingester_status(config.component).get(
                        "pulled_repositories", 0
                    )
                ),
            )
            if claimed_request is not None:
                complete_ingester_scan_request(
                    ingester=config.component,
                    request_token=str(claimed_request["scan_request_token"]),
                )
                get_observability().record_ingester_scan_request(
                    ingester=config.component,
                    phase="completed",
                    requested_by=str(
                        claimed_request.get("scan_requested_by") or "unknown"
                    ),
                    accepted=True,
                )
            attempt = 1
            pending_request = _wait_for_next_cycle(config.component, interval_seconds)
        except Exception as exc:
            delay_seconds = retry_after_seconds(exc, attempt)
            _persist_ingester_status(
                config,
                status="degraded",
                last_attempt_at=started_at,
                next_retry_at=_utc_now() + timedelta(seconds=delay_seconds),
                last_error_kind=classify_sync_error(exc),
                last_error_message=str(exc),
            )
            if claimed_request is not None:
                complete_ingester_scan_request(
                    ingester=config.component,
                    request_token=str(claimed_request["scan_request_token"]),
                    error_message=str(exc),
                )
                get_observability().record_ingester_scan_request(
                    ingester=config.component,
                    phase="failed",
                    requested_by=str(
                        claimed_request.get("scan_requested_by") or "unknown"
                    ),
                    accepted=False,
                )
            attempt += 1
            log(
                config.component,
                f"Repo sync degraded after transient failure: {exc}. Retrying in {delay_seconds}s",
            )
            pending_request = _wait_for_next_cycle(config.component, delay_seconds)
