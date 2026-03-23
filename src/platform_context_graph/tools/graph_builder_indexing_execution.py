"""Runtime indexing execution helpers for ``GraphBuilder``."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .graph_builder_indexing_discovery import (
    _apply_ignore_spec,
    _discover_git_repositories,
    _find_pcgignore,
)
from .graph_builder_indexing_types import RepositoryParseSnapshot


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
    to_thread = getattr(asyncio_module, "to_thread", None)
    if callable(to_thread):
        imports_map = await to_thread(builder._pre_scan_for_imports, repo_files)
    else:
        imports_map = builder._pre_scan_for_imports(repo_files)
    file_data_items: list[dict[str, Any]] = []
    for file_path in repo_files:
        if not file_path.is_file():
            continue
        if job_id:
            builder.job_manager.update_job(job_id, current_file=str(file_path))
        if callable(to_thread):
            file_data = await to_thread(
                builder.parse_file,
                repo_path,
                file_path,
                is_dependency,
            )
        else:
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


def _snapshot_file_data(
    snapshot: RepositoryParseSnapshot | dict[str, Any],
) -> list[dict[str, Any]]:
    """Return parsed file data from a snapshot object or dict payload."""
    file_data = getattr(snapshot, "file_data", None)
    if file_data is not None:
        return file_data
    if isinstance(snapshot, dict):
        return list(snapshot.get("file_data", []))
    raise TypeError(f"Unsupported snapshot type: {type(snapshot)!r}")


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
        for file_data in _snapshot_file_data(snapshot)
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
