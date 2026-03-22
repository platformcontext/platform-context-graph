"""Bootstrap orchestration for repo synchronization runtimes."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from platform_context_graph.observability import (
    get_observability,
    initialize_observability,
)

from .config import RepoSyncConfig, RepoSyncResult
from .git import (
    clone_missing_repositories_detailed,
    filesystem_sync_all,
    git_token,
    repo_checkout_name,
)
from .support import (
    begin_index_cycle,
    fingerprint_tree,
    index_workspace_default,
    invoke_index_workspace,
    manifest_path,
    record_phase,
    log,
    workspace_lock,
)

DEFAULT_BOOTSTRAP_LOCK_RETRY_SECONDS = 5
DEFAULT_BOOTSTRAP_LOCK_MAX_WAIT_SECONDS = 600


def _bootstrap_lock_retry_seconds() -> float:
    """Return the delay between bootstrap lock acquisition attempts."""

    return max(
        1.0,
        float(
            os.getenv(
                "PCG_BOOTSTRAP_LOCK_RETRY_SECONDS",
                str(DEFAULT_BOOTSTRAP_LOCK_RETRY_SECONDS),
            )
        ),
    )


def _bootstrap_lock_max_wait_seconds() -> float:
    """Return the maximum time bootstrap waits for the workspace lock."""

    return max(
        _bootstrap_lock_retry_seconds(),
        float(
            os.getenv(
                "PCG_BOOTSTRAP_LOCK_MAX_WAIT_SECONDS",
                str(DEFAULT_BOOTSTRAP_LOCK_MAX_WAIT_SECONDS),
            )
        ),
    )


def _request_index(
    config: RepoSyncConfig,
    index_workspace: Callable[..., None],
    *,
    selected_repositories: list[Path] | None = None,
    family: str,
) -> None:
    """Run an index request under the repo-sync observability request context.

    Args:
        config: Repo sync runtime configuration.
        index_workspace: Callable that indexes the workspace directory.
    """

    with get_observability().request_context(component=config.component):
        invoke_index_workspace(
            index_workspace,
            config.repos_dir,
            selected_repositories=selected_repositories,
            family=family,
            source=config.source_mode,
            component=config.component,
        )


def _record_bootstrap_phases(
    *,
    config: RepoSyncConfig,
    discovered_count: int,
    cloned_count: int,
    skipped_count: int,
    failed_count: int,
) -> None:
    """Record repo phase counters for a bootstrap cycle.

    Args:
        config: Repo sync runtime configuration.
        discovered_count: Number of repositories discovered.
        cloned_count: Number of repositories cloned.
        skipped_count: Number of repositories skipped.
        failed_count: Number of repositories that failed.
    """

    record_phase(
        config=config,
        mode="bootstrap",
        phase="discovered",
        count=discovered_count,
    )
    if cloned_count:
        record_phase(
            config=config,
            mode="bootstrap",
            phase="cloned",
            count=cloned_count,
        )
    if skipped_count:
        record_phase(
            config=config,
            mode="bootstrap",
            phase="skipped",
            count=skipped_count,
        )
    if failed_count:
        record_phase(
            config=config,
            mode="bootstrap",
            phase="failed",
            count=failed_count,
        )
    record_phase(
        config=config,
        mode="bootstrap",
        phase="indexed",
        count=discovered_count,
    )


def _run_bootstrap_filesystem(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[..., None],
) -> RepoSyncResult:
    """Run filesystem-mode bootstrap indexing.

    Args:
        config: Repo sync runtime configuration.
        index_workspace: Callable that indexes the workspace directory.

    Returns:
        Result summary for the bootstrap cycle.
    """

    discovered = filesystem_sync_all(config)
    discovered_count = len(discovered)
    with begin_index_cycle(
        config=config,
        mode="bootstrap",
        repo_count=discovered_count,
    ):
        _record_bootstrap_phases(
            config=config,
            discovered_count=discovered_count,
            cloned_count=discovered_count,
            skipped_count=0,
            failed_count=0,
        )
        selected_repositories = [
            (config.repos_dir / repo_checkout_name(repo_id)).resolve()
            for repo_id in discovered
        ]
        _request_index(
            config,
            index_workspace,
            selected_repositories=selected_repositories,
            family="bootstrap",
        )
        if config.filesystem_root is not None:
            manifest_path(config).write_text(
                fingerprint_tree(config.filesystem_root),
                encoding="utf-8",
            )
    return RepoSyncResult(
        discovered=discovered_count,
        cloned=discovered_count,
        indexed=discovered_count,
    )


def _run_bootstrap_git(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[..., None],
) -> RepoSyncResult:
    """Run Git-backed bootstrap indexing.

    Args:
        config: Repo sync runtime configuration.
        index_workspace: Callable that indexes the workspace directory.

    Returns:
        Result summary for the bootstrap cycle.
    """

    token = git_token(config)
    discovered, cloned_paths, skipped, failed = clone_missing_repositories_detailed(
        config, token
    )
    cloned = len(cloned_paths)
    discovered_count = len(discovered)
    with begin_index_cycle(
        config=config,
        mode="bootstrap",
        repo_count=discovered_count,
    ):
        _record_bootstrap_phases(
            config=config,
            discovered_count=discovered_count,
            cloned_count=cloned,
            skipped_count=skipped,
            failed_count=failed,
        )
        selected_repositories = [
            (config.repos_dir / repo_checkout_name(repo_id)).resolve()
            for repo_id in discovered
        ]
        _request_index(
            config,
            index_workspace,
            selected_repositories=selected_repositories,
            family="bootstrap",
        )
    return RepoSyncResult(
        discovered=discovered_count,
        cloned=cloned,
        skipped=skipped,
        failed=failed,
        indexed=discovered_count,
    )


def run_bootstrap_index(
    config: RepoSyncConfig,
    *,
    index_workspace: Callable[..., None] | None = None,
) -> RepoSyncResult:
    """Run the initial workspace bootstrap clone/sync and indexing pass.

    Args:
        config: Repo sync runtime configuration.
        index_workspace: Optional callable that indexes the workspace directory.

    Returns:
        Result summary for the bootstrap cycle.
    """

    initialize_observability(component=config.component)
    index_workspace = index_workspace or index_workspace_default
    retry_seconds = _bootstrap_lock_retry_seconds()
    max_wait_seconds = _bootstrap_lock_max_wait_seconds()
    deadline = time.monotonic() + max_wait_seconds

    while True:
        with workspace_lock(config) as acquired:
            if acquired:
                if config.source_mode == "filesystem":
                    return _run_bootstrap_filesystem(
                        config, index_workspace=index_workspace
                    )
                return _run_bootstrap_git(config, index_workspace=index_workspace)

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(
                f"Bootstrap could not acquire workspace lock within {max_wait_seconds:.0f}s"
            )
        sleep_seconds = min(retry_seconds, remaining)
        log(
            config.component,
            f"Workspace lock busy; retrying bootstrap in {sleep_seconds:.0f}s",
        )
        time.sleep(sleep_seconds)
