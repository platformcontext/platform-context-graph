"""Git and repository discovery helpers for repo sync runtimes."""

from __future__ import annotations

import base64
import inspect
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from ...cli.config_manager import get_config_value
from .config import RepoSyncConfig, RepoSyncRepositoryRule, RepoSyncResult
from .github_auth import github_app_token
from .git_sync_ops import (
    clone_missing_repositories_detailed_impl,
    filesystem_sync_all_impl,
    refresh_repository_origin_url as _refresh_repository_origin_url_impl,
    refreshed_origin_url as _refreshed_origin_url_impl,
    update_existing_repositories_detailed_impl,
)
from .repository_layout import managed_repository_roots
from .repository_selection import (
    archived_skip_summary,
    discover_repository_selection,
)
from .support import log


@dataclass(frozen=True, slots=True)
class WorkspacePlan:
    """Preview of the repositories selected for one workspace."""

    source_mode: str
    repos_dir: Path
    repository_ids: list[str]
    matched_repositories: int
    already_cloned: int
    stale_checkouts: int


def git_token(config: RepoSyncConfig) -> str | None:
    """Resolve the token used for Git and GitHub operations.

    Args:
        config: Repo sync configuration.

    Returns:
        Token string when the configured auth mode uses one, otherwise ``None``.
    """

    if config.git_auth_method == "githubApp":
        return github_app_token()
    if config.git_auth_method == "token":
        return os.getenv("PCG_GIT_TOKEN") or os.getenv("GITHUB_TOKEN")
    return None


def _append_git_config_env(env: dict[str, str], key: str, value: str) -> None:
    """Append one Git config override to a subprocess environment."""

    raw_count = env.get("GIT_CONFIG_COUNT", "0")
    try:
        config_count = int(raw_count)
    except ValueError:
        config_count = 0
    env["GIT_CONFIG_COUNT"] = str(config_count + 1)
    env[f"GIT_CONFIG_KEY_{config_count}"] = key
    env[f"GIT_CONFIG_VALUE_{config_count}"] = value


def _github_http_extraheader(token: str) -> str:
    """Return the GitHub HTTPS authorization header for Git subprocesses."""

    encoded = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode(
        "ascii"
    )
    return f"AUTHORIZATION: basic {encoded}"


def git_env(config: RepoSyncConfig, token: str | None = None) -> dict[str, str]:
    """Build the subprocess environment for Git operations.

    Args:
        config: Repo sync configuration.
        token: Optional pre-resolved GitHub token.

    Returns:
        Process environment with SSH configuration when needed.
    """

    env = dict(os.environ)
    if config.git_auth_method != "ssh":
        resolved_token = token if token is not None else git_token(config)
        if config.git_auth_method in {"githubApp", "token"} and resolved_token:
            _append_git_config_env(
                env,
                "http.https://github.com/.extraheader",
                _github_http_extraheader(resolved_token),
            )
        return env

    private_key_path = os.getenv(
        "PCG_SSH_PRIVATE_KEY_PATH", "/var/run/secrets/pcg-ssh/id_rsa"
    )
    known_hosts_path = os.getenv(
        "PCG_SSH_KNOWN_HOSTS_PATH", "/var/run/secrets/pcg-ssh/known_hosts"
    )
    strict_hosts = "yes" if Path(known_hosts_path).exists() else "no"
    known_hosts_opt = (
        f"-o UserKnownHostsFile={known_hosts_path}"
        if Path(known_hosts_path).exists()
        else ""
    )
    env["GIT_SSH_COMMAND"] = (
        f"ssh -i {private_key_path} {known_hosts_opt} -o StrictHostKeyChecking={strict_hosts}"
    ).strip()
    return env


def _git_operation_env(config: RepoSyncConfig, token: str | None) -> dict[str, str]:
    """Build per-operation Git subprocess auth state.

    GitHub App tokens expire during long repo-sync cycles, so each clone or fetch
    operation must resolve auth from the current cache state instead of reusing a
    token captured at the start of the cycle.

    Args:
        config: Repo sync configuration.
        token: Previously resolved token for non-refreshing auth modes.

    Returns:
        Git subprocess environment for the current operation.
    """

    operation_token = token
    if config.git_auth_method == "githubApp":
        operation_token = None
    return git_env(config, operation_token)


def _call_with_supported_kwargs(function: Callable[..., object], /, *args, **kwargs):
    """Call a helper with only the keyword arguments it declares."""

    signature = inspect.signature(function)
    supported_kwargs = {
        key: value for key, value in kwargs.items() if key in signature.parameters
    }
    return function(*args, **supported_kwargs)


