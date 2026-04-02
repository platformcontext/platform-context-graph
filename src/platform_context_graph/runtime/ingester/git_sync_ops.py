"""Git clone/fetch/reset implementation helpers for repo sync runtimes."""

from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from platform_context_graph.observability import get_observability
from platform_context_graph.platform.dependency_catalog import (
    dependency_ignore_enabled,
    is_dependency_path,
)
from platform_context_graph.collectors.git.gitignore import (
    honor_gitignore_enabled,
    is_gitignored_in_repo,
)
from platform_context_graph.collectors.git.discovery import (
    find_pcgignore,
)
from platform_context_graph.utils.debug_log import emit_log_call, warning_logger

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
    """Return a clean HTTPS GitHub origin URL without embedded credentials."""

    if not token:
        return None

    parsed = urlsplit(remote_url.strip())
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        return None

    path = parsed.path.lstrip("/")
    if not path:
        return None

    return f"https://github.com/{path}"


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
    env = git_env_fn(config, token)
    telemetry = get_observability()

    with telemetry.start_span(
        "pcg.ingester.clone_missing_repositories",
        component=config.component,
        attributes={"pcg.ingester.discovered_repo_count": len(discovered)},
    ):
        for repo_id in discovered:
            repo_path = config.repos_dir / repo_checkout_name_fn(repo_id)
            if (repo_path / ".git").exists():
                skipped += 1
                continue

            remote_url = repo_remote_url_fn(config, repo_id, token)
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            log(config.component, f"Cloning {repo_id}")
            with telemetry.start_span(
                "pcg.ingester.clone_repository",
                component=config.component,
                attributes={
                    "pcg.repo.slug": repo_id,
                    "pcg.repo.path": str(repo_path),
                },
            ):
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
                f"[{config.component}] Failed to clone {repo_id}: {result.stderr.strip()}",
                event_name="ingester.clone.failed",
                extra_keys={
                    "repo_slug": repo_id,
                    "repo_path": str(repo_path),
                },
            )
    return discovered, cloned_paths, skipped, failed


