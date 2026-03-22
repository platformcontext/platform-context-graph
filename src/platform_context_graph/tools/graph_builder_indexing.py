"""Indexing orchestration and file discovery helpers for ``GraphBuilder``."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RepositoryParseSnapshot:
    """In-memory parsed representation for one repository."""

    repo_path: str
    file_count: int
    imports_map: dict[str, list[str]]
    file_data: list[dict[str, Any]]


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
        files = builder._collect_supported_files(path)
        total_files = len(files)
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
    supported_extensions = set(builder.parsers.keys())
    if path.is_file():
        return [path] if path.suffix in supported_extensions else []

    ignore_dirs = get_ignored_dir_names(get_config_value_fn=get_config_value_fn)
    telemetry = get_observability_fn()
    files: list[Path] = []
    for root, dirs, filenames in os_module.walk(path):
        kept_dirs = []
        for directory in sorted(dirs):
            if directory.lower() in ignore_dirs:
                telemetry.record_hidden_directory_skip(directory.lower())
                continue
            if directory.startswith("."):
                telemetry.record_hidden_directory_skip("hidden")
                continue
            kept_dirs.append(directory)
        dirs[:] = kept_dirs
        for filename in sorted(filenames):
            file_path = Path(root) / filename
            if file_path.suffix in supported_extensions:
                files.append(file_path)
    return files


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
    return _apply_ignore_spec(
        files,
        spec,
        ignore_root,
        debug_log_fn=debug_log_fn,
    ), spec, ignore_root


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
            files, _spec, _ignore_root = discover_index_files(
                builder,
                repo_path,
                pathspec_module=pathspec_module,
                debug_log_fn=lambda *_args, **_kwargs: None,
            )
            resolved[repo_path] = files
        return resolved

    files, _spec, _ignore_root = discover_index_files(
        builder,
        path,
        pathspec_module=pathspec_module,
        debug_log_fn=lambda *_args, **_kwargs: None,
    )
    git_repos, _file_to_repo = _discover_git_repositories(path, files)
    if git_repos:
        return {repo_root.resolve(): repo_files for repo_root, repo_files in git_repos.items()}
    repo_root = path.resolve() if path.is_dir() else path.resolve().parent
    return {repo_root: files}


async def parse_repository_snapshot_async(
    builder: Any,
    repo_path: Path,
    repo_files: list[Path],
    *,
    is_dependency: bool,
    job_id: str | None,
    asyncio_module: Any,
    info_logger_fn: Any,
) -> RepositoryParseSnapshot:
    """Parse one repository into an in-memory snapshot without writing state."""

    repo_path = repo_path.resolve()
    info_logger_fn(f"Starting repo {repo_path.name} ({len(repo_files)} files)")
    imports_map = builder._pre_scan_for_imports(repo_files)
    file_data_items: list[dict[str, Any]] = []
    for file_path in repo_files:
        if not file_path.is_file():
            continue
        if job_id:
            builder.job_manager.update_job(job_id, current_file=str(file_path))
        file_data = builder.parse_file(repo_path, file_path, is_dependency)
        if "error" not in file_data:
            file_data_items.append(file_data)
        await asyncio_module.sleep(0.01)
    info_logger_fn(f"Finished repo {repo_path.name} ({len(file_data_items)} parsed files)")
    return RepositoryParseSnapshot(
        repo_path=str(repo_path),
        file_count=len(repo_files),
        imports_map=imports_map,
        file_data=file_data_items,
    )


def finalize_index_batch(
    builder: Any,
    *,
    snapshots: list[RepositoryParseSnapshot | Any],
    merged_imports_map: dict[str, list[str]],
    info_logger_fn: Any,
) -> None:
    """Create cross-file and cross-repo relationships after repo commits finish."""

    all_file_data = [
        file_data
        for snapshot in snapshots
        for file_data in getattr(snapshot, "file_data", snapshot["file_data"])
    ]
    info_logger_fn("Creating inheritance links and function calls...")
    link_start = time.monotonic()
    builder._create_all_inheritance_links(all_file_data, merged_imports_map)
    builder._create_all_function_calls(all_file_data, merged_imports_map)
    builder._create_all_infra_links(all_file_data)
    builder._materialize_workloads()
    link_elapsed = time.monotonic() - link_start
    info_logger_fn(f"Link creation done in {link_elapsed:.1f}s")


async def build_graph_from_path_async(
    builder: Any,
    path: Path,
    is_dependency: bool,
    job_id: str | None,
    *,
    asyncio_module: Any,
    datetime_cls: Any,
    debug_log_fn: Any,
    error_logger_fn: Any,
    get_config_value_fn: Any,
    info_logger_fn: Any,
    pathspec_module: Any,
    warning_logger_fn: Any,
    job_status_enum: Any,
) -> None:
    """Index a file tree through the Tree-sitter orchestration path.

    Args:
        builder: ``GraphBuilder`` facade instance.
        path: File or directory to index.
        is_dependency: Whether the path is being indexed as a dependency.
        job_id: Optional background job identifier.
        asyncio_module: Asyncio module used for cooperative yielding.
        datetime_cls: ``datetime`` class used for timestamps.
        debug_log_fn: Debug logger callable.
        error_logger_fn: Error logger callable.
        get_config_value_fn: Runtime config resolver.
        info_logger_fn: Info logger callable.
        pathspec_module: Imported ``pathspec`` module.
        warning_logger_fn: Warning logger callable.
        job_status_enum: Job status enum with terminal states.
    """
    try:
        scip_enabled = (
            get_config_value_fn("SCIP_INDEXER") or "false"
        ).lower() == "true"
        if scip_enabled:
            from .scip_indexer import detect_project_lang, is_scip_available

            scip_langs_str = (
                get_config_value_fn("SCIP_LANGUAGES")
                or "python,typescript,go,rust,java"
            )
            scip_languages = [
                lang.strip() for lang in scip_langs_str.split(",") if lang.strip()
            ]
            detected_lang = detect_project_lang(path, scip_languages)

            if detected_lang and is_scip_available(detected_lang):
                info_logger_fn(
                    f"SCIP_INDEXER=true — using SCIP for language: {detected_lang}"
                )
                await builder._build_graph_from_scip(
                    path, is_dependency, job_id, detected_lang
                )
                return
            if detected_lang:
                warning_logger_fn(
                    f"SCIP_INDEXER=true but scip-{detected_lang} binary not found. Falling back to Tree-sitter. Install it first."
                )
            else:
                info_logger_fn(
                    "SCIP_INDEXER=true but no SCIP-supported language detected. Falling back to Tree-sitter."
                )

        if job_id:
            builder.job_manager.update_job(job_id, status=job_status_enum.RUNNING)

        spec, ignore_root = _find_pcgignore(
            path, debug_log_fn=debug_log_fn, pathspec_module=pathspec_module
        )
        files = builder._collect_supported_files(path)
        files = _apply_ignore_spec(files, spec, ignore_root, debug_log_fn=debug_log_fn)

        git_repos, file_to_repo = _discover_git_repositories(path, files)
        if git_repos:
            for repo_root in git_repos:
                builder.add_repository_to_graph(repo_root, is_dependency)
            repo_summary = sorted(
                (
                    (repo_root.name, len(file_list))
                    for repo_root, file_list in git_repos.items()
                ),
                key=lambda item: -item[1],
            )
            info_logger_fn(
                f"Detected {len(git_repos)} repos under {path} ({len(files)} total files). "
                f"Largest: {', '.join(f'{name}({count})' for name, count in repo_summary[:5])}"
            )
        else:
            repo_root = path if path.is_dir() else path.parent
            builder.add_repository_to_graph(repo_root, is_dependency)
            info_logger_fn(f"Indexing single path {path} ({len(files)} files)")

        if job_id:
            builder.job_manager.update_job(job_id, total_files=len(files))

        prescan_start = time.monotonic()
        info_logger_fn(f"Pre-scanning {len(files)} files for imports map...")
        imports_map = builder._pre_scan_for_imports(files)
        prescan_elapsed = time.monotonic() - prescan_start
        info_logger_fn(
            f"Pre-scan done in {prescan_elapsed:.1f}s — {len(imports_map)} definitions found"
        )

        all_file_data: list[dict[str, Any]] = []
        total_files = len(files)
        log_interval = max(100, total_files // 10) if total_files > 0 else 1
        index_start = time.monotonic()

        current_repo_name = None
        repo_file_count = 0
        repos_completed = 0
        total_repos = len(git_repos) if git_repos else 1
        processed_count = 0

        for file_path in files:
            if not file_path.is_file():
                continue

            if job_id:
                builder.job_manager.update_job(job_id, current_file=str(file_path))

            file_git_repo = file_to_repo.get(file_path)
            repo_path = (
                file_git_repo.resolve()
                if file_git_repo
                else (
                    file_path.parent.resolve() if not path.is_dir() else path.resolve()
                )
            )
            repo_name = repo_path.name

            if repo_name != current_repo_name:
                if current_repo_name is not None:
                    repos_completed += 1
                    info_logger_fn(
                        f"Finished repo {current_repo_name} ({repo_file_count} files) [{repos_completed}/{total_repos} repos done]"
                    )
                current_repo_name = repo_name
                repo_file_count = 0
                info_logger_fn(
                    f"Starting repo {repo_name} [{repos_completed + 1}/{total_repos}]"
                )

            file_data = builder.parse_file(repo_path, file_path, is_dependency)
            if "error" not in file_data:
                builder.add_file_to_graph(file_data, repo_name, imports_map)
                all_file_data.append(file_data)

            processed_count += 1
            repo_file_count += 1
            if job_id:
                builder.job_manager.update_job(job_id, processed_files=processed_count)

            if processed_count % log_interval == 0:
                elapsed = time.monotonic() - index_start
                rate = processed_count / elapsed if elapsed > 0 else 0
                remaining = (total_files - processed_count) / rate if rate > 0 else 0
                info_logger_fn(
                    f"Progress: {processed_count}/{total_files} files ({processed_count * 100 // total_files}%) | {rate:.0f} files/s | ~{remaining:.0f}s remaining"
                )
            await asyncio_module.sleep(0.01)

        if current_repo_name is not None:
            repos_completed += 1
            info_logger_fn(
                f"Finished repo {current_repo_name} ({repo_file_count} files) [{repos_completed}/{total_repos} repos done]"
            )

        total_elapsed = time.monotonic() - index_start
        info_logger_fn(
            f"File indexing complete: {processed_count}/{total_files} files across {repos_completed} repos in {total_elapsed:.1f}s ({processed_count / total_elapsed:.0f} files/s)"
        )
        info_logger_fn("Creating inheritance links and function calls...")
        link_start = time.monotonic()
        builder._create_all_inheritance_links(all_file_data, imports_map)
        builder._create_all_function_calls(all_file_data, imports_map)
        builder._create_all_infra_links(all_file_data)
        builder._materialize_workloads()
        link_elapsed = time.monotonic() - link_start
        info_logger_fn(f"Link creation done in {link_elapsed:.1f}s")

        if job_id:
            builder.job_manager.update_job(
                job_id,
                status=job_status_enum.COMPLETED,
                end_time=datetime_cls.now(),
            )
    except Exception as exc:
        error_message = str(exc)
        error_logger_fn(f"Failed to build graph for path {path}: {error_message}")
        if job_id:
            if (
                "no such file found" in error_message
                or "deleted" in error_message
                or "not found" in error_message
            ):
                status = job_status_enum.CANCELLED
            else:
                status = job_status_enum.FAILED

            builder.job_manager.update_job(
                job_id,
                status=status,
                end_time=datetime_cls.now(),
                errors=[str(exc)],
            )


__all__ = [
    "RepositoryParseSnapshot",
    "apply_ignore_spec",
    "build_graph_from_path_async",
    "collect_supported_files",
    "discover_git_repositories",
    "discover_index_files",
    "estimate_processing_time",
    "finalize_index_batch",
    "find_pcgignore",
    "get_ignored_dir_names",
    "merge_import_maps",
    "parse_repository_snapshot_async",
    "resolve_repository_file_sets",
]