def list_repo_identifiers(config: RepoSyncConfig, token: str | None) -> list[str]:
    """Discover repository identifiers for the configured source mode.

    Args:
        config: Repo sync configuration.
        token: GitHub token for organization discovery when required.

    Returns:
        Repository identifiers suitable for checkout naming and cloning.
    """

    return discover_repository_selection(config, token).repository_ids


def count_stale_checkouts(config: RepoSyncConfig, discovered: list[str]) -> int:
    """Count managed git checkouts that no longer match current discovery rules."""

    expected_checkout_paths = {
        (config.repos_dir / repo_checkout_name(repo_id)).resolve()
        for repo_id in discovered
    }
    return sum(
        1
        for path in managed_repository_roots(config.repos_dir)
        if path.resolve() not in expected_checkout_paths
    )


def build_workspace_plan(config: RepoSyncConfig) -> dict[str, object]:
    """Return a non-mutating preview of the currently selected workspace."""

    token = git_token(config) if config.source_mode == "githubOrg" else None
    repository_ids = list_repo_identifiers(config, token)
    checkout_paths = {
        (config.repos_dir / repo_checkout_name(repo_id)).resolve()
        for repo_id in repository_ids
    }
    already_cloned = 0
    already_cloned = sum(
        1
        for path in managed_repository_roots(config.repos_dir)
        if path.resolve() in checkout_paths
    )

    plan = asdict(
        WorkspacePlan(
            source_mode=config.source_mode,
            repos_dir=config.repos_dir,
            repository_ids=repository_ids,
            matched_repositories=len(repository_ids),
            already_cloned=already_cloned,
            stale_checkouts=count_stale_checkouts(config, repository_ids),
        )
    )
    plan["repos_dir"] = str(config.repos_dir)
    return plan


def run_workspace_sync(config: RepoSyncConfig) -> RepoSyncResult:
    """Clone, fetch, or copy the configured workspace without indexing it."""

    if config.source_mode == "filesystem":
        discovered = filesystem_sync_all(config)
        return RepoSyncResult(
            discovered=len(discovered),
            cloned=len(discovered),
        )

    token = git_token(config)
    selection = discover_repository_selection(config, token)
    if selection.archived_repository_ids:
        log(config.component, archived_skip_summary(selection.archived_repository_ids))
    discovered, cloned, skipped, clone_failed = clone_missing_repositories(
        config,
        token,
        selected_repository_ids=selection.repository_ids,
    )
    updated, update_failed = update_existing_repositories(
        config,
        token,
        selected_repository_ids=selection.repository_ids,
    )
    return RepoSyncResult(
        discovered=len(discovered),
        cloned=cloned,
        updated=updated,
        skipped=skipped,
        failed=clone_failed + update_failed,
        stale=count_stale_checkouts(config, discovered),
    )


def repository_matches_rules(
    repository_id: str, rules: tuple[RepoSyncRepositoryRule, ...]
) -> bool:
    """Return whether a repository identifier matches any include rule.

    Args:
        repository_id: Repository identifier, typically ``org/repo``.
        rules: Include rules configured for the runtime.

    Returns:
        ``True`` when the repository should be synced.
    """

    if not rules:
        return True
    return any(rule.matches(repository_id) for rule in rules)


