"""Git clone/fetch/reset implementation helpers for repo sync runtimes."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from platform_context_graph.utils.debug_log import warning_logger

from .config import RepoSyncConfig
from .repository_layout import managed_repository_roots
from .support import (
    branchless_retry_key,
    default_branch_retry_seconds,
    load_default_branch_retry_cache,
    log,
    save_default_branch_retry_cache,
)

@dataclass(frozen=True, slots=True)
class DefaultBranchResolution:
    """Resolved default-branch state for one repository checkout."""

    branch: str | None
    error: str | None = None
    from_remote_head: bool = False


def _parse_remote_head_branch(symbolic_ref: str, *, prefix: str) -> str | None:
    """Extract a branch name from a symbolic ref output string."""

    normalized = symbolic_ref.strip()
    if not normalized.startswith(prefix):
        return None
    branch = normalized.removeprefix(prefix).strip()
    return branch or None


def _resolve_default_branch(
    repo_dir: Path,
    env: dict[str, str],
    *,
    subprocess_run_fn,
) -> DefaultBranchResolution:
    """Return the default branch for a checkout, or failure details."""

    local_head = subprocess_run_fn(
        ["git", "-C", str(repo_dir), "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    branch = _parse_remote_head_branch(
        local_head.stdout,
        prefix="refs/remotes/origin/",
    )
    if branch is not None:
        return DefaultBranchResolution(branch=branch)

    return _resolve_remote_default_branch(
        repo_dir,
        env,
        subprocess_run_fn=subprocess_run_fn,
    )


def _resolve_remote_default_branch(
    repo_dir: Path,
    env: dict[str, str],
    *,
    subprocess_run_fn,
) -> DefaultBranchResolution:
    """Return the current remote HEAD branch or the lookup failure."""

    remote_head = subprocess_run_fn(
        ["git", "-C", str(repo_dir), "ls-remote", "--symref", "origin", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if remote_head.returncode != 0:
        error = remote_head.stderr.strip() or remote_head.stdout.strip()
        return DefaultBranchResolution(
            branch=None,
            error=error or "unable to query remote HEAD",
            from_remote_head=True,
        )

    for line in remote_head.stdout.splitlines():
        branch = _parse_remote_head_branch(
            line.split("\t", 1)[0],
            prefix="ref: refs/heads/",
        )
        if branch is not None:
            return DefaultBranchResolution(branch=branch, from_remote_head=True)
    return DefaultBranchResolution(branch=None, from_remote_head=True)


def _is_missing_remote_ref(stderr: str, branch: str) -> bool:
    """Return whether a fetch failed because the remote branch does not exist."""

    normalized = stderr.strip().lower()
    return (
        "couldn't find remote ref" in normalized
        and branch.strip().lower() in normalized
    )


def _retry_fetch_after_stale_shallow_lock(
    repo_dir: Path,
    fetch_command: list[str],
    env: dict[str, str],
    component: str,
    fetch_result,
    *,
    subprocess_run_fn,
):
    """Remove a stale ``.git/shallow.lock`` file and retry fetch once."""

    normalized = fetch_result.stderr.strip()
    shallow_lock = repo_dir / ".git" / "shallow.lock"
    if ".git/shallow.lock" not in normalized or "File exists" not in normalized:
        return fetch_result
    if not shallow_lock.exists():
        return fetch_result

    try:
        shallow_lock.unlink()
    except OSError:
        return fetch_result

    log(component, f"Removed stale shallow lock for {repo_dir.name}; retrying fetch")
    return subprocess_run_fn(
        fetch_command,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _fetch_branch(
    repo_dir: Path,
    branch: str,
    clone_depth: int,
    env: dict[str, str],
    component: str,
    *,
    subprocess_run_fn,
):
    """Fetch one branch and retry once if a stale shallow lock is present."""

    fetch_command = [
        "git",
        "-C",
        str(repo_dir),
        "fetch",
        "origin",
        branch,
        f"--depth={clone_depth}",
    ]
    fetch_result = subprocess_run_fn(
        fetch_command,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    return _retry_fetch_after_stale_shallow_lock(
        repo_dir,
        fetch_command,
        env,
        component,
        fetch_result,
        subprocess_run_fn=subprocess_run_fn,
    )


def _set_remote_head_branch(
    repo_dir: Path,
    branch: str,
    env: dict[str, str],
    component: str,
    *,
    subprocess_run_fn,
) -> None:
    """Update the cached ``origin/HEAD`` symref after remote resolution succeeds."""

    set_head_result = subprocess_run_fn(
        ["git", "-C", str(repo_dir), "remote", "set-head", "origin", branch],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if set_head_result.returncode != 0:
        warning_logger(
            f"[{component}] Failed to update origin/HEAD for {repo_dir.name}: "
            f"{set_head_result.stderr.strip()}"
        )


def refreshed_origin_url(remote_url: str, token: str | None) -> str | None:
    """Return an HTTPS origin URL with the current token injected."""

    if not token:
        return None

    parsed = urlsplit(remote_url.strip())
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        return None

    path = parsed.path.lstrip("/")
    if not path:
        return None

    return f"https://x-access-token:{token}@github.com/{path}"


def refresh_repository_origin_url(
    repo_dir: Path,
    token: str | None,
    env: dict[str, str],
    *,
    subprocess_run_fn,
) -> None:
    """Rewrite an existing HTTPS origin to use the latest GitHub token."""

    if not token:
        return

    origin_result = subprocess_run_fn(
        ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if origin_result.returncode != 0:
        return

    current_origin = origin_result.stdout.strip()
    refreshed_origin = refreshed_origin_url(current_origin, token)
    if refreshed_origin is None or refreshed_origin == current_origin:
        return

    subprocess_run_fn(
        ["git", "-C", str(repo_dir), "remote", "set-url", "origin", refreshed_origin],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def clone_missing_repositories_detailed_impl(
    config: RepoSyncConfig,
    token: str | None,
    *,
    list_repo_identifiers_fn,
    repo_checkout_name_fn,
    repo_remote_url_fn,
    git_env_fn,
    subprocess_run_fn,
) -> tuple[list[str], list[Path], int, int]:
    """Clone repositories that are not already present in the workspace."""

    config.repos_dir.mkdir(parents=True, exist_ok=True)
    discovered = list_repo_identifiers_fn(config, token)
    cloned_paths: list[Path] = []
    skipped = 0
    failed = 0
    env = git_env_fn(config)

    for repo_id in discovered:
        repo_path = config.repos_dir / repo_checkout_name_fn(repo_id)
        if (repo_path / ".git").exists():
            skipped += 1
            continue

        remote_url = repo_remote_url_fn(config, repo_id, token)
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        log(config.component, f"Cloning {repo_id}")
        result = subprocess_run_fn(
            [
                "git",
                "clone",
                f"--depth={config.clone_depth}",
                "--single-branch",
                remote_url,
                str(repo_path),
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if result.returncode == 0:
            cloned_paths.append(repo_path.resolve())
            continue

        failed += 1
        shutil.rmtree(repo_path, ignore_errors=True)
        warning_logger(
            f"[{config.component}] Failed to clone {repo_id}: {result.stderr.strip()}"
        )
    return discovered, cloned_paths, skipped, failed


def filesystem_sync_all_impl(
    config: RepoSyncConfig,
    *,
    list_repo_identifiers_fn,
    repo_checkout_name_fn,
) -> list[str]:
    """Copy all filesystem-mode repositories into the managed workspace."""

    if config.filesystem_root is None:
        raise ValueError("filesystem source mode requires PCG_FILESYSTEM_ROOT")

    discovered = list_repo_identifiers_fn(config, token=None)
    config.repos_dir.mkdir(parents=True, exist_ok=True)
    for path in config.repos_dir.iterdir():
        if path.name.startswith(".pcg-"):
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    for repo_id in discovered:
        source_path = config.filesystem_root / repo_id
        target_path = config.repos_dir / repo_checkout_name_fn(repo_id)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_path, target_path, ignore_dangling_symlinks=True)
    return discovered


def update_existing_repositories_detailed_impl(
    config: RepoSyncConfig,
    token: str | None,
    force_default_branch_refresh: bool = False,
    *,
    git_env_fn,
    refresh_repository_origin_url_fn,
    subprocess_run_fn,
) -> tuple[list[Path], int]:
    """Fetch and hard-reset repositories that changed upstream."""

    updated_paths: list[Path] = []
    failed = 0
    env = git_env_fn(config)
    retry_cache = load_default_branch_retry_cache(config)
    branchless_repos: list[str] = []
    now = time.time()
    retry_ttl_seconds = default_branch_retry_seconds()

    for repo_dir in managed_repository_roots(config.repos_dir):
        cache_key = branchless_retry_key(config, repo_dir)
        if not force_default_branch_refresh:
            expires_at = retry_cache.get(cache_key)
            if expires_at is not None and expires_at > now:
                continue
            if expires_at is not None:
                retry_cache.pop(cache_key, None)

        refresh_repository_origin_url_fn(
            repo_dir,
            token,
            env,
            subprocess_run_fn=subprocess_run_fn,
        )

        default_branch_resolution = _resolve_default_branch(
            repo_dir,
            env,
            subprocess_run_fn=subprocess_run_fn,
        )
        if default_branch_resolution.error is not None:
            failed += 1
            warning_logger(
                f"[{config.component}] Failed to resolve default branch for "
                f"{cache_key}: {default_branch_resolution.error}"
            )
            continue
        if default_branch_resolution.branch is None:
            retry_cache[cache_key] = now + retry_ttl_seconds
            branchless_repos.append(cache_key)
            continue

        retry_cache.pop(cache_key, None)
        default_branch = default_branch_resolution.branch
        heal_remote_head = default_branch_resolution.from_remote_head
        fetch_result = _fetch_branch(
            repo_dir,
            default_branch,
            config.clone_depth,
            env,
            config.component,
            subprocess_run_fn=subprocess_run_fn,
        )
        if fetch_result.returncode != 0:
            if _is_missing_remote_ref(fetch_result.stderr, default_branch):
                remote_branch_resolution = _resolve_remote_default_branch(
                    repo_dir,
                    env,
                    subprocess_run_fn=subprocess_run_fn,
                )
                if remote_branch_resolution.error is not None:
                    failed += 1
                    warning_logger(f"[{config.component}] Failed to resolve default branch for {cache_key}: {remote_branch_resolution.error}")
                    continue
                if remote_branch_resolution.branch is None:
                    retry_cache[cache_key] = now + retry_ttl_seconds
                    branchless_repos.append(cache_key)
                    continue
                if remote_branch_resolution.branch != default_branch:
                    default_branch = remote_branch_resolution.branch
                    heal_remote_head = remote_branch_resolution.from_remote_head
                    fetch_result = _fetch_branch(
                        repo_dir,
                        default_branch,
                        config.clone_depth,
                        env,
                        config.component,
                        subprocess_run_fn=subprocess_run_fn,
                    )
            if fetch_result.returncode != 0:
                failed += 1
                warning_logger(
                    f"[{config.component}] Failed to fetch {cache_key}: {fetch_result.stderr.strip()}"
                )
                continue
        if heal_remote_head:
            _set_remote_head_branch(
                repo_dir,
                default_branch,
                env,
                config.component,
                subprocess_run_fn=subprocess_run_fn,
            )

        local_head = subprocess_run_fn(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        ).stdout.strip()
        remote_head = subprocess_run_fn(
            ["git", "-C", str(repo_dir), "rev-parse", "FETCH_HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        ).stdout.strip()
        if local_head == remote_head:
            continue

        reset_result = subprocess_run_fn(
            ["git", "-C", str(repo_dir), "reset", "--hard", "FETCH_HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if reset_result.returncode == 0:
            updated_paths.append(repo_dir.resolve())
        else:
            failed += 1
            warning_logger(
                f"[{config.component}] Failed to reset {cache_key}: {reset_result.stderr.strip()}"
            )
    if branchless_repos:
        preview = ", ".join(branchless_repos[:5])
        if len(branchless_repos) > 5:
            preview = f"{preview}, ..."
        warning_logger(
            f"[{config.component}] Skipping {len(branchless_repos)} "
            f"{'repository' if len(branchless_repos) == 1 else 'repositories'} "
            f"with no discoverable default branch: {preview}"
        )
    save_default_branch_retry_cache(config, retry_cache)
    return updated_paths, failed


__all__ = [
    "clone_missing_repositories_detailed_impl",
    "filesystem_sync_all_impl",
    "refresh_repository_origin_url",
    "refreshed_origin_url",
    "update_existing_repositories_detailed_impl",
]
