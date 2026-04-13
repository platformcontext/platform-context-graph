"""Support utilities for repo sync runtimes."""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import os
import socket
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

from platform_context_graph.observability import (
    get_observability,
    initialize_observability,
)
from platform_context_graph.utils.debug_log import info_logger, warning_logger

from .config import RepoSyncConfig, RepoSyncResult
from .retry_cache import (
    DEFAULT_BRANCHLESS_RETRY_CACHE_FILENAME,
    DEFAULT_BRANCHLESS_RETRY_SECONDS,
    branchless_retry_key,
    default_branch_retry_cache_path,
    default_branch_retry_seconds,
    load_default_branch_retry_cache,
    save_default_branch_retry_cache,
)

LOCK_METADATA_FILENAME = "lock.json"
DEFAULT_LOCK_HEARTBEAT_SECONDS = 30
DEFAULT_LOCK_STALE_SECONDS = 300

__all__ = [
    "DEFAULT_BRANCHLESS_RETRY_CACHE_FILENAME",
    "DEFAULT_BRANCHLESS_RETRY_SECONDS",
    "branchless_retry_key",
    "default_branch_retry_cache_path",
    "default_branch_retry_seconds",
    "load_default_branch_retry_cache",
    "save_default_branch_retry_cache",
]

# Unique identifier for this process lifetime.  In Kubernetes, PID 1 and
# hostname are reused across container restarts so they cannot distinguish
# a new incarnation from the previous one.  A random boot ID lets
# ``_is_stale_lock`` detect that the holder no longer exists even when
# the heartbeat file on the PVC still looks fresh.
_BOOT_ID: str = hashlib.sha256(
    f"{os.getpid()}-{time.monotonic_ns()}".encode()
).hexdigest()[:16]


def index_workspace_default(
    workspace: Path,
    *,
    selected_repositories: list[Path] | None = None,
    family: str = "index",
    source: str = "manual",
    component: str = "cli",
    force: bool = False,
) -> None:
    """Run the default CLI indexing entrypoint for a workspace.

    Args:
        workspace: Repository workspace to index.
    """

    from platform_context_graph.cli.cli_helpers import index_helper

    index_helper(
        str(workspace),
        force=force,
        selected_repositories=selected_repositories,
        family=family,
        source=source,
        component=component,
    )


def invoke_index_workspace(
    index_workspace: Callable[..., None],
    workspace: Path,
    *,
    selected_repositories: list[Path] | None = None,
    family: str,
    source: str,
    component: str,
    force: bool = False,
) -> None:
    """Call an index callback with repo-batch metadata when supported."""

    try:
        signature = inspect.signature(index_workspace)
    except (TypeError, ValueError):
        index_workspace(workspace)
        return

    accepts_var_kwargs = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    kwargs: dict[str, object] = {}
    for key, value in {
        "selected_repositories": selected_repositories,
        "family": family,
        "source": source,
        "component": component,
        "force": force,
    }.items():
        if accepts_var_kwargs or key in signature.parameters:
            kwargs[key] = value
    index_workspace(workspace, **kwargs)


def resumable_repository_paths(workspace: Path) -> list[Path]:
    """Return repositories from the latest workspace run that still need work."""

    from platform_context_graph.indexing.coordinator_models import ACTIVE_REPO_STATES
    from platform_context_graph.indexing.run_status import describe_latest_index_run

    summary = describe_latest_index_run(workspace.resolve())
    if summary is None:
        return []
    return sorted(
        {
            Path(repository["repo_path"]).resolve()
            for repository in summary.get("repositories", [])
            if repository.get("status") in ACTIVE_REPO_STATES
        },
        key=str,
    )


def log(component: str, message: str) -> None:
    """Emit a repo-sync runtime log message.

    Args:
        component: Runtime component name.
        message: Human-readable log message.
    """

    info_logger(
        f"[{component}] {message}",
        event_name="ingester.lifecycle",
        extra_keys={"ingester_component": component},
    )


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


def _lock_metadata_path(config: RepoSyncConfig) -> Path:
    """Return the metadata path used to track workspace lock ownership."""

    return config.sync_lock_dir / LOCK_METADATA_FILENAME


def _utc_now() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""

    return datetime.now(timezone.utc).isoformat()


def _lock_heartbeat_seconds() -> int:
    """Return the configured workspace lock heartbeat interval."""

    return max(
        1,
        int(
            os.getenv(
                "PCG_SYNC_LOCK_HEARTBEAT_SECONDS",
                str(DEFAULT_LOCK_HEARTBEAT_SECONDS),
            )
        ),
    )


def _lock_stale_seconds() -> int:
    """Return the maximum age for a workspace lock heartbeat."""

    return max(
        _lock_heartbeat_seconds() + 1,
        int(
            os.getenv(
                "PCG_SYNC_LOCK_STALE_SECONDS",
                str(DEFAULT_LOCK_STALE_SECONDS),
            )
        ),
    )


