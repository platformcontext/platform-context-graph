"""Watch target planning helpers for repo-partitioned filesystem watching."""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path

VALID_WATCH_SCOPES = {"auto", "repo", "workspace"}


def watch_debounce_seconds() -> float:
    """Return the configured debounce interval for incremental watch batches."""

    raw_value = os.getenv("PCG_WATCH_DEBOUNCE_SECONDS", "2.0").strip()
    try:
        return max(0.1, min(float(raw_value), 60.0))
    except ValueError:
        return 2.0


@dataclass(slots=True)
class WatchPlan:
    """Resolved watch configuration for one requested path."""

    root_path: Path
    scope: str
    repository_paths: list[Path]


def discover_repository_roots(path: Path) -> list[Path]:
    """Return nested git repository roots under ``path``."""

    if not path.is_dir():
        return []
    return sorted(
        {git_dir.parent.resolve() for git_dir in path.rglob(".git") if git_dir.is_dir()}
    )


def matches_repository_patterns(
    repo_path: Path,
    patterns: list[str] | None,
) -> bool:
    """Return whether a repository matches any include/exclude pattern."""

    if not patterns:
        return False
    candidates = {repo_path.name, str(repo_path), repo_path.as_posix()}
    return any(
        fnmatch.fnmatch(candidate, pattern)
        for pattern in patterns
        for candidate in candidates
    )


def resolve_watch_targets(
    path: str | Path,
    *,
    scope: str = "auto",
    include_repositories: list[str] | None = None,
    exclude_repositories: list[str] | None = None,
) -> WatchPlan:
    """Resolve a watch request into repo-partitioned targets."""

    normalized_scope = scope.lower().strip()
    if normalized_scope not in VALID_WATCH_SCOPES:
        raise ValueError(
            f"Unsupported watch scope '{scope}'. Expected one of: "
            f"{', '.join(sorted(VALID_WATCH_SCOPES))}"
        )

    root_path = Path(path).resolve()
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    if not root_path.is_dir():
        raise NotADirectoryError(root_path)

    direct_repo = (root_path / ".git").exists()
    discovered_repos = discover_repository_roots(root_path)
    if direct_repo and root_path not in discovered_repos:
        discovered_repos.insert(0, root_path)

    effective_scope = normalized_scope
    if normalized_scope == "repo":
        repository_paths = [root_path]
    elif normalized_scope == "workspace":
        effective_scope = "workspace"
        repository_paths = discovered_repos or [root_path]
    elif direct_repo or not discovered_repos:
        effective_scope = "repo"
        repository_paths = [root_path]
    else:
        effective_scope = "workspace"
        repository_paths = discovered_repos

    filtered_repositories = []
    for repo_path in repository_paths:
        if include_repositories and not matches_repository_patterns(
            repo_path,
            include_repositories,
        ):
            continue
        if matches_repository_patterns(repo_path, exclude_repositories):
            continue
        filtered_repositories.append(repo_path.resolve())

    if not filtered_repositories:
        raise ValueError(
            "Watch filters excluded every repository under the target path"
        )

    return WatchPlan(
        root_path=root_path,
        scope=effective_scope,
        repository_paths=sorted(filtered_repositories),
    )


__all__ = [
    "VALID_WATCH_SCOPES",
    "WatchPlan",
    "discover_repository_roots",
    "matches_repository_patterns",
    "resolve_watch_targets",
    "watch_debounce_seconds",
]
