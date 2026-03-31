"""File discovery helpers for graph-builder indexing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..cli.config_manager import get_config_value
from ..utils.debug_log import info_logger
from .dependency_catalog import dependency_ignore_enabled, is_dependency_path
from .graph_builder_gitignore import (
    filter_repo_gitignore_files,
    summarize_gitignored_paths,
)
from .repository_display import repository_display_name


def estimate_processing_time(
    builder: Any, path: Path, *, error_logger_fn: Any
) -> tuple[int, float] | None:
    """Estimate indexing duration based on supported file count.

    Args:
        builder: ``GraphBuilder`` facade instance.
        path: File or directory slated for indexing.
        error_logger_fn: Error logger callable.

    Returns:
        A ``(file_count, estimated_seconds)`` tuple or ``None`` if discovery failed.
    """
    try:
        repo_file_sets = resolve_repository_file_sets(
            builder,
            path,
            selected_repositories=None,
            pathspec_module=__import__("pathspec"),
        )
        total_files = sum(len(files) for files in repo_file_sets.values())
        estimated_time = total_files * 0.05
        return total_files, estimated_time
    except Exception as exc:
        error_logger_fn(f"Could not estimate processing time for {path}: {exc}")
        return None


def get_ignored_dir_names(*, get_config_value_fn: Any) -> set[str]:
    """Resolve the configured list of ignored directory names.

    Args:
        get_config_value_fn: Runtime config resolver.

    Returns:
        Lower-cased directory names that should be skipped during file discovery.
    """
    ignore_dirs_str = get_config_value_fn("IGNORE_DIRS") or ""
    return {
        directory.strip().lower()
        for directory in ignore_dirs_str.split(",")
        if directory.strip()
    }


def ignore_hidden_files(*, get_config_value_fn: Any) -> bool:
    """Return whether hidden files and directories should be skipped."""

    raw_value = str(get_config_value_fn("IGNORE_HIDDEN_FILES") or "true").strip()
    return raw_value.lower() != "false"


def collect_supported_files(
    builder: Any,
    path: Path,
    *,
    get_config_value_fn: Any,
    get_observability_fn: Any,
    os_module: Any,
) -> list[Path]:
    """Collect files with supported parser extensions while skipping ignored dirs.

    Args:
        builder: ``GraphBuilder`` facade instance.
        path: File or directory to scan.
        get_config_value_fn: Runtime config resolver.
        get_observability_fn: Observability accessor.
        os_module: ``os`` module used for walking the filesystem.

    Returns:
        Supported file paths rooted at ``path``.
    """
    from .graph_builder_raw_text import parser_key_for_path

    dependency_exclusion_enabled = dependency_ignore_enabled(
        get_config_value_fn=get_config_value_fn
    )
    ignore_hidden = ignore_hidden_files(get_config_value_fn=get_config_value_fn)

    if path.is_file():
        if dependency_exclusion_enabled and _is_dependency_relative_to(
            path, root=path.parent
        ):
            return []
        return [path] if parser_key_for_path(path, builder.parsers) else []

    ignore_dirs = get_ignored_dir_names(get_config_value_fn=get_config_value_fn)
    telemetry = get_observability_fn()
    files: list[Path] = []
    for root, dirs, filenames in os_module.walk(path):
        root_path = Path(root)
        kept_dirs = []
        for directory in sorted(dirs):
            candidate_dir = root_path / directory
            if dependency_exclusion_enabled and _is_dependency_relative_to(
                candidate_dir, root=path
            ):
                telemetry.record_hidden_directory_skip(directory.lower())
                continue
            if directory.lower() in ignore_dirs:
                telemetry.record_hidden_directory_skip(directory.lower())
                continue
            if ignore_hidden and directory.startswith("."):
                telemetry.record_hidden_directory_skip("hidden")
                continue
            kept_dirs.append(directory)
        dirs[:] = kept_dirs
        for filename in sorted(filenames):
            file_path = root_path / filename
            if dependency_exclusion_enabled and _is_dependency_relative_to(
                file_path, root=path
            ):
                continue
            if parser_key_for_path(file_path, builder.parsers):
                files.append(file_path)
    return files


def _is_dependency_relative_to(candidate: Path, *, root: Path) -> bool:
    """Return whether a candidate is under a dependency root relative to ``root``."""

    try:
        relative_path = candidate.relative_to(root)
    except ValueError:
        return is_dependency_path(candidate)
    if relative_path == Path("."):
        return False
    return is_dependency_path(relative_path)


def _find_pcgignore(
    path: Path, *, debug_log_fn: Any, pathspec_module: Any
) -> tuple[Any, Path]:
    """Search upward for ``.pcgignore`` and build a matching spec if found.

    Args:
        path: Root path being indexed.
        debug_log_fn: Debug logger callable.
        pathspec_module: Imported ``pathspec`` module.

    Returns:
        A tuple of ``(spec_or_none, ignore_root)``.
    """
    pcgignore_path = None
    ignore_root = path.resolve()
    current = path.resolve()
    if not current.is_dir():
        current = current.parent

    while True:
        candidate = current / ".pcgignore"
        if candidate.exists():
            pcgignore_path = candidate
            ignore_root = current
            debug_log_fn(f"Found .pcgignore at {ignore_root}")
            break
        if current.parent == current:
            break
        current = current.parent

    if pcgignore_path:
        with open(pcgignore_path) as handle:
            ignore_patterns = handle.read().splitlines()
        return (
            pathspec_module.PathSpec.from_lines("gitwildmatch", ignore_patterns),
            ignore_root,
        )

    return None, ignore_root


def _apply_ignore_spec(
    files: list[Path],
    spec: Any,
    ignore_root: Path,
    *,
    debug_log_fn: Any,
) -> list[Path]:
    """Filter discovered files through a ``.pcgignore`` spec.

    Args:
        files: Candidate files gathered from the filesystem walk.
        spec: ``pathspec.PathSpec`` instance or ``None``.
        ignore_root: Root directory used for relative ignore matching.
        debug_log_fn: Debug logger callable.

    Returns:
        Filtered file paths after ignore rules are applied.
    """
    if not spec:
        return files

    filtered_files: list[Path] = []
    for file_path in files:
        try:
            rel_path = file_path.relative_to(ignore_root)
            if not spec.match_file(str(rel_path)):
                filtered_files.append(file_path)
            else:
                debug_log_fn(f"Ignored file based on .pcgignore: {rel_path}")
        except ValueError:
            filtered_files.append(file_path)
    return filtered_files


def _discover_git_repositories(
    path: Path, files: list[Path]
) -> tuple[dict[Path, list[Path]], dict[Path, Path]]:
    """Group discovered files by their nearest git repository root.

    Args:
        path: Root path being indexed.
        files: Candidate files after ignore processing.

    Returns:
        Tuple of ``(git_repos, file_to_repo)`` mappings.
    """
    git_repos: dict[Path, list[Path]] = {}
    file_to_repo: dict[Path, Path] = {}
    dir_to_repo_cache: dict[Path, Path | None] = {}

    if not path.is_dir():
        return git_repos, file_to_repo

    for file_path in files:
        start_dir = file_path.parent
        if start_dir in dir_to_repo_cache:
            repo_root = dir_to_repo_cache[start_dir]
            if repo_root is not None:
                git_repos.setdefault(repo_root, []).append(file_path)
                file_to_repo[file_path] = repo_root
            else:
                git_repos.setdefault(path, []).append(file_path)
                file_to_repo[file_path] = path
            continue

        candidate = start_dir
        walked: list[Path] = []
        found = False
        while candidate != path.parent:
            if candidate in dir_to_repo_cache:
                cached = dir_to_repo_cache[candidate]
                for walked_dir in walked:
                    dir_to_repo_cache[walked_dir] = cached
                if cached is not None:
                    git_repos.setdefault(cached, []).append(file_path)
                    file_to_repo[file_path] = cached
                else:
                    git_repos.setdefault(path, []).append(file_path)
                    file_to_repo[file_path] = path
                found = True
                break

            walked.append(candidate)
            if (candidate / ".git").exists():
                for walked_dir in walked:
                    dir_to_repo_cache[walked_dir] = candidate
                git_repos.setdefault(candidate, []).append(file_path)
                file_to_repo[file_path] = candidate
                found = True
                break
            candidate = candidate.parent

        if not found:
            for walked_dir in walked:
                dir_to_repo_cache[walked_dir] = None
            git_repos.setdefault(path, []).append(file_path)
            file_to_repo[file_path] = path

    return git_repos, file_to_repo


def merge_import_maps(
    target: dict[str, list[str]],
    source: dict[str, list[str]],
) -> None:
    """Merge one imports map into another while preserving uniqueness."""

    for symbol, paths in source.items():
        existing = target.setdefault(symbol, [])
        for path in paths:
            if path not in existing:
                existing.append(path)


def find_pcgignore(
    path: Path,
    *,
    debug_log_fn: Any,
    pathspec_module: Any,
) -> tuple[Any, Path]:
    """Public wrapper for ``.pcgignore`` discovery."""

    return _find_pcgignore(
        path,
        debug_log_fn=debug_log_fn,
        pathspec_module=pathspec_module,
    )


def apply_ignore_spec(
    files: list[Path],
    spec: Any,
    ignore_root: Path,
    *,
    debug_log_fn: Any,
) -> list[Path]:
    """Public wrapper for ignore-spec filtering."""

    return _apply_ignore_spec(
        files,
        spec,
        ignore_root,
        debug_log_fn=debug_log_fn,
    )


def discover_git_repositories(
    path: Path, files: list[Path]
) -> tuple[dict[Path, list[Path]], dict[Path, Path]]:
    """Public wrapper for grouping files by repository root."""

    return _discover_git_repositories(path, files)


def discover_index_files(
    builder: Any,
    path: Path,
    *,
    pathspec_module: Any,
    debug_log_fn: Any,
) -> tuple[list[Path], Any, Path]:
    """Collect supported files under one path after applying ``.pcgignore``."""

    spec, ignore_root = _find_pcgignore(
        path,
        debug_log_fn=debug_log_fn,
        pathspec_module=pathspec_module,
    )
    files = builder._collect_supported_files(path)
    filtered_files = _apply_ignore_spec(
        files,
        spec,
        ignore_root,
        debug_log_fn=debug_log_fn,
    )
    if path.is_dir() and (path / ".git").exists():
        gitignore_result = filter_repo_gitignore_files(
            path.resolve(),
            filtered_files,
            get_config_value_fn=get_config_value,
        )
        return gitignore_result.kept_files, spec, ignore_root
    return filtered_files, spec, ignore_root


def resolve_repository_file_sets(
    builder: Any,
    path: Path,
    *,
    selected_repositories: list[Path] | tuple[Path, ...] | None,
    pathspec_module: Any,
) -> dict[Path, list[Path]]:
    """Return repository roots mapped to their supported files."""

    if selected_repositories:
        resolved: dict[Path, list[Path]] = {}
        for repo_path in sorted({repo.resolve() for repo in selected_repositories}):
            raw_files = builder._collect_supported_files(repo_path)
            spec, ignore_root = _find_pcgignore(
                repo_path,
                debug_log_fn=lambda *_args, **_kwargs: None,
                pathspec_module=pathspec_module,
            )
            files = _apply_ignore_spec(
                raw_files,
                spec,
                ignore_root,
                debug_log_fn=lambda *_args, **_kwargs: None,
            )
            gitignore_result = filter_repo_gitignore_files(
                repo_path.resolve(),
                files,
                get_config_value_fn=get_config_value,
            )
            info_logger(
                f"Repository discovery {repository_display_name(repo_path)}: "
                f"supported={len(raw_files)} "
                f"pcgignore_excluded={len(raw_files) - len(files)} "
                f"gitignore_excluded={len(gitignore_result.ignored_files)} "
                f"external_excluded={len(gitignore_result.external_files)} "
                f"indexed={len(gitignore_result.kept_files)} "
                f"gitignore_top={summarize_gitignored_paths(repo_path, gitignore_result.ignored_files)}"
            )
            resolved[repo_path] = gitignore_result.kept_files
        return resolved

    raw_files = builder._collect_supported_files(path)
    raw_git_repos, _ = _discover_git_repositories(path, raw_files)
    spec, ignore_root = _find_pcgignore(
        path,
        debug_log_fn=lambda *_args, **_kwargs: None,
        pathspec_module=pathspec_module,
    )
    files = _apply_ignore_spec(
        raw_files,
        spec,
        ignore_root,
        debug_log_fn=lambda *_args, **_kwargs: None,
    )
    git_repos, _file_to_repo = _discover_git_repositories(path, files)
    if git_repos:
        resolved: dict[Path, list[Path]] = {}
        for repo_root, repo_files in sorted(git_repos.items()):
            raw_repo_files = raw_git_repos.get(repo_root, [])
            gitignore_result = filter_repo_gitignore_files(
                repo_root.resolve(),
                repo_files,
                get_config_value_fn=get_config_value,
            )
            info_logger(
                f"Repository discovery {repository_display_name(repo_root)}: "
                f"supported={len(raw_repo_files)} "
                f"pcgignore_excluded={len(raw_repo_files) - len(repo_files)} "
                f"gitignore_excluded={len(gitignore_result.ignored_files)} "
                f"external_excluded={len(gitignore_result.external_files)} "
                f"indexed={len(gitignore_result.kept_files)} "
                f"gitignore_top={summarize_gitignored_paths(repo_root, gitignore_result.ignored_files)}"
            )
            resolved[repo_root.resolve()] = gitignore_result.kept_files
        return resolved
    repo_root = path.resolve() if path.is_dir() else path.resolve().parent
    gitignore_result = filter_repo_gitignore_files(
        repo_root,
        files,
        get_config_value_fn=get_config_value,
    )
    info_logger(
        f"Repository discovery {repository_display_name(repo_root)}: "
        f"supported={len(raw_files)} "
        f"pcgignore_excluded={len(raw_files) - len(files)} "
        f"gitignore_excluded={len(gitignore_result.ignored_files)} "
        f"external_excluded={len(gitignore_result.external_files)} "
        f"indexed={len(gitignore_result.kept_files)} "
        f"gitignore_top={summarize_gitignored_paths(repo_root, gitignore_result.ignored_files)}"
    )
    return {repo_root: gitignore_result.kept_files}
