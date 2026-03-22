"""Git and repository discovery helpers for repo sync runtimes."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from platform_context_graph.utils.debug_log import warning_logger

from .config import RepoSyncConfig, RepoSyncRepositoryRule, RepoSyncResult
from .github_auth import github_api_request, github_app_token, github_headers
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


def git_env(config: RepoSyncConfig) -> dict[str, str]:
    """Build the subprocess environment for Git operations.

    Args:
        config: Repo sync configuration.

    Returns:
        Process environment with SSH configuration when needed.
    """

    env = dict(os.environ)
    if config.git_auth_method != "ssh":
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
        return sorted(
            path.name for path in config.filesystem_root.iterdir() if path.is_dir()
        )

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

    if not config.repos_dir.exists():
        return 0

    expected_checkout_names = {repo_checkout_name(repo_id) for repo_id in discovered}
    return sum(
        1
        for path in config.repos_dir.iterdir()
        if path.is_dir()
        and (path / ".git").exists()
        and path.name not in expected_checkout_names
    )


def build_workspace_plan(config: RepoSyncConfig) -> dict[str, object]:
    """Return a non-mutating preview of the currently selected workspace."""

    token = git_token(config)
    repository_ids = list_repo_identifiers(config, token)
    checkout_names = {repo_checkout_name(repo_id) for repo_id in repository_ids}
    already_cloned = 0
    if config.repos_dir.exists():
        already_cloned = sum(
            1
            for path in config.repos_dir.iterdir()
            if path.is_dir()
            and (path / ".git").exists()
            and path.name in checkout_names
        )

    return asdict(
        WorkspacePlan(
            source_mode=config.source_mode,
            repos_dir=config.repos_dir,
            repository_ids=repository_ids,
            matched_repositories=len(repository_ids),
            already_cloned=already_cloned,
            stale_checkouts=count_stale_checkouts(config, repository_ids),
        )
    )


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
        Stable slug used as the local directory name.
    """
    sanitized = repo_id.strip().strip("/")
    if not sanitized:
        return "repository"
    return sanitized.replace("/", "--")


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
    if token:
        return f"https://x-access-token:{token}@github.com/{slug}.git"
    return f"https://github.com/{slug}.git"


def _refreshed_origin_url(remote_url: str, token: str | None) -> str | None:
    """Return an HTTPS origin URL with the current token injected.

    Args:
        remote_url: Existing origin URL stored in the repository config.
        token: GitHub token for authenticated HTTPS access.

    Returns:
        A refreshed authenticated origin URL, or ``None`` when the remote should
        be left unchanged.
    """

    if not token:
        return None

    parsed = urlsplit(remote_url.strip())
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        return None

    path = parsed.path.lstrip("/")
    if not path:
        return None

    return f"https://x-access-token:{token}@github.com/{path}"


def _refresh_repository_origin_url(
    repo_dir: Path,
    token: str | None,
    env: dict[str, str],
) -> None:
    """Rewrite an existing HTTPS origin to use the latest GitHub token."""

    if not token:
        return

    origin_result = subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    if origin_result.returncode != 0:
        return

    current_origin = origin_result.stdout.strip()
    refreshed_origin = _refreshed_origin_url(current_origin, token)
    if refreshed_origin is None or refreshed_origin == current_origin:
        return

    subprocess.run(
        ["git", "-C", str(repo_dir), "remote", "set-url", "origin", refreshed_origin],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def clone_missing_repositories(
    config: RepoSyncConfig, token: str | None
) -> tuple[list[str], int, int, int]:
    """Clone repositories that are not already present in the workspace.

    Args:
        config: Repo sync configuration.
        token: Git token used for GitHub discovery and clone URLs.

    Returns:
        Tuple of discovered repository IDs, cloned count, skipped count, and
        failed count.
    """

    config.repos_dir.mkdir(parents=True, exist_ok=True)
    discovered = list_repo_identifiers(config, token)
    cloned = 0
    skipped = 0
    failed = 0
    env = git_env(config)

    for repo_id in discovered:
        repo_path = config.repos_dir / repo_checkout_name(repo_id)
        if (repo_path / ".git").exists():
            skipped += 1
            continue

        remote_url = repo_remote_url(config, repo_id, token)
        log(config.component, f"Cloning {repo_id}")
        result = subprocess.run(
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
            cloned += 1
            continue

        failed += 1
        shutil.rmtree(repo_path, ignore_errors=True)
        warning_logger(
            f"[{config.component}] Failed to clone {repo_id}: {result.stderr.strip()}"
        )
    return discovered, cloned, skipped, failed


def filesystem_sync_all(config: RepoSyncConfig) -> list[str]:
    """Copy all filesystem-mode repositories into the managed workspace.

    Args:
        config: Repo sync configuration.

    Returns:
        Repository identifiers copied into the workspace.
    """

    if config.filesystem_root is None:
        raise ValueError("filesystem source mode requires PCG_FILESYSTEM_ROOT")

    discovered = list_repo_identifiers(config, token=None)
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
        target_path = config.repos_dir / repo_checkout_name(repo_id)
        shutil.copytree(source_path, target_path, ignore_dangling_symlinks=True)
    return discovered


def update_existing_repositories(
    config: RepoSyncConfig, token: str | None
) -> tuple[int, int]:
    """Fetch and hard-reset repositories that changed upstream.

    Args:
        config: Repo sync configuration.
        token: Git token used for authenticated fetches when required.

    Returns:
        Tuple of updated count and failed count.
    """

    updated = 0
    failed = 0
    env = git_env(config)

    for repo_dir in sorted(
        path for path in config.repos_dir.iterdir() if path.is_dir()
    ):
        if not (repo_dir / ".git").exists():
            continue

        default_branch_result = subprocess.run(
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

        _refresh_repository_origin_url(repo_dir, token, env)

        fetch_result = subprocess.run(
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

        local_head = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        ).stdout.strip()
        remote_head = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "FETCH_HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        ).stdout.strip()
        if local_head == remote_head:
            continue

        reset_result = subprocess.run(
            ["git", "-C", str(repo_dir), "reset", "--hard", "FETCH_HEAD"],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if reset_result.returncode == 0:
            updated += 1
        else:
            failed += 1
            warning_logger(
                f"[{config.component}] Failed to reset {repo_dir.name}: {reset_result.stderr.strip()}"
            )
    return updated, failed
