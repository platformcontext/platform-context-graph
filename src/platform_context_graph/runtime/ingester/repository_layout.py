"""Helpers for managed repository layout and filesystem repo discovery."""

from __future__ import annotations

from pathlib import Path


def managed_repository_roots(repos_dir: Path) -> list[Path]:
    """Return the shallowest managed Git checkout roots in a workspace."""

    if not repos_dir.exists():
        return []

    roots: list[Path] = []
    for git_path in sorted(repos_dir.rglob(".git")):
        repo_root = git_path.parent.resolve()
        if not git_path.exists() or not repo_root.is_dir():
            continue
        if any(parent in roots for parent in repo_root.parents):
            continue
        roots.append(repo_root)
    return roots


def discover_filesystem_repository_ids(filesystem_root: Path) -> list[str]:
    """Return repository identifiers discovered under a filesystem source root."""

    resolved_root = filesystem_root.resolve()
    repo_ids = [
        repo_root.relative_to(resolved_root).as_posix()
        for repo_root in _discover_repo_roots(resolved_root)
    ]
    return sorted(repo_ids)


def _discover_repo_roots(root: Path) -> list[Path]:
    """Recursively discover repository roots beneath ``root``."""

    if _is_repository_root(root):
        return [root]

    repo_roots: list[Path] = []
    for child in sorted(path for path in root.iterdir() if path.is_dir()):
        repo_roots.extend(_discover_repo_roots(child))
    return repo_roots


def _is_repository_root(path: Path) -> bool:
    """Return whether ``path`` should be treated as one repository root."""

    git_marker = path / ".git"
    if git_marker.exists():
        return True

    child_directories = 0
    for child in path.iterdir():
        if child.is_dir():
            child_directories += 1
            continue
        if child.name == ".DS_Store":
            continue
        return True
    return child_directories == 0


__all__ = [
    "discover_filesystem_repository_ids",
    "managed_repository_roots",
]