def filesystem_sync_all_impl(
    config: RepoSyncConfig,
    *,
    get_config_value_fn,
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
        shutil.copytree(
            source_path,
            target_path,
            ignore=_filesystem_copy_ignore(
                source_path,
                get_config_value_fn=get_config_value_fn,
            ),
            ignore_dangling_symlinks=True,
        )
    return discovered


def _filesystem_copy_ignore(
    repo_root: Path,
    *,
    get_config_value_fn,
):
    """Return a copytree ignore callback aligned to repo/workspace indexing."""

    repo_root = repo_root.resolve()
    ignore_dirs_str = get_config_value_fn("IGNORE_DIRS") or ""
    ignore_dirs = {
        directory.strip().lower()
        for directory in str(ignore_dirs_str).split(",")
        if directory.strip()
    }
    dependency_exclusion_enabled = dependency_ignore_enabled(
        get_config_value_fn=get_config_value_fn
    )
    gitignore_enabled = honor_gitignore_enabled(get_config_value_fn=get_config_value_fn)
    gitignore_cache: dict[Path, object | None] = {}
    pcgignore_spec, pcgignore_root = find_pcgignore(
        repo_root,
        debug_log_fn=lambda _message: None,
        pathspec_module=__import__("pathspec"),
    )
    resolved_pcgignore_root = Path(pcgignore_root).resolve()

    def _ignored(names_root: str, names: list[str]) -> set[str]:
        """Filter copytree children using gitignore, pcgignore, and repo rules."""

        current_root = Path(names_root).resolve()
        ignored: set[str] = set()
        for name in names:
            candidate = current_root / name
            if gitignore_enabled and _is_gitignored_candidate(
                repo_root,
                candidate,
                spec_cache=gitignore_cache,
            ):
                ignored.add(name)
                continue
            if pcgignore_spec is not None:
                try:
                    relative_path = candidate.resolve().relative_to(resolved_pcgignore_root)
                except ValueError:
                    relative_path = None
                if (
                    relative_path is not None
                    and _pcgignore_matches(
                        pcgignore_spec,
                        relative_path=relative_path,
                        is_dir=candidate.is_dir(),
                    )
                ):
                    ignored.add(name)
                    continue
            if not candidate.is_dir():
                continue
            if dependency_exclusion_enabled and _is_dependency_relative_to(
                candidate, root=repo_root
            ):
                ignored.add(name)
                continue
            if name.lower() in ignore_dirs or name.startswith("."):
                ignored.add(name)
        return ignored

    return _ignored


def _is_dependency_relative_to(candidate: Path, *, root: Path) -> bool:
    """Return whether a candidate path lives under a dependency/cache root."""

    try:
        relative_path = candidate.relative_to(root)
    except ValueError:
        return is_dependency_path(candidate)
    if relative_path == Path("."):
        return False
    return is_dependency_path(relative_path)


def _is_gitignored_candidate(
    repo_root: Path,
    candidate: Path,
    *,
    spec_cache: dict[Path, object | None],
) -> bool:
    """Return whether one filesystem copy candidate is ignored by `.gitignore`."""

    if is_gitignored_in_repo(repo_root, candidate, spec_cache=spec_cache):
        return True
    if not candidate.is_dir():
        return False
    probe_path = candidate / "__pcg_dir_probe__"
    return is_gitignored_in_repo(repo_root, probe_path, spec_cache=spec_cache)


def _pcgignore_matches(spec: object, *, relative_path: Path, is_dir: bool) -> bool:
    """Return whether a relative path is ignored by the repo-level `.pcgignore`."""

    match_inputs = [relative_path.as_posix()]
    if is_dir:
        match_inputs.append(f"{relative_path.as_posix().rstrip('/')}/")
    return any(spec.match_file(path_value) for path_value in match_inputs)


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
    env = git_env_fn(config, token)
    retry_cache = load_default_branch_retry_cache(config)
    branchless_repos: list[str] = []
    now = time.time()
    retry_ttl_seconds = default_branch_retry_seconds()
    telemetry = get_observability()

    with telemetry.start_span(
        "pcg.ingester.update_existing_repositories",
        component=config.component,
    ):
        for repo_dir in managed_repository_roots(config.repos_dir):
            cache_key = branchless_retry_key(config, repo_dir)
            if not force_default_branch_refresh:
                expires_at = retry_cache.get(cache_key)
                if expires_at is not None and expires_at > now:
                    continue
                if expires_at is not None:
                    retry_cache.pop(cache_key, None)

            with telemetry.start_span(
                "pcg.ingester.update_repository",
                component=config.component,
                attributes={
                    "pcg.repo.slug": cache_key,
                    "pcg.repo.path": str(repo_dir),
                },
            ):
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
                    emit_log_call(
                        warning_logger,
                        f"[{config.component}] Failed to resolve default branch for "
                        f"{cache_key}: {default_branch_resolution.error}",
                        event_name="ingester.default_branch.failed",
                        extra_keys={"repo_slug": cache_key},
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
                            emit_log_call(
                                warning_logger,
                                f"[{config.component}] Failed to resolve default branch for {cache_key}: {remote_branch_resolution.error}",
                                event_name="ingester.default_branch.failed",
                                extra_keys={"repo_slug": cache_key},
                            )
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
                        emit_log_call(
                            warning_logger,
                            f"[{config.component}] Failed to fetch {cache_key}: {fetch_result.stderr.strip()}",
                            event_name="ingester.fetch.failed",
                            extra_keys={"repo_slug": cache_key},
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
                    emit_log_call(
                        warning_logger,
                        f"[{config.component}] Failed to reset {cache_key}: {reset_result.stderr.strip()}",
                        event_name="ingester.reset.failed",
                        extra_keys={"repo_slug": cache_key},
                    )
    if branchless_repos:
        preview = ", ".join(branchless_repos[:5])
        if len(branchless_repos) > 5:
            preview = f"{preview}, ..."
        emit_log_call(
            warning_logger,
            f"[{config.component}] Skipping {len(branchless_repos)} "
            f"{'repository' if len(branchless_repos) == 1 else 'repositories'} "
            f"with no discoverable default branch: {preview}",
            event_name="ingester.default_branch.missing",
            extra_keys={
                "repository_count": len(branchless_repos),
                "preview": preview,
            },
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
