"""Git and repository discovery helpers for repo sync runtimes."""

from __future__ import annotations

import base64
import os
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import RepoSyncConfig, RepoSyncRepositoryRule, RepoSyncResult
from .github_auth import github_api_request, github_app_token, github_headers
from .git_sync_ops import (
    clone_missing_repositories_detailed_impl,
    filesystem_sync_all_impl,
    refresh_repository_origin_url as _refresh_repository_origin_url_impl,
    refreshed_origin_url as _refreshed_origin_url_impl,
    update_existing_repositories_detailed_impl,
)
from .repository_layout import (
    discover_filesystem_repository_ids,
    managed_repository_roots,
)


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


def list_repo_identifiers(config: RepoSyncConfig, token: str | None) -> list[str]:
    """Discover repository identifiers for the configured source mode.

    Args:
        config: Repo sync configuration.
        token: GitHub token for organization discovery when required.

    Returns:
        Repository identifiers suitable for checkout naming and cloning.
    """

    if config.source_mode == "filesystem":
        if config.filesystem_root is None:
            raise ValueError("filesystem source mode requires PCG_FILESYSTEM_ROOT")
        if config.repositories:
            return sorted(
                "/".join(part for part in repo.strip().strip("/").split("/") if part)
                for repo in config.repositories
                if repo.strip()
            )
        return discover_filesystem_repository_ids(config.filesystem_root)

    if config.source_mode == "explicit":
        return sorted(config.repositories)

    if config.source_mode != "githubOrg":
        raise ValueError(f"Unsupported PCG_REPO_SOURCE_MODE={config.source_mode}")
    if not config.github_org:
        raise ValueError("githubOrg source mode requires PCG_GITHUB_ORG")
    if token is None:
        raise ValueError("githubOrg source mode requires GitHub token or App auth")

    repos: list[str] = []
    page = 1
    while len(repos) < config.repo_limit:
        response = github_api_request(
            "get",
            f"https://api.github.com/orgs/{config.github_org}/repos",
            headers=github_headers(token),
            params={
                "per_page": min(100, config.repo_limit - len(repos)),
                "page": page,
                "type": "all",
            },
            timeout=15,
        )
        items = response.json()
        if not items:
            break
        repos.extend(item["full_name"] for item in items if item.get("full_name"))
        page += 1
    candidates = repos[: config.repo_limit]
    if not config.repository_rules:
        return candidates
    return [
        repo_id
        for repo_id in candidates
        if repository_matches_rules(repo_id, config.repository_rules)
    ]


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
    discovered, cloned, skipped, clone_failed = clone_missing_repositories(
        config, token
    )
    updated, update_failed = update_existing_repositories(config, token)
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
    config: RepoSyncConfig, token: str | None
) -> tuple[list[str], int, int, int]:
    """Clone repositories that are not already present in the workspace."""

    discovered, cloned_paths, skipped, failed = clone_missing_repositories_detailed(
        config, token
    )
    return discovered, len(cloned_paths), skipped, failed


def clone_missing_repositories_detailed(
    config: RepoSyncConfig, token: str | None
) -> tuple[list[str], list[Path], int, int]:
    """Clone repositories that are not already present in the workspace.

    Args:
        config: Repo sync configuration.
        token: Git token used for GitHub discovery and clone URLs.

    Returns:
        Tuple of discovered repository IDs, cloned repository paths, skipped
        count, and failed count.
    """

    return clone_missing_repositories_detailed_impl(
        config,
        token,
        list_repo_identifiers_fn=list_repo_identifiers,
        repo_checkout_name_fn=repo_checkout_name,
        repo_remote_url_fn=repo_remote_url,
        git_env_fn=git_env,
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
        list_repo_identifiers_fn=list_repo_identifiers,
        repo_checkout_name_fn=repo_checkout_name,
    )


def update_existing_repositories(
    config: RepoSyncConfig,
    token: str | None,
    *,
    force_default_branch_refresh: bool = False,
) -> tuple[int, int]:
    """Fetch and hard-reset repositories that changed upstream."""

    updated_paths, failed = update_existing_repositories_detailed(
        config,
        token,
        force_default_branch_refresh=force_default_branch_refresh,
    )
    return len(updated_paths), failed


def update_existing_repositories_detailed(
    config: RepoSyncConfig,
    token: str | None,
    *,
    force_default_branch_refresh: bool = False,
) -> tuple[list[Path], int]:
    """Fetch and hard-reset repositories that changed upstream.

    Args:
        config: Repo sync configuration.
        token: Git token used for authenticated fetches when required.

    Returns:
        Tuple of updated repository paths and failed count.
    """

    return update_existing_repositories_detailed_impl(
        config,
        token,
        force_default_branch_refresh=force_default_branch_refresh,
        git_env_fn=git_env,
        refresh_repository_origin_url_fn=_refresh_repository_origin_url,
        subprocess_run_fn=subprocess.run,
    )
