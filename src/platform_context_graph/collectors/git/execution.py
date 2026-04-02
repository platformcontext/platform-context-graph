"""Path-level indexing orchestration helpers for the Git collector."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from ...utils.debug_log import emit_log_call
from .display import repository_display_name
from .discovery import resolve_repository_file_sets

EmitLogCallFn = Callable[..., None]
RepositoryDisplayNameFn = Callable[[Path], str]
ResolveRepositoryFileSetsFn = Callable[..., dict[Path, list[Path]]]
TimeMonotonicFn = Callable[[], float]


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
    emit_log_call_fn: EmitLogCallFn = emit_log_call,
    repository_display_name_fn: RepositoryDisplayNameFn = repository_display_name,
    resolve_repository_file_sets_fn: ResolveRepositoryFileSetsFn = (
        resolve_repository_file_sets
    ),
    time_monotonic_fn: TimeMonotonicFn = time.monotonic,
) -> None:
    """Index a file tree through the Tree-sitter orchestration path."""

    try:
        if path.is_file():
            files = builder._collect_supported_files(path)
            repo_root = path.parent.resolve()
            builder.add_repository_to_graph(repo_root, is_dependency)
            emit_log_call_fn(
                info_logger_fn,
                f"Indexing single path {path} ({len(files)} files)",
                event_name="index.path.started",
                extra_keys={"path": str(path), "file_count": len(files)},
            )
            git_repos: dict[Path, list[Path]] = {}
            file_to_repo: dict[Path, Path] = {}
        else:
            repo_file_sets = resolve_repository_file_sets_fn(
                builder,
                path,
                selected_repositories=None,
                pathspec_module=pathspec_module,
            )
            git_repos = repo_file_sets
            file_to_repo = {
                file_path: repo_root
                for repo_root, repo_files in repo_file_sets.items()
                for file_path in repo_files
            }
            files = [
                file_path
                for repo_root in sorted(repo_file_sets)
                for file_path in repo_file_sets[repo_root]
            ]

        scip_enabled = (
            get_config_value_fn("SCIP_INDEXER") or "false"
        ).lower() == "true"
        if scip_enabled:
            from ...tools.scip_indexer import detect_project_lang, is_scip_available

            scip_langs_str = (
                get_config_value_fn("SCIP_LANGUAGES")
                or "python,typescript,go,rust,java"
            )
            scip_languages = [
                lang.strip() for lang in scip_langs_str.split(",") if lang.strip()
            ]
            detected_lang = detect_project_lang(path, scip_languages)

            if detected_lang and is_scip_available(detected_lang):
                emit_log_call_fn(
                    info_logger_fn,
                    f"SCIP_INDEXER=true — using SCIP for language: {detected_lang}",
                    event_name="index.scip.started",
                    extra_keys={"path": str(path), "language": detected_lang},
                )
                await builder._build_graph_from_scip(
                    path,
                    is_dependency,
                    job_id,
                    detected_lang,
                )
                return
            if detected_lang:
                emit_log_call_fn(
                    warning_logger_fn,
                    f"SCIP_INDEXER=true but scip-{detected_lang} binary not found. Falling back to Tree-sitter. Install it first.",
                    event_name="index.scip.unavailable",
                    extra_keys={"path": str(path), "language": detected_lang},
                )
            else:
                emit_log_call_fn(
                    info_logger_fn,
                    "SCIP_INDEXER=true but no SCIP-supported language detected. Falling back to Tree-sitter.",
                    event_name="index.scip.unsupported",
                    extra_keys={"path": str(path)},
                )

        if job_id:
            builder.job_manager.update_job(job_id, status=job_status_enum.RUNNING)
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
            emit_log_call_fn(
                info_logger_fn,
                f"Detected {len(git_repos)} repos under {path} ({len(files)} total files). "
                f"Largest: {', '.join(f'{name}({count})' for name, count in repo_summary[:5])}",
                event_name="index.discovery.completed",
                extra_keys={
                    "path": str(path),
                    "repository_count": len(git_repos),
                    "file_count": len(files),
                },
            )
        else:
            repo_root = path if path.is_dir() else path.parent
            builder.add_repository_to_graph(repo_root, is_dependency)
            emit_log_call_fn(
                info_logger_fn,
                f"Indexing single path {path} ({len(files)} files)",
                event_name="index.path.started",
                extra_keys={"path": str(path), "file_count": len(files)},
            )

        if job_id:
            builder.job_manager.update_job(job_id, total_files=len(files))

        prescan_start = time_monotonic_fn()
        emit_log_call_fn(
            info_logger_fn,
            f"Pre-scanning {len(files)} files for imports map...",
            event_name="index.prescan.started",
            extra_keys={"path": str(path), "file_count": len(files)},
        )
        imports_map = builder._pre_scan_for_imports(files)
        prescan_elapsed = time_monotonic_fn() - prescan_start
        emit_log_call_fn(
            info_logger_fn,
            f"Pre-scan done in {prescan_elapsed:.1f}s — {len(imports_map)} definitions found",
            event_name="index.prescan.completed",
            extra_keys={
                "path": str(path),
                "definition_count": len(imports_map),
                "duration_seconds": round(prescan_elapsed, 3),
            },
        )

        all_file_data: list[dict[str, Any]] = []
        total_files = len(files)
        log_interval = max(100, total_files // 10) if total_files > 0 else 1
        index_start = time_monotonic_fn()

        current_repo_name = None
        repo_file_count = repos_completed = processed_count = 0
        total_repos = len(git_repos) if git_repos else 1
        repo_name_cache: dict[Path, str] = {}

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
            repo_name = repo_name_cache.get(repo_path)
            if repo_name is None:
                repo_name_cache[repo_path] = repo_name = repository_display_name_fn(
                    repo_path
                )

            if repo_name != current_repo_name:
                if current_repo_name is not None:
                    repos_completed += 1
                    emit_log_call_fn(
                        info_logger_fn,
                        f"Finished repo {current_repo_name} ({repo_file_count} files) [{repos_completed}/{total_repos} repos done]",
                        event_name="index.repository.completed",
                        extra_keys={
                            "repo_name": current_repo_name,
                            "repo_file_count": repo_file_count,
                            "repos_completed": repos_completed,
                            "total_repositories": total_repos,
                        },
                    )
                current_repo_name = repo_name
                repo_file_count = 0
                emit_log_call_fn(
                    info_logger_fn,
                    f"Starting repo {repo_name} [{repos_completed + 1}/{total_repos}]",
                    event_name="index.repository.started",
                    extra_keys={
                        "repo_name": repo_name,
                        "repository_index": repos_completed + 1,
                        "total_repositories": total_repos,
                    },
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
                elapsed = time_monotonic_fn() - index_start
                rate = processed_count / elapsed if elapsed > 0 else 0
                remaining = (total_files - processed_count) / rate if rate > 0 else 0
                emit_log_call_fn(
                    info_logger_fn,
                    f"Progress: {processed_count}/{total_files} files ({processed_count * 100 // total_files}%) | {rate:.0f} files/s | ~{remaining:.0f}s remaining",
                    event_name="index.parse.progress",
                    extra_keys={
                        "processed_files": processed_count,
                        "total_files": total_files,
                        "files_per_second": round(rate, 3),
                        "remaining_seconds": round(remaining, 3),
                    },
                )
            await asyncio_module.sleep(0.01)

        if current_repo_name is not None:
            repos_completed += 1
            emit_log_call_fn(
                info_logger_fn,
                f"Finished repo {current_repo_name} ({repo_file_count} files) [{repos_completed}/{total_repos} repos done]",
                event_name="index.repository.completed",
                extra_keys={
                    "repo_name": current_repo_name,
                    "repo_file_count": repo_file_count,
                    "repos_completed": repos_completed,
                    "total_repositories": total_repos,
                },
            )

        total_elapsed = time_monotonic_fn() - index_start
        emit_log_call_fn(
            info_logger_fn,
            f"File indexing complete: {processed_count}/{total_files} files across {repos_completed} repos in {total_elapsed:.1f}s ({processed_count / total_elapsed:.0f} files/s)",
            event_name="index.parse.completed",
            extra_keys={
                "processed_files": processed_count,
                "total_files": total_files,
                "repository_count": repos_completed,
                "duration_seconds": round(total_elapsed, 3),
                "files_per_second": (
                    round(processed_count / total_elapsed, 3)
                    if total_elapsed > 0
                    else 0.0
                ),
            },
        )
        emit_log_call_fn(
            info_logger_fn,
            "Creating inheritance links and function calls...",
            event_name="index.links.started",
            extra_keys={"file_count": len(all_file_data)},
        )
        link_start = time_monotonic_fn()
        builder._create_all_inheritance_links(all_file_data, imports_map)
        builder._create_all_function_calls(all_file_data, imports_map)
        builder._create_all_infra_links(all_file_data)
        builder._materialize_workloads()
        committed_repo_paths = sorted(git_repos) if git_repos else [repo_root]
        builder._resolve_repository_relationships(committed_repo_paths)
        link_elapsed = time_monotonic_fn() - link_start
        emit_log_call_fn(
            info_logger_fn,
            f"Link creation done in {link_elapsed:.1f}s",
            event_name="index.links.completed",
            extra_keys={"duration_seconds": round(link_elapsed, 3)},
        )

        if job_id:
            builder.job_manager.update_job(
                job_id,
                status=job_status_enum.COMPLETED,
                end_time=datetime_cls.now(),
            )
    except Exception as exc:
        error_message = str(exc)
        emit_log_call_fn(
            error_logger_fn,
            f"Failed to build graph for path {path}: {error_message}",
            event_name="index.path.failed",
            extra_keys={"path": str(path)},
        )
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


__all__ = ["build_graph_from_path_async"]
