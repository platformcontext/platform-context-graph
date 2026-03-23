"""Git clone/fetch/reset implementation helpers for repo sync runtimes."""

from __future__ import annotations

import shutil
from pathlib import Path
from urllib.parse import urlsplit

from platform_context_graph.utils.debug_log import warning_logger

from .config import RepoSyncConfig
from .support import log


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
        if path.name == ".pcg-sync.lock":
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    for repo_id in discovered:
        source_path = config.filesystem_root / repo_id
        target_path = config.repos_dir / repo_checkout_name_fn(repo_id)
        shutil.copytree(source_path, target_path, ignore_dangling_symlinks=True)
    return discovered


def update_existing_repositories_detailed_impl(
    config: RepoSyncConfig,
    token: str | None,
    *,
    git_env_fn,
    refresh_repository_origin_url_fn,
    subprocess_run_fn,
) -> tuple[list[Path], int]:
    """Fetch and hard-reset repositories that changed upstream."""

    updated_paths: list[Path] = []
    failed = 0
    env = git_env_fn(config)

    for repo_dir in sorted(
        path for path in config.repos_dir.iterdir() if path.is_dir()
    ):
        if not (repo_dir / ".git").exists():
            continue

        default_branch_result = subprocess_run_fn(
            ["git", "-C", str(repo_dir), "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        default_branch = (
            default_branch_result.stdout.strip().replace("refs/remotes/origin/", "")
            if default_branch_result.returncode == 0
            and default_branch_result.stdout.strip()
            else "main"
        )

        refresh_repository_origin_url_fn(
            repo_dir,
            token,
            env,
            subprocess_run_fn=subprocess_run_fn,
        )

        fetch_result = subprocess_run_fn(
            [
                "git",
                "-C",
                str(repo_dir),
                "fetch",
                "origin",
                default_branch,
                f"--depth={config.clone_depth}",
            ],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if fetch_result.returncode != 0:
            failed += 1
            warning_logger(
                f"[{config.component}] Failed to fetch {repo_dir.name}: {fetch_result.stderr.strip()}"
            )
            continue

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
                f"[{config.component}] Failed to reset {repo_dir.name}: {reset_result.stderr.strip()}"
            )
    return updated_paths, failed


__all__ = [
    "clone_missing_repositories_detailed_impl",
    "filesystem_sync_all_impl",
    "refresh_repository_origin_url",
    "refreshed_origin_url",
    "update_existing_repositories_detailed_impl",
]
