"""Sync loop orchestration for repository ingester runtimes."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from platform_context_graph.observability import get_observability, initialize_observability

from .bootstrap import _request_index
from .config import RepoSyncConfig, RepoSyncResult
from .git import (
    clone_missing_repositories,
    filesystem_sync_all,
    git_token,
    repo_checkout_name,
    update_existing_repositories,
)
from .retry import MAX_REPO_SYNC_RETRY_SECONDS, classify_sync_error, retry_after_seconds
from .support import (
    begin_index_cycle,
    fingerprint_tree,
    index_workspace_default,
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

_PRESERVED_STATUS_KEYS = ("active_run_id", "repository_count", "pulled_repositories", "in_sync_repositories", "pending_repositories", "completed_repositories", "failed_repositories")


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
        payload[key] = overrides.pop(key, current.get(key, 0 if "repositories" in key else None))
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


def _wait_for_next_cycle(component: str, delay_seconds: int) -> dict[str, object] | None:
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
    index_workspace: Callable[[Path], None],
) -> RepoSyncResult:
    """Run a filesystem-backed repo sync cycle.

    Args:
        config: Repo sync runtime configuration.
        index_workspace: Callable that indexes the workspace directory.

    Returns:
        Result summary for the sync cycle.
    """

    if config.filesystem_root is None:
        raise ValueError("filesystem source mode requires PCG_FILESYSTEM_ROOT")

    current_manifest = fingerprint_tree(config.filesystem_root)
    fixture_manifest_path = manifest_path(config)
    previous_manifest = (
        fixture_manifest_path.read_text(encoding="utf-8").strip()
        if fixture_manifest_path.exists()
        else ""
    )
    if current_manifest == previous_manifest:
        log(config.component, "No fixture changes detected")
        return RepoSyncResult()

    discovered = filesystem_sync_all(config)
    discovered_count = len(discovered)
    with begin_index_cycle(config=config, mode="sync", repo_count=discovered_count):
        record_phase(
            config=config,
            mode="sync",
            phase="discovered",
            count=discovered_count,
        )
        record_phase(
            config=config,
            mode="sync",
            phase="updated",
            count=discovered_count,
        )
        record_phase(
            config=config,
            mode="sync",
            phase="indexed",
            count=discovered_count,
        )
        _request_index(config, index_workspace)
        fixture_manifest_path.write_text(current_manifest, encoding="utf-8")
    return RepoSyncResult(
        discovered=discovered_count,
        updated=discovered_count,
        indexed=discovered_count,
    )


def _run_sync_git(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[[Path], None],
) -> RepoSyncResult:
    """Run a Git-backed repo sync cycle.

    Args:
        config: Repo sync runtime configuration.
        index_workspace: Callable that indexes the workspace directory.

    Returns:
        Result summary for the sync cycle.
    """

    token = git_token(config)
    discovered, cloned, clone_skipped, clone_failed = clone_missing_repositories(
        config, token
    )
    updated, update_failed = update_existing_repositories(config, token)
    stale = _stale_checkout_count(config, discovered)
    failed = clone_failed + update_failed
    should_index = cloned > 0 or updated > 0
    if not should_index:
        record_phase(
            config=config,
            mode="sync",
            phase="discovered",
            count=len(discovered),
        )
        if clone_skipped:
            record_phase(
                config=config,
                mode="sync",
                phase="skipped",
                count=clone_skipped,
            )
        if failed:
            record_phase(
                config=config,
                mode="sync",
                phase="failed",
                count=failed,
            )
        if stale:
            record_phase(
                config=config,
                mode="sync",
                phase="stale",
                count=stale,
            )
        log(
            config.component,
            "No repository changes detected; skipping re-index",
        )
        if stale:
            log(
                config.component,
                f"Leaving {stale} stale checkout(s) unmanaged in the workspace",
            )
        return RepoSyncResult(
            discovered=len(discovered),
            skipped=clone_skipped,
            failed=failed,
            stale=stale,
        )

    discovered_count = len(
        [
            path
            for path in config.repos_dir.iterdir()
            if path.is_dir() and (path / ".git").exists()
        ]
    )
    with begin_index_cycle(config=config, mode="sync", repo_count=discovered_count):
        record_phase(
            config=config,
            mode="sync",
            phase="discovered",
            count=len(discovered),
        )
        if cloned:
            record_phase(
                config=config,
                mode="sync",
                phase="cloned",
                count=cloned,
            )
        if updated:
            record_phase(
                config=config,
                mode="sync",
                phase="updated",
                count=updated,
            )
        if clone_skipped:
            record_phase(
                config=config,
                mode="sync",
                phase="skipped",
                count=clone_skipped,
            )
        if failed:
            record_phase(
                config=config,
                mode="sync",
                phase="failed",
                count=failed,
            )
        if stale:
            record_phase(
                config=config,
                mode="sync",
                phase="stale",
                count=stale,
            )
        record_phase(
            config=config,
            mode="sync",
            phase="indexed",
            count=discovered_count,
        )
        _request_index(config, index_workspace)
    return RepoSyncResult(
        discovered=len(discovered),
        cloned=cloned,
        updated=updated,
        skipped=clone_skipped,
        failed=failed,
        stale=stale,
        indexed=discovered_count,
    )


def run_repo_sync_cycle(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[[Path], None] | None = None,
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
    index_workspace: Callable[[Path], None] | None = None,
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
                or int(_current_ingester_status(config.component).get("repository_count", 0)),
                pulled_repositories=result.discovered
                or int(_current_ingester_status(config.component).get("pulled_repositories", 0)),
            )
            if claimed_request is not None:
                complete_ingester_scan_request(
                    ingester=config.component,
                    request_token=str(claimed_request["scan_request_token"]),
                )
                get_observability().record_ingester_scan_request(
                    ingester=config.component,
                    phase="completed",
                    requested_by=str(claimed_request.get("scan_requested_by") or "unknown"),
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
                    requested_by=str(claimed_request.get("scan_requested_by") or "unknown"),
                    accepted=False,
                )
            attempt += 1
            log(
                config.component,
                f"Repo sync degraded after transient failure: {exc}. Retrying in {delay_seconds}s",
            )
            pending_request = _wait_for_next_cycle(config.component, delay_seconds)


def _stale_checkout_count(config: RepoSyncConfig, discovered: list[str]) -> int:
    """Count managed git checkouts that no longer match current discovery rules.

    Args:
        config: Repo sync runtime configuration.
        discovered: Repository identifiers discovered during the current cycle.

    Returns:
        Number of existing git worktrees left unmanaged in the workspace.
    """

    expected_checkout_names = {repo_checkout_name(repo_id) for repo_id in discovered}
    return sum(
        1
        for path in config.repos_dir.iterdir()
        if path.is_dir()
        and (path / ".git").exists()
        and path.name not in expected_checkout_names
    )