def _write_lock_metadata(config: RepoSyncConfig) -> None:
    """Persist current workspace lock ownership metadata."""

    _lock_metadata_path(config).write_text(
        json.dumps(
            {
                "boot_id": _BOOT_ID,
                "component": config.component,
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "heartbeat_at": _utc_now(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def _is_stale_lock(config: RepoSyncConfig) -> bool:
    """Return whether the current workspace lock should be treated as stale.

    A lock is stale when either:
    * The heartbeat is older than ``_lock_stale_seconds()``, **or**
    * The lock was written by a different boot (i.e. a previous container
      incarnation that no longer exists).  In Kubernetes, PID 1 and the
      pod hostname are reused after a restart, so heartbeat age alone is
      not sufficient to detect a dead holder.
    """

    metadata_path = _lock_metadata_path(config)
    if not metadata_path.exists():
        return True

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        heartbeat_at = payload["heartbeat_at"]
        heartbeat_time = datetime.fromisoformat(heartbeat_at)
    except (KeyError, ValueError, json.JSONDecodeError, OSError):
        return True

    # If both the current process and the recorded holder are PID 1 on the same
    # hostname, a boot_id mismatch means this is a restarted container entrypoint
    # rather than a concurrent local process. Restricting the heuristic to PID 1
    # avoids reaping fresh locks from other live processes on the same host.
    lock_boot_id = payload.get("boot_id")
    lock_hostname = payload.get("hostname")
    try:
        lock_pid = int(payload.get("pid"))
    except (TypeError, ValueError):
        lock_pid = None
    if (
        os.getpid() == 1
        and lock_pid == 1
        and lock_boot_id is not None
        and lock_boot_id != _BOOT_ID
        and lock_hostname == socket.gethostname()
    ):
        return True

    if heartbeat_time.tzinfo is None:
        heartbeat_time = heartbeat_time.replace(tzinfo=timezone.utc)

    age_seconds = (datetime.now(timezone.utc) - heartbeat_time).total_seconds()
    return age_seconds > _lock_stale_seconds()


def _start_lock_heartbeat(
    config: RepoSyncConfig,
) -> tuple[threading.Event, threading.Thread]:
    """Start the background heartbeat updater for the workspace lock."""

    stop_event = threading.Event()
    interval_seconds = _lock_heartbeat_seconds()

    def _heartbeat() -> None:
        """Refresh lock ownership metadata until the lock is released."""

        while not stop_event.wait(interval_seconds):
            try:
                _write_lock_metadata(config)
            except OSError:
                break

    thread = threading.Thread(
        target=_heartbeat,
        name=f"pcg-sync-lock-heartbeat-{config.component}",
        daemon=True,
    )
    thread.start()
    return stop_event, thread


def _remove_workspace_lock_path(lock_path: Path) -> OSError | None:
    """Remove a workspace lock path whether it is a directory or a file.

    Returns:
        ``None`` when the path was removed successfully or did not exist.
        The underlying ``OSError`` when cleanup fails.
    """

    try:
        if lock_path.is_dir() and not lock_path.is_symlink():
            shutil.rmtree(lock_path)
        else:
            lock_path.unlink()
    except FileNotFoundError:
        return None
    except OSError as exc:
        return exc
    return None if not lock_path.exists() else OSError("workspace lock still exists")


@contextlib.contextmanager
def workspace_lock(config: RepoSyncConfig) -> Iterator[bool]:
    """Acquire the repo workspace lock for a sync or bootstrap cycle.

    Args:
        config: Repo sync configuration.

    Yields:
        ``True`` when the caller acquired the lock, otherwise ``False``.
    """

    if config.sync_lock_dir.exists() and _is_stale_lock(config):
        log(
            config.component,
            f"Reaping stale workspace lock at {config.sync_lock_dir}",
        )
        cleanup_error = _remove_workspace_lock_path(config.sync_lock_dir)
        if cleanup_error is not None:
            warning_logger(
                f"[{config.component}] Failed to remove stale workspace lock at "
                f"{config.sync_lock_dir}: {cleanup_error}; skipping cycle",
                event_name="ingester.lifecycle",
                extra_keys={"ingester_component": config.component},
                exc_info=cleanup_error,
            )
            yield False
            return

    try:
        config.sync_lock_dir.mkdir(parents=True)
    except FileExistsError:
        log(
            config.component,
            f"Workspace lock busy at {config.sync_lock_dir}; skipping cycle",
        )
        yield False
        return

    _write_lock_metadata(config)
    stop_event, heartbeat_thread = _start_lock_heartbeat(config)
    log(config.component, f"Acquired workspace lock at {config.sync_lock_dir}")
    try:
        yield True
    finally:
        stop_event.set()
        heartbeat_thread.join(timeout=_lock_heartbeat_seconds())
        cleanup_error = _remove_workspace_lock_path(config.sync_lock_dir)
        if cleanup_error is not None:
            warning_logger(
                f"[{config.component}] Failed to remove workspace lock at "
                f"{config.sync_lock_dir}: {cleanup_error}",
                event_name="ingester.lifecycle",
                extra_keys={"ingester_component": config.component},
                exc_info=cleanup_error,
            )
        else:
            log(config.component, f"Released workspace lock at {config.sync_lock_dir}")


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
    log(
        config.component,
        f"Skipped {mode} cycle because workspace lock {config.sync_lock_dir} is active",
    )
    return RepoSyncResult(lock_skipped=True)
