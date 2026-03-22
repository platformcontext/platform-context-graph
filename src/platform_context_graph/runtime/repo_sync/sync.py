"""Sync loop orchestration for repo synchronization runtimes."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

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
    time.sleep(int(os.getenv("PCG_REPO_SYNC_INITIAL_DELAY_SECONDS", "30")))
    while True:
        run_repo_sync_cycle(config, index_workspace=index_workspace)
        time.sleep(interval_seconds)


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
