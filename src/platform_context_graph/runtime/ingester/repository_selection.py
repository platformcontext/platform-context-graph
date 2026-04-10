"""Repository discovery and selection helpers for repo-sync runtimes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .config import RepoSyncConfig, RepoSyncRepositoryRule
from .config import extract_exact_repository_ids
from .github_auth import github_api_request, github_headers


@dataclass(frozen=True, slots=True)
class GitHubRepositoryRecord:
    """One GitHub repository candidate returned during org discovery."""

    repo_id: str
    archived: bool = False


@dataclass(frozen=True, slots=True)
class RepositorySelection:
    """Selected repository ids plus archived ids excluded by policy."""

    repository_ids: list[str]
    archived_repository_ids: list[str]


def discover_repository_selection(
    config: RepoSyncConfig,
    token: str | None,
) -> RepositorySelection:
    """Discover selected repository ids and archived ids excluded by policy."""

    if config.source_mode == "filesystem":
        if config.filesystem_root is None:
            raise ValueError("filesystem source mode requires PCG_FILESYSTEM_ROOT")
        if config.repositories:
            repository_ids = sorted(
                "/".join(part for part in repo.strip().strip("/").split("/") if part)
                for repo in config.repositories
                if repo.strip()
            )
            return RepositorySelection(repository_ids, [])
        from .repository_layout import discover_filesystem_repository_ids

        return RepositorySelection(
            discover_filesystem_repository_ids(config.filesystem_root),
            [],
        )

    if config.source_mode == "explicit":
        return RepositorySelection(sorted(config.repositories), [])

    if config.source_mode != "githubOrg":
        raise ValueError(f"Unsupported PCG_REPO_SOURCE_MODE={config.source_mode}")
    if not config.github_org:
        raise ValueError("githubOrg source mode requires PCG_GITHUB_ORG")
    if token is None:
        raise ValueError("githubOrg source mode requires GitHub token or App auth")

    repositories: list[GitHubRepositoryRecord] = []
    page = 1
    while len(repositories) < config.repo_limit:
        response = github_api_request(
            "get",
            f"https://api.github.com/orgs/{config.github_org}/repos",
            headers=github_headers(token),
            params={
                "per_page": min(100, config.repo_limit - len(repositories)),
                "page": page,
                "type": "all",
            },
            timeout=15,
        )
        items = response.json()
        if not items:
            break
        for item in items:
            full_name = str(item.get("full_name") or "").strip()
            if not full_name:
                continue
            repositories.append(
                GitHubRepositoryRecord(
                    repo_id=full_name,
                    archived=bool(item.get("archived")),
                )
            )
        page += 1
    return select_github_repository_ids(
        repositories=repositories[: config.repo_limit],
        repository_rules=config.repository_rules,
        include_archived_repos=config.include_archived_repos,
    )


def select_github_repository_ids(
    *,
    repositories: Iterable[GitHubRepositoryRecord],
    repository_rules: tuple[RepoSyncRepositoryRule, ...],
    include_archived_repos: bool,
) -> RepositorySelection:
    """Return selected ids and archived ids excluded by current policy."""

    exact_rule_values = set(extract_exact_repository_ids(repository_rules))
    selectable_repo_ids: list[str] = []
    archived_repository_ids: list[str] = []
    seen_selectable: set[str] = set()
    seen_archived: set[str] = set()

    for repository in repositories:
        repo_id = repository.repo_id.strip()
        if not repo_id:
            continue
        archived_allowed = include_archived_repos or repo_id in exact_rule_values
        if repository.archived and not archived_allowed:
            if repo_id not in seen_archived:
                archived_repository_ids.append(repo_id)
                seen_archived.add(repo_id)
            continue
        if repo_id not in seen_selectable:
            selectable_repo_ids.append(repo_id)
            seen_selectable.add(repo_id)

    if not repository_rules:
        return RepositorySelection(
            repository_ids=selectable_repo_ids,
            archived_repository_ids=archived_repository_ids,
        )

    selected_repository_ids = [
        repo_id
        for repo_id in selectable_repo_ids
        if any(rule.matches(repo_id) for rule in repository_rules)
    ]
    return RepositorySelection(
        repository_ids=selected_repository_ids,
        archived_repository_ids=archived_repository_ids,
    )


def archived_skip_summary(repository_ids: list[str], *, preview_limit: int = 5) -> str:
    """Return a compact archived-repository skip summary string."""

    if not repository_ids:
        return ""
    preview = ", ".join(repository_ids[:preview_limit])
    if len(repository_ids) > preview_limit:
        preview = f"{preview}, ..."
    noun = "repository" if len(repository_ids) == 1 else "repositories"
    return f"Skipping {len(repository_ids)} archived {noun}: {preview}"
