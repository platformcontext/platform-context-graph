"""Repo-scoped ``.gitignore`` helpers for indexing discovery and watch flows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pathspec.gitignore import GitIgnoreSpec


@dataclass(frozen=True, slots=True)
class GitIgnoreFilterResult:
    """Summarize repo-local ``.gitignore`` filtering for one file set."""

    kept_files: list[Path]
    ignored_files: list[Path]


def honor_gitignore_enabled(*, get_config_value_fn: Any) -> bool:
    """Return whether repo/workspace indexing should honor repo-local `.gitignore`."""

    configured = get_config_value_fn("PCG_HONOR_GITIGNORE")
    if configured is None or not str(configured).strip():
        return True
    return str(configured).strip().lower() == "true"


def _ancestor_dirs(repo_root: Path, file_path: Path) -> list[Path]:
    """Return ancestor directories from repo root through file parent."""

    file_path = file_path.resolve()
    repo_root = repo_root.resolve()
    if file_path == repo_root:
        return [repo_root]

    parent_dir = file_path if file_path.is_dir() else file_path.parent
    if repo_root != parent_dir and repo_root not in parent_dir.parents:
        raise ValueError(f"{file_path} is not under repo root {repo_root}")

    dirs: list[Path] = []
    current = parent_dir
    while True:
        dirs.append(current)
        if current == repo_root:
            break
        current = current.parent
    dirs.reverse()
    return dirs


def _load_gitignore_spec(
    gitignore_path: Path,
    *,
    spec_cache: dict[Path, GitIgnoreSpec | None],
) -> GitIgnoreSpec | None:
    """Load and cache a ``GitIgnoreSpec`` for one `.gitignore` file."""

    resolved = gitignore_path.resolve()
    if resolved in spec_cache:
        return spec_cache[resolved]

    if not resolved.exists() or not resolved.is_file():
        spec_cache[resolved] = None
        return None

    lines = resolved.read_text(encoding="utf-8").splitlines()
    if not lines:
        spec_cache[resolved] = None
        return None

    spec = GitIgnoreSpec.from_lines(lines)
    spec_cache[resolved] = spec
    return spec


def is_gitignored_in_repo(
    repo_root: Path,
    file_path: Path,
    *,
    spec_cache: dict[Path, GitIgnoreSpec | None] | None = None,
) -> bool:
    """Return whether ``file_path`` is ignored by `.gitignore` files in ``repo_root``."""

    repo_root = repo_root.resolve()
    file_path = file_path.resolve()
    cache = spec_cache if spec_cache is not None else {}

    matched: bool | None = None
    for directory in _ancestor_dirs(repo_root, file_path):
        spec = _load_gitignore_spec(directory / ".gitignore", spec_cache=cache)
        if spec is None:
            continue
        relative_path = file_path.relative_to(directory).as_posix()
        include, index = spec._backend.match_file(relative_path)
        if index is not None:
            matched = bool(include)

    return bool(matched)


def filter_repo_gitignore_files(
    repo_root: Path,
    files: list[Path],
    *,
    get_config_value_fn: Any,
) -> GitIgnoreFilterResult:
    """Filter one repo's files through its own `.gitignore` rules only."""

    if not honor_gitignore_enabled(get_config_value_fn=get_config_value_fn):
        return GitIgnoreFilterResult(
            kept_files=sorted(path.resolve() for path in files),
            ignored_files=[],
        )

    cache: dict[Path, GitIgnoreSpec | None] = {}
    kept_files: list[Path] = []
    ignored_files: list[Path] = []
    for file_path in sorted(path.resolve() for path in files):
        if is_gitignored_in_repo(repo_root, file_path, spec_cache=cache):
            ignored_files.append(file_path)
        else:
            kept_files.append(file_path)
    return GitIgnoreFilterResult(kept_files=kept_files, ignored_files=ignored_files)


def summarize_gitignored_paths(
    repo_root: Path,
    ignored_files: list[Path],
    *,
    limit: int = 5,
) -> str:
    """Return a compact top-path summary for ignored files in one repo."""

    repo_root = repo_root.resolve()
    buckets: dict[str, int] = {}
    for file_path in ignored_files:
        relative_parts = file_path.resolve().relative_to(repo_root).parts
        bucket = relative_parts[0] if relative_parts else "."
        buckets[bucket] = buckets.get(bucket, 0) + 1
    summary = ", ".join(
        f"{name}({count})"
        for name, count in sorted(
            buckets.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    )
    return summary or "none"


__all__ = [
    "GitIgnoreFilterResult",
    "filter_repo_gitignore_files",
    "honor_gitignore_enabled",
    "is_gitignored_in_repo",
    "summarize_gitignored_paths",
]
