"""Runtime indexing execution helpers for ``GraphBuilder``."""

from __future__ import annotations

import os
import time
from heapq import heappush, heappushpop
from pathlib import Path
from typing import Any

from .graph_builder_indexing_discovery import resolve_repository_file_sets
from .graph_builder_indexing_types import RepositoryParseSnapshot
from .repository_display import repository_display_name

_REPO_PARSE_PROGRESS_MIN_FILES = 250
_REPO_PARSE_PROGRESS_TARGET_STEPS = 20
_SLOW_PARSE_FILE_THRESHOLD_SECONDS = 1.0
_SLOW_PARSE_TOP_FILES = 5


def _repo_file_parse_concurrency() -> int:
    """Return the opt-in file-level parse concurrency for one repository."""

    raw_value = os.getenv("PCG_REPO_FILE_PARSE_CONCURRENCY")
    if raw_value is None or not raw_value.strip():
        return 1
    try:
        return max(1, min(int(raw_value), 64))
    except ValueError:
        return 1


def _repo_relative_path(repo_path: Path, file_path: Path) -> str:
    """Return a repo-relative path when possible."""

    try:
        return str(file_path.resolve().relative_to(repo_path))
    except ValueError:
        return str(file_path.name)


def _record_slow_parse_file(
    slow_files: list[tuple[float, str]], elapsed_seconds: float, relative_path: str
) -> None:
    """Track the slowest parsed files without unbounded growth."""

    entry = (elapsed_seconds, relative_path)
    if len(slow_files) < _SLOW_PARSE_TOP_FILES:
        heappush(slow_files, entry)
        return
    if entry > slow_files[0]:
        heappushpop(slow_files, entry)


