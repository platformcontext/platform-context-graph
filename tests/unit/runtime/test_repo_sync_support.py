from __future__ import annotations

import importlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from platform_context_graph.runtime.ingester.config import RepoSyncConfig


def _config_for_lock(tmp_path: Path) -> RepoSyncConfig:
    """Build a minimal repo-sync config for workspace-lock tests."""

    return RepoSyncConfig(
        repos_dir=tmp_path / "workspace" / "repos",
        source_mode="filesystem",
        git_auth_method="none",
        github_org=None,
        repositories=[],
        filesystem_root=tmp_path / "fixtures",
        clone_depth=1,
        repo_limit=100,
        sync_lock_dir=tmp_path / "workspace" / "repos" / ".pcg-sync.lock",
        component="repo-sync",
    )


def _write_lock(
    lock_dir: Path,
    *,
    boot_id: str,
    pid: int,
    hostname: str,
) -> None:
    """Write fresh lock metadata for one holder process."""

    lock_dir.mkdir(parents=True, exist_ok=True)
    (lock_dir / "lock.json").write_text(
        json.dumps(
            {
                "boot_id": boot_id,
                "component": "repo-sync",
                "pid": pid,
                "hostname": hostname,
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def test_is_stale_lock_keeps_fresh_lock_from_same_host_non_pid1_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh locks from other live local processes must not be reaped."""

    support = importlib.import_module("platform_context_graph.runtime.ingester.support")
    config = _config_for_lock(tmp_path)
    _write_lock(
        config.sync_lock_dir,
        boot_id="other-process-boot",
        pid=2222,
        hostname="test-host",
    )

    monkeypatch.setattr(support, "_BOOT_ID", "current-process-boot")
    monkeypatch.setattr(support.socket, "gethostname", lambda: "test-host")
    monkeypatch.setattr(support.os, "getpid", lambda: 3333)

    assert support._is_stale_lock(config) is False


def test_is_stale_lock_reaps_pid1_lock_from_prior_container_boot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PID 1 lock holders should still be reaped after a same-host reboot."""

    support = importlib.import_module("platform_context_graph.runtime.ingester.support")
    config = _config_for_lock(tmp_path)
    _write_lock(
        config.sync_lock_dir,
        boot_id="previous-container-boot",
        pid=1,
        hostname="test-host",
    )

    monkeypatch.setattr(support, "_BOOT_ID", "current-container-boot")
    monkeypatch.setattr(support.socket, "gethostname", lambda: "test-host")
    monkeypatch.setattr(support.os, "getpid", lambda: 1)

    assert support._is_stale_lock(config) is True


def test_managed_repository_roots_ignores_nested_git_directories(
    tmp_path: Path,
) -> None:
    """Nested Git directories inside one managed repo must not count as extra repos."""

    layout = importlib.import_module(
        "platform_context_graph.runtime.ingester.repository_layout"
    )

    repos_dir = tmp_path / "workspace" / "repos"
    repo_root = repos_dir / "boatsgroup" / "payments-api"
    nested_git = repo_root / "vendor" / "example" / ".git"
    (repo_root / ".git").mkdir(parents=True)
    nested_git.mkdir(parents=True)

    roots = layout.managed_repository_roots(repos_dir)

    assert roots == [repo_root.resolve()]


def test_default_branch_retry_seconds_reads_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default-branch retry TTL should be configurable from the environment."""

    support = importlib.import_module("platform_context_graph.runtime.ingester.support")
    monkeypatch.setenv("PCG_DEFAULT_BRANCH_RETRY_SECONDS", "120")

    assert support.default_branch_retry_seconds() == 120
