"""Persistent retry-cache helpers for repo-sync workspaces."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import RepoSyncConfig

DEFAULT_BRANCHLESS_RETRY_SECONDS = 86400
DEFAULT_BRANCHLESS_RETRY_CACHE_FILENAME = ".pcg-default-branch-retry-cache.json"


def default_branch_retry_cache_path(config: RepoSyncConfig) -> Path:
    """Return the persistent cache file for repos missing a default branch."""
    return config.repos_dir / DEFAULT_BRANCHLESS_RETRY_CACHE_FILENAME


def default_branch_retry_seconds() -> int:
    """Return the retry TTL for repos without a discoverable default branch."""
    return max(
        1,
        int(
            os.getenv(
                "PCG_DEFAULT_BRANCH_RETRY_SECONDS",
                str(DEFAULT_BRANCHLESS_RETRY_SECONDS),
            )
        ),
    )


def branchless_retry_key(config: RepoSyncConfig, repo_dir: Path) -> str:
    """Return the cache key for one managed repository checkout."""
    repo_root = repo_dir.resolve()
    workspace_root = config.repos_dir.resolve()
    try:
        return repo_root.relative_to(workspace_root).as_posix()
    except ValueError:
        return repo_root.as_posix()


def load_default_branch_retry_cache(config: RepoSyncConfig) -> dict[str, float]:
    """Load the persisted cache of repos that recently lacked a default branch."""
    cache_path = default_branch_retry_cache_path(config)
    if not cache_path.exists():
        return {}

    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}

    entries = payload.get("repos", payload) if isinstance(payload, dict) else {}
    if not isinstance(entries, dict):
        return {}

    cache: dict[str, float] = {}
    for repo_key, expires_at in entries.items():
        try:
            cache[str(repo_key)] = float(expires_at)
        except (TypeError, ValueError):
            continue
    return cache


def save_default_branch_retry_cache(
    config: RepoSyncConfig,
    retry_cache: dict[str, float],
) -> None:
    """Persist the retry cache for repos without a discoverable default branch."""
    cache_path = default_branch_retry_cache_path(config)
    if not retry_cache:
        try:
            cache_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        return

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps({"version": 1, "repos": retry_cache}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