async def parse_repository_snapshot_async(
    builder: Any,
    repo_path: Path,
    repo_files: list[Path],
    *,
    is_dependency: bool,
    job_id: str | None,
    asyncio_module: Any,
    info_logger_fn: Any,
    progress_callback: Any | None = None,
) -> RepositoryParseSnapshot:
    """Parse one repository into an in-memory snapshot without writing state."""

    repo_path = repo_path.resolve()
    repo_label = repository_display_name(repo_path)
    info_logger_fn(f"Starting repo {repo_label} ({len(repo_files)} files)")
    repo_start = time.monotonic()
    to_thread = getattr(asyncio_module, "to_thread", None)
    info_logger_fn(
        f"Pre-scanning repo {repo_label} ({len(repo_files)} files) for imports map..."
    )
    prescan_start = time.monotonic()
    if callable(to_thread):
        imports_map = await to_thread(builder._pre_scan_for_imports, repo_files)
    else:
        imports_map = builder._pre_scan_for_imports(repo_files)
    prescan_elapsed = time.monotonic() - prescan_start
    info_logger_fn(
        f"Pre-scan repo {repo_label} done in {prescan_elapsed:.1f}s — "
        f"{len(imports_map)} definitions found"
    )
    parsed_file_data: list[dict[str, Any] | None] = [None] * len(repo_files)
    slow_files: list[tuple[float, str]] = []
    progress_every = max(
        1,
        max(
            _REPO_PARSE_PROGRESS_MIN_FILES,
            max(1, len(repo_files) // _REPO_PARSE_PROGRESS_TARGET_STEPS),
        ),
    )
    file_parse_concurrency = _repo_file_parse_concurrency()
    processed_files = 0

    async def _parse_one(
        index: int, file_path: Path
    ) -> tuple[int, Path | None, dict[str, Any] | None, float]:
        """Parse one file and return its ordered result payload."""

        if not file_path.is_file():
            return (index, None, None, 0.0)
        if callable(progress_callback):
            progress_callback(current_file=str(file_path.resolve()))
        if job_id:
            builder.job_manager.update_job(job_id, current_file=str(file_path))
        file_parse_start = time.monotonic()
        if callable(to_thread):
            file_data = await to_thread(
                builder.parse_file,
                repo_path,
                file_path,
                is_dependency,
            )
        else:
            file_data = builder.parse_file(repo_path, file_path, is_dependency)
        return (index, file_path, file_data, time.monotonic() - file_parse_start)

    def _record_parse_result(
        index: int,
        file_path: Path | None,
        file_data: dict[str, Any] | None,
        file_parse_elapsed: float,
    ) -> None:
        """Fold one completed file parse into repo-level progress telemetry."""

        nonlocal processed_files
        if file_path is None or file_data is None:
            return
        processed_files += 1
        relative_path = _repo_relative_path(repo_path, file_path)
        if file_parse_elapsed >= _SLOW_PARSE_FILE_THRESHOLD_SECONDS:
            _record_slow_parse_file(slow_files, file_parse_elapsed, relative_path)
            info_logger_fn(
                f"Slow parse file in repo {repo_label}: "
                f"{relative_path} took {file_parse_elapsed:.1f}s"
            )
        if "error" not in file_data:
            parsed_file_data[index] = file_data
        if processed_files == len(repo_files) or processed_files % progress_every == 0:
            info_logger_fn(
                f"Repo {repo_label} parse progress: "
                f"{processed_files}/{len(repo_files)} files in "
                f"{time.monotonic() - repo_start:.1f}s"
            )

    if (
        callable(to_thread)
        and file_parse_concurrency > 1
        and hasattr(asyncio_module, "Semaphore")
        and hasattr(asyncio_module, "create_task")
        and hasattr(asyncio_module, "as_completed")
    ):
        semaphore = asyncio_module.Semaphore(file_parse_concurrency)

        async def _parse_with_semaphore(
            index: int, file_path: Path
        ) -> tuple[int, Path | None, dict[str, Any] | None, float]:
            """Bound per-repo file parsing with the configured semaphore."""

            async with semaphore:
                return await _parse_one(index, file_path)

        tasks = [
            asyncio_module.create_task(_parse_with_semaphore(index, file_path))
            for index, file_path in enumerate(repo_files)
        ]
        try:
            for completed_task in asyncio_module.as_completed(tasks):
                _record_parse_result(*(await completed_task))
                await asyncio_module.sleep(0)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
    else:
        for index, file_path in enumerate(repo_files):
            _record_parse_result(*(await _parse_one(index, file_path)))
            await asyncio_module.sleep(0)

    file_data_items = [item for item in parsed_file_data if item is not None]
    if slow_files:
        slowest_summary = ", ".join(
            f"{relative_path}({elapsed_seconds:.1f}s)"
            for elapsed_seconds, relative_path in sorted(slow_files, reverse=True)
        )
        info_logger_fn(
            f"Slowest parse files in repo {repo_label}: {slowest_summary}"
        )
    total_elapsed = time.monotonic() - repo_start
    info_logger_fn(
        f"Finished repo {repo_label} ({len(file_data_items)} parsed files) "
        f"in {total_elapsed:.1f}s"
    )
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
    stage_progress_callback: Any | None = None,
) -> dict[str, float]:
    """Create cross-file and cross-repo relationships after repo commits finish."""

    all_file_data = [
        file_data
        for snapshot in snapshots
        for file_data in _snapshot_file_data(snapshot)
    ]
    info_logger_fn(
        f"Creating inheritance links and function calls for {len(all_file_data)} parsed files..."
    )
    total_start = time.monotonic()
    stage_timings: dict[str, float] = {}
    for stage_name, stage_fn in (
        (
            "inheritance",
            lambda: builder._create_all_inheritance_links(
                all_file_data, merged_imports_map
            ),
        ),
        (
            "function_calls",
            lambda: builder._create_all_function_calls(
                all_file_data, merged_imports_map
            ),
        ),
        ("infra_links", lambda: builder._create_all_infra_links(all_file_data)),
        ("workloads", builder._materialize_workloads),
    ):
        if callable(stage_progress_callback):
            stage_progress_callback(stage_name)
        stage_start = time.monotonic()
        stage_fn()
        elapsed = time.monotonic() - stage_start
        stage_timings[stage_name] = elapsed
        info_logger_fn(f"Finalization stage {stage_name} done in {elapsed:.1f}s")
    total_elapsed = time.monotonic() - total_start
    info_logger_fn(
        "Finalization timings: "
        f"inheritance={stage_timings['inheritance']:.1f}s, "
        f"function_calls={stage_timings['function_calls']:.1f}s, "
        f"infra_links={stage_timings['infra_links']:.1f}s, "
        f"workloads={stage_timings['workloads']:.1f}s, "
        f"total={total_elapsed:.1f}s"
    )
    return stage_timings


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
        if path.is_file():
            files = builder._collect_supported_files(path)
            repo_root = path.parent.resolve()
            builder.add_repository_to_graph(repo_root, is_dependency)
            info_logger_fn(f"Indexing single path {path} ({len(files)} files)")
            git_repos: dict[Path, list[Path]] = {}
            file_to_repo: dict[Path, Path] = {}
        else:
            repo_file_sets = resolve_repository_file_sets(
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
            repo_name = repository_display_name(repo_path)

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