def repo_checkout_name(repo_id: str) -> str:
    """Return the local checkout directory name for a repository identifier.

    Args:
        repo_id: Repository identifier, typically ``org/repo``.

    Returns:
        Relative repository path used as the local checkout directory name.
    """
    sanitized = repo_id.replace("\\", "/").strip().strip("/")
    if not sanitized:
        return "repository"
    parts = [part for part in sanitized.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        raise ValueError(f"Invalid repository identifier for checkout path: {repo_id}")
    return "/".join(parts)


def repo_remote_url(config: RepoSyncConfig, repo_id: str, token: str | None) -> str:
    """Build the Git remote URL for the configured repository and auth mode.

    Args:
        config: Repo sync configuration.
        repo_id: Repository identifier, optionally unqualified.
        token: Git token when required by the auth mode.

    Returns:
        Remote URL suitable for ``git clone``.
    """

    slug = repo_id
    if "/" not in slug:
        if not config.github_org:
            raise ValueError("Non-qualified repository names require PCG_GITHUB_ORG")
        slug = f"{config.github_org}/{slug}"

    if config.git_auth_method == "ssh":
        return f"git@github.com:{slug}.git"
    return f"https://github.com/{slug}.git"


def _refreshed_origin_url(remote_url: str, token: str | None) -> str | None:
    """Return an HTTPS origin URL with the current token injected."""

    return _refreshed_origin_url_impl(remote_url, token)


def _refresh_repository_origin_url(
    repo_dir: Path,
    token: str | None,
    env: dict[str, str],
    *,
    subprocess_run_fn=subprocess.run,
) -> None:
    """Rewrite an existing HTTPS origin to use the latest GitHub token."""

    _refresh_repository_origin_url_impl(
        repo_dir,
        token,
        env,
        subprocess_run_fn=subprocess_run_fn,
    )


def clone_missing_repositories(
    config: RepoSyncConfig,
    token: str | None,
    *,
    selected_repository_ids: list[str] | None = None,
    archived_repository_ids_observer: Callable[[list[str]], None] | None = None,
) -> tuple[list[str], int, int, int]:
    """Clone repositories that are not already present in the workspace."""

    discovered, cloned_paths, skipped, failed = clone_missing_repositories_detailed(
        config,
        token,
        selected_repository_ids=selected_repository_ids,
        archived_repository_ids_observer=archived_repository_ids_observer,
    )
    return discovered, len(cloned_paths), skipped, failed


def clone_missing_repositories_detailed(
    config: RepoSyncConfig,
    token: str | None,
    *,
    selected_repository_ids: list[str] | None = None,
    archived_repository_ids_observer: Callable[[list[str]], None] | None = None,
) -> tuple[list[str], list[Path], int, int]:
    """Clone repositories that are not already present in the workspace.

    Args:
        config: Repo sync configuration.
        token: Git token used for GitHub discovery and clone URLs.

    Returns:
        Tuple of discovered repository IDs, cloned repository paths, skipped
        count, and failed count.
    """

    if selected_repository_ids is None:
        if archived_repository_ids_observer is None:
            selected_repository_ids = list_repo_identifiers(config, token)
        else:
            selection = discover_repository_selection(config, token)
            selected_repository_ids = selection.repository_ids
            if selection.archived_repository_ids:
                log(
                    config.component,
                    archived_skip_summary(selection.archived_repository_ids),
                )
            archived_repository_ids_observer(selection.archived_repository_ids)

    return _call_with_supported_kwargs(
        clone_missing_repositories_detailed_impl,
        config,
        token,
        repository_ids=selected_repository_ids,
        list_repo_identifiers_fn=lambda *_args: selected_repository_ids,
        repo_checkout_name_fn=repo_checkout_name,
        repo_remote_url_fn=repo_remote_url,
        git_env_fn=_git_operation_env,
        subprocess_run_fn=subprocess.run,
    )


def filesystem_sync_all(config: RepoSyncConfig) -> list[str]:
    """Copy all filesystem-mode repositories into the managed workspace.

    Args:
        config: Repo sync configuration.

    Returns:
        Repository identifiers copied into the workspace.
    """

    return filesystem_sync_all_impl(
        config,
        get_config_value_fn=get_config_value,
        list_repo_identifiers_fn=list_repo_identifiers,
        repo_checkout_name_fn=repo_checkout_name,
    )


def update_existing_repositories(
    config: RepoSyncConfig,
    token: str | None,
    *,
    force_default_branch_refresh: bool = False,
    selected_repository_ids: list[str] | None = None,
) -> tuple[int, int]:
    """Fetch and hard-reset repositories that changed upstream."""

    updated_paths, failed = update_existing_repositories_detailed(
        config,
        token,
        force_default_branch_refresh=force_default_branch_refresh,
        selected_repository_ids=selected_repository_ids,
    )
    return len(updated_paths), failed


def update_existing_repositories_detailed(
    config: RepoSyncConfig,
    token: str | None,
    *,
    force_default_branch_refresh: bool = False,
    selected_repository_ids: list[str] | None = None,
) -> tuple[list[Path], int]:
    """Fetch and hard-reset repositories that changed upstream.

    Args:
        config: Repo sync configuration.
        token: Git token used for authenticated fetches when required.

    Returns:
        Tuple of updated repository paths and failed count.
    """

    if selected_repository_ids is None:
        selected_repository_ids = [
            repo_dir.resolve().relative_to(config.repos_dir.resolve()).as_posix()
            for repo_dir in managed_repository_roots(config.repos_dir)
        ]

    selected_repository_paths = {
        (config.repos_dir / repo_checkout_name(repo_id)).resolve()
        for repo_id in selected_repository_ids
    }

    return _call_with_supported_kwargs(
        update_existing_repositories_detailed_impl,
        config,
        token,
        force_default_branch_refresh=force_default_branch_refresh,
        selected_repository_paths=selected_repository_paths,
        git_env_fn=_git_operation_env,
        refresh_repository_origin_url_fn=_refresh_repository_origin_url,
        subprocess_run_fn=subprocess.run,
    )
