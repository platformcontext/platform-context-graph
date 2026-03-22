"""Sync loop orchestration for repo synchronization runtimes."""

from __future__ import annotations

import random
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import requests

from platform_context_graph.observability import initialize_observability

from .bootstrap import _request_index
from .config import RepoSyncConfig, RepoSyncResult
from .git import (
    clone_missing_repositories,
    filesystem_sync_all,
    git_token,
    repo_checkout_name,
    update_existing_repositories,
)
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
from ..status_store import update_runtime_status

DEFAULT_REPO_SYNC_RETRY_SECONDS = 5
MAX_REPO_SYNC_RETRY_SECONDS = 300


def _utc_now() -> datetime:
    """Return the current UTC timestamp."""

    return datetime.now(timezone.utc)


def _classify_sync_error(exc: Exception) -> str:
    """Classify one repo-sync exception into a coarse runtime status kind."""

    if isinstance(
        exc,
        (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
            requests.exceptions.ProxyError,
            requests.exceptions.SSLError,
        ),
    ):
        return "network"
    if isinstance(exc, requests.exceptions.HTTPError):
        response = exc.response
        if response is not None and response.status_code in {403, 429}:
            return "rate_limit"
        if response is not None and 500 <= response.status_code < 600:
            return "github_5xx"
        return "http"
    if isinstance(exc, ValueError):
        return "misconfigured"
    return "unknown"


def _retry_after_seconds(exc: Exception, attempt: int) -> int:
    """Return bounded retry delay with jitter for transient sync failures."""

    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        retry_after = exc.response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(1, min(MAX_REPO_SYNC_RETRY_SECONDS, int(retry_after)))
            except ValueError:
                pass
        reset_header = exc.response.headers.get("X-RateLimit-Reset")
        if reset_header:
            try:
                reset_time = datetime.fromtimestamp(int(reset_header), tz=timezone.utc)
                wait_seconds = max(1, int((reset_time - _utc_now()).total_seconds()))
                return min(MAX_REPO_SYNC_RETRY_SECONDS, wait_seconds)
            except ValueError:
                pass
    base_delay = min(
        MAX_REPO_SYNC_RETRY_SECONDS,
        DEFAULT_REPO_SYNC_RETRY_SECONDS * (2 ** max(0, attempt - 1)),
    )
    jitter = random.randint(0, min(5, base_delay))
    return min(MAX_REPO_SYNC_RETRY_SECONDS, base_delay + jitter)


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

    config = RepoSyncConfig.from_env(component="repo-sync")
    initialize_observability(component=config.component)
    initial_delay_seconds = int(os.getenv("PCG_REPO_SYNC_INITIAL_DELAY_SECONDS", "30"))
    if initial_delay_seconds > 0:
        time.sleep(initial_delay_seconds)
    attempt = 1
    while True:
        started_at = _utc_now()
        try:
            update_runtime_status(
                component=config.component,
                source_mode=config.source_mode,
                status="syncing",
                last_attempt_at=started_at,
            )
            run_repo_sync_cycle(config, index_workspace=index_workspace)
            update_runtime_status(
                component=config.component,
                source_mode=config.source_mode,
                status="idle",
                last_attempt_at=started_at,
                last_success_at=_utc_now(),
                next_retry_at=None,
                last_error_kind=None,
                last_error_message=None,
            )
            attempt = 1
            time.sleep(interval_seconds)
        except Exception as exc:
            delay_seconds = _retry_after_seconds(exc, attempt)
            update_runtime_status(
                component=config.component,
                source_mode=config.source_mode,
                status="degraded",
                last_attempt_at=started_at,
                next_retry_at=_utc_now() + timedelta(seconds=delay_seconds),
                last_error_kind=_classify_sync_error(exc),
                last_error_message=str(exc),
            )
            attempt += 1
            log(
                config.component,
                f"Repo sync degraded after transient failure: {exc}. Retrying in {delay_seconds}s",
            )
            time.sleep(delay_seconds)


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
