"""Helpers for human-readable repository labels in logs."""

from __future__ import annotations

from pathlib import Path

from ..repository_identity import git_remote_for_path, repository_metadata


def repository_display_name(repo_path: Path) -> str:
    """Return a stable, readable repository label for logs."""

    repo_path = repo_path.resolve()
    metadata = repository_metadata(
        name=repo_path.name,
        local_path=str(repo_path),
        remote_url=git_remote_for_path(repo_path),
    )
    repo_slug = str(metadata.get("repo_slug") or "").strip().strip("/")
    if repo_slug:
        return repo_slug

    for parent in repo_path.parents:
        if parent.name == "repos":
            try:
                return repo_path.relative_to(parent).as_posix()
            except ValueError:
                break
    return repo_path.name


__all__ = ["repository_display_name"]
