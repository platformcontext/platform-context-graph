"""Support utilities for repo sync runtimes."""

from __future__ import annotations

import contextlib
import hashlib
import shutil
from pathlib import Path
from typing import Iterator

from platform_context_graph.observability import (
    get_observability,
    initialize_observability,
)
from platform_context_graph.utils.debug_log import info_logger

from .config import RepoSyncConfig, RepoSyncResult


def index_workspace_default(workspace: Path) -> None:
    """Run the default CLI indexing entrypoint for a workspace.

    Args:
        workspace: Repository workspace to index.
    """

    from platform_context_graph.cli.cli_helpers import index_helper

    index_helper(str(workspace))


def log(component: str, message: str) -> None:
    """Emit a repo-sync runtime log message.

    Args:
        component: Runtime component name.
        message: Human-readable log message.
    """

    info_logger(f"[{component}] {message}")


def fingerprint_tree(root: Path) -> str:
    """Compute a stable fingerprint for the contents of a directory tree.

    Args:
        root: Directory whose file contents should be fingerprinted.

    Returns:
        SHA-256 digest over the file paths and metadata in the tree.
    """

    digest = hashlib.sha256()
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        relative_path = file_path.relative_to(root)
        digest.update(str(relative_path).encode("utf-8"))
        stat = file_path.stat()
        digest.update(str(int(stat.st_mtime_ns)).encode("utf-8"))
        digest.update(str(stat.st_size).encode("utf-8"))
    return digest.hexdigest()


def manifest_path(config: RepoSyncConfig) -> Path:
    """Return the manifest file used by filesystem sync mode.

    Args:
        config: Repo sync configuration.

    Returns:
        Path to the current manifest file.
    """

    return config.repos_dir / ".pcg-fixture-manifest"


@contextlib.contextmanager
def workspace_lock(config: RepoSyncConfig) -> Iterator[bool]:
    """Acquire the repo workspace lock for a sync or bootstrap cycle.

    Args:
        config: Repo sync configuration.

    Yields:
        ``True`` when the caller acquired the lock, otherwise ``False``.
    """

    try:
        config.sync_lock_dir.mkdir(parents=True)
    except FileExistsError:
        yield False
        return

    try:
        yield True
    finally:
        shutil.rmtree(config.sync_lock_dir, ignore_errors=True)


def begin_index_cycle(
    *,
    config: RepoSyncConfig,
    mode: str,
    repo_count: int,
) -> contextlib.AbstractContextManager[None]:
    """Create the observability scope for a repo indexing cycle.

    Args:
        config: Repo sync configuration.
        mode: Cycle mode, such as ``bootstrap`` or ``sync``.
        repo_count: Number of repositories in the current cycle.

    Returns:
        Context manager that records the index run telemetry.
    """

    initialize_observability(component=config.component)
    telemetry = get_observability()
    return telemetry.index_run(
        component=config.component,
        mode=mode,
        source=config.source_mode,
        repo_count=repo_count,
    )


def record_phase(
    *,
    config: RepoSyncConfig,
    mode: str,
    phase: str,
    count: int,
) -> None:
    """Record a repo-sync phase count in observability.

    Args:
        config: Repo sync configuration.
        mode: Cycle mode, such as ``bootstrap`` or ``sync``.
        phase: Telemetry phase name.
        count: Number of repositories in the phase.
    """

    get_observability().record_index_repositories(
        component=config.component,
        phase=phase,
        count=count,
        mode=mode,
        source=config.source_mode,
    )


def record_lock_skip(config: RepoSyncConfig, *, mode: str) -> RepoSyncResult:
    """Record a lock-contention skip and return the standard result object.

    Args:
        config: Repo sync configuration.
        mode: Cycle mode, such as ``bootstrap`` or ``sync``.

    Returns:
        Result object describing a skipped cycle.
    """

    get_observability().record_lock_contention_skip(
        component=config.component,
        mode=mode,
        source=config.source_mode,
    )
    return RepoSyncResult(lock_skipped=True)
