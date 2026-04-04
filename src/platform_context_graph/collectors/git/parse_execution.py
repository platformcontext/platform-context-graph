"""Repository-parse execution helpers for the Git collector."""

from __future__ import annotations

import asyncio
import os
import time
from heapq import heappush, heappushpop
from pathlib import Path
from typing import Any, Callable

from ...observability import get_observability
from ...utils.debug_log import emit_log_call
from .parse_worker import parse_file_in_worker
from .display import repository_display_name
from .types import RepositoryParseSnapshot

_REPO_PARSE_PROGRESS_MIN_FILES = 250
_REPO_PARSE_PROGRESS_TARGET_STEPS = 20
_SLOW_PARSE_FILE_THRESHOLD_SECONDS = 1.0
_SLOW_PARSE_TOP_FILES = 5

EmitLogCallFn = Callable[..., None]
RepositoryDisplayNameFn = Callable[[Path], str]
TimeMonotonicFn = Callable[[], float]


def _repo_file_parse_concurrency(
    *,
    multiprocess_enabled: bool = False,
    parse_workers: int = 1,
) -> int:
    """Return the opt-in file-level parse concurrency for one repository."""

    raw_value = os.getenv("PCG_REPO_FILE_PARSE_CONCURRENCY")
    if raw_value is None or not raw_value.strip():
        return max(1, parse_workers) if multiprocess_enabled else 1
    try:
        return max(1, min(int(raw_value), 64))
    except ValueError:
        return max(1, parse_workers) if multiprocess_enabled else 1


def _repo_relative_path(repo_path: Path, file_path: Path) -> str:
    """Return a repo-relative path when possible."""

    try:
        return str(file_path.resolve().relative_to(repo_path))
    except ValueError:
        return str(file_path.name)


def _record_slow_parse_file(
    slow_files: list[tuple[float, str]],
    elapsed_seconds: float,
    relative_path: str,
) -> None:
    """Track the slowest parsed files without unbounded growth."""

    entry = (elapsed_seconds, relative_path)
    if len(slow_files) < _SLOW_PARSE_TOP_FILES:
        heappush(slow_files, entry)
        return
    if entry > slow_files[0]:
        heappushpop(slow_files, entry)


def _repo_file_parse_multiprocess_enabled() -> bool:
    """Return whether the opt-in multiprocess parser skeleton is enabled."""

    raw_value = os.getenv("PCG_REPO_FILE_PARSE_MULTIPROCESS")
    return bool(raw_value and raw_value.strip().lower() == "true")


def _repo_file_parse_strategy(*, parse_executor: Any | None) -> str:
    """Return the effective parse strategy label for telemetry."""

    if _repo_file_parse_multiprocess_enabled() and parse_executor is not None:
        return "multiprocess"
    return "threaded"


async def _cancel_and_drain_parse_tasks(
    tasks: list[Any],
    *,
    asyncio_module: Any,
) -> None:
    """Cancel unfinished parse tasks and drain all outcomes.

    Draining the tasks prevents asyncio from logging "Task exception was never
    retrieved" when one repository parse failure leaves sibling tasks behind.
    """

    for task in tasks:
        if not task.done():
            task.cancel()

    gather = getattr(asyncio_module, "gather", None)
    if callable(gather):
        await gather(*tasks, return_exceptions=True)
        return

    for task in tasks:
        try:
            await task
        except BaseException:  # pragma: no cover - fallback for test doubles only.
            continue


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
    parse_executor: Any | None = None,
    component: str | None = None,
    mode: str | None = None,
    source: str | None = None,
    parse_workers: int = 1,
    emit_log_call_fn: EmitLogCallFn = emit_log_call,
    get_observability_fn: Callable[[], Any] = get_observability,
    parse_file_in_worker_fn: Callable[..., dict[str, Any]] = parse_file_in_worker,
    repository_display_name_fn: RepositoryDisplayNameFn = repository_display_name,
    repo_parse_progress_min_files: int = _REPO_PARSE_PROGRESS_MIN_FILES,
    repo_parse_progress_target_steps: int = _REPO_PARSE_PROGRESS_TARGET_STEPS,
    slow_parse_file_threshold_seconds: float = _SLOW_PARSE_FILE_THRESHOLD_SECONDS,
    time_monotonic_fn: TimeMonotonicFn = time.monotonic,
) -> RepositoryParseSnapshot:
    """Parse one repository into an in-memory snapshot without writing state."""

    repo_path = repo_path.resolve()
    repo_label = repository_display_name_fn(repo_path)
    telemetry = get_observability_fn()
    file_parse_strategy = _repo_file_parse_strategy(parse_executor=parse_executor)
    multiprocess_requested = _repo_file_parse_multiprocess_enabled()
    if multiprocess_requested and parse_executor is None:
        emit_log_call_fn(
            info_logger_fn,
            f"Repo {repo_label} requested multiprocess parsing but no parse executor "
            "was configured; falling back to the threaded path.",
            event_name="index.parse.multiprocess.fallback",
            extra_keys={
                "repo_path": str(repo_path),
                "file_count": len(repo_files),
                "parse_strategy": file_parse_strategy,
            },
        )
    emit_log_call_fn(
        info_logger_fn,
        f"Starting repo {repo_label} ({len(repo_files)} files)",
        event_name="index.parse.started",
        extra_keys={
            "repo_path": str(repo_path),
            "file_count": len(repo_files),
        },
    )
    repo_start = time_monotonic_fn()
    to_thread = getattr(asyncio_module, "to_thread", None)
    with telemetry.start_span(
        "pcg.index.parse_repository",
        attributes={
            "pcg.index.repo_path": str(repo_path),
            "pcg.index.file_count": len(repo_files),
            "pcg.index.file_parse_strategy": file_parse_strategy,
        },
    ):
        emit_log_call_fn(
            info_logger_fn,
            f"Pre-scanning repo {repo_label} ({len(repo_files)} files) for imports map...",
            event_name="index.prescan.started",
            extra_keys={
                "repo_path": str(repo_path),
                "file_count": len(repo_files),
            },
        )
        prescan_start = time_monotonic_fn()
        with telemetry.start_span(
            "pcg.index.prescan_repository",
            attributes={"pcg.index.repo_path": str(repo_path)},
        ):
            if callable(to_thread):
                imports_map = await to_thread(builder._pre_scan_for_imports, repo_files)
            else:
                imports_map = builder._pre_scan_for_imports(repo_files)
        prescan_elapsed = time_monotonic_fn() - prescan_start
        emit_log_call_fn(
            info_logger_fn,
            f"Pre-scan repo {repo_label} done in {prescan_elapsed:.1f}s — "
            f"{len(imports_map)} definitions found",
            event_name="index.prescan.completed",
            extra_keys={
                "repo_path": str(repo_path),
                "duration_seconds": round(prescan_elapsed, 6),
                "definition_count": len(imports_map),
            },
        )
    parsed_file_data: list[dict[str, Any] | None] = [None] * len(repo_files)
    slow_files: list[tuple[float, str]] = []
    progress_every = max(
        1,
        max(
            repo_parse_progress_min_files,
            max(1, len(repo_files) // repo_parse_progress_target_steps),
        ),
    )
    file_parse_concurrency = _repo_file_parse_concurrency(
        multiprocess_enabled=file_parse_strategy == "multiprocess",
        parse_workers=parse_workers,
    )
    processed_files = 0
    active_parse_tasks = 0

    def _set_active_parse_tasks(count: int) -> None:
        """Update the observable count of in-flight file parse tasks."""

        if (
            hasattr(telemetry, "set_index_parse_tasks_active")
            and component
            and mode
            and source
        ):
            telemetry.set_index_parse_tasks_active(
                component=component,
                mode=mode,
                source=source,
                active_count=count,
                parse_strategy=file_parse_strategy,
                parse_workers=parse_workers,
            )

    async def _parse_one(
        index: int,
        file_path: Path,
    ) -> tuple[int, Path | None, dict[str, Any] | None, float]:
        """Parse one file and return its ordered result payload."""

        if not file_path.is_file():
            return (index, None, None, 0.0)
        if callable(progress_callback):
            progress_callback(current_file=str(file_path.resolve()))
        if job_id:
            builder.job_manager.update_job(job_id, current_file=str(file_path))
        file_parse_start = time_monotonic_fn()
        if file_parse_strategy == "multiprocess" and parse_executor is not None:
            emit_log_call_fn(
                info_logger_fn,
                f"Dispatching {file_path.name} to the process-pool parser",
                event_name="index.parse.worker_handoff",
                extra_keys={
                    "repo_path": str(repo_path),
                    "file_path": str(file_path),
                    "parse_strategy": file_parse_strategy,
                    "parse_workers": parse_workers,
                    "file_parse_concurrency": file_parse_concurrency,
                },
            )
            get_running_loop = getattr(asyncio_module, "get_running_loop", None)
            running_loop = (
                get_running_loop()
                if callable(get_running_loop)
                else asyncio.get_running_loop()
            )
            file_data = await running_loop.run_in_executor(
                parse_executor,
                parse_file_in_worker_fn,
                str(repo_path),
                str(file_path),
                is_dependency,
            )
        elif callable(to_thread):
            file_data = await to_thread(
                builder.parse_file,
                repo_path,
                file_path,
                is_dependency,
            )
        else:
            file_data = builder.parse_file(repo_path, file_path, is_dependency)
        return (index, file_path, file_data, time_monotonic_fn() - file_parse_start)

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
        if file_parse_elapsed >= slow_parse_file_threshold_seconds:
            _record_slow_parse_file(slow_files, file_parse_elapsed, relative_path)
            emit_log_call_fn(
                info_logger_fn,
                f"Slow parse file in repo {repo_label}: "
                f"{relative_path} took {file_parse_elapsed:.1f}s",
                event_name="index.parse.slow_file",
                extra_keys={
                    "repo_path": str(repo_path),
                    "relative_path": relative_path,
                    "duration_seconds": round(file_parse_elapsed, 6),
                },
            )
        if "error" not in file_data:
            parsed_file_data[index] = file_data
        if processed_files == len(repo_files) or processed_files % progress_every == 0:
            emit_log_call_fn(
                info_logger_fn,
                f"Repo {repo_label} parse progress: "
                f"{processed_files}/{len(repo_files)} files in "
                f"{time_monotonic_fn() - repo_start:.1f}s",
                event_name="index.parse.progress",
                extra_keys={
                    "repo_path": str(repo_path),
                    "processed_files": processed_files,
                    "total_files": len(repo_files),
                    "duration_seconds": round(time_monotonic_fn() - repo_start, 6),
                },
            )

    emit_log_call_fn(
        info_logger_fn,
        f"Repository parse dispatch configured for {repo_label}: "
        f"strategy={file_parse_strategy}, max_in_flight={file_parse_concurrency}, "
        f"workers={parse_workers}",
        event_name="index.parse.dispatch.configured",
        extra_keys={
            "repo_path": str(repo_path),
            "parse_strategy": file_parse_strategy,
            "file_parse_concurrency": file_parse_concurrency,
            "parse_workers": parse_workers,
            "file_count": len(repo_files),
        },
    )
    _set_active_parse_tasks(0)

    if (
        (callable(to_thread) or file_parse_strategy == "multiprocess")
        and file_parse_concurrency > 1
        and hasattr(asyncio_module, "Semaphore")
        and hasattr(asyncio_module, "create_task")
        and hasattr(asyncio_module, "as_completed")
    ):
        semaphore = asyncio_module.Semaphore(file_parse_concurrency)

        async def _parse_with_semaphore(
            index: int,
            file_path: Path,
        ) -> tuple[int, Path | None, dict[str, Any] | None, float]:
            """Bound per-repo file parsing with the configured semaphore."""

            nonlocal active_parse_tasks
            async with semaphore:
                active_parse_tasks += 1
                _set_active_parse_tasks(active_parse_tasks)
                try:
                    return await _parse_one(index, file_path)
                finally:
                    active_parse_tasks -= 1
                    _set_active_parse_tasks(active_parse_tasks)

        tasks = [
            asyncio_module.create_task(_parse_with_semaphore(index, file_path))
            for index, file_path in enumerate(repo_files)
        ]
        tasks_drained = False
        try:
            for completed_task in asyncio_module.as_completed(tasks):
                _record_parse_result(*(await completed_task))
                await asyncio_module.sleep(0)
        except Exception:
            await _cancel_and_drain_parse_tasks(tasks, asyncio_module=asyncio_module)
            tasks_drained = True
            raise
        finally:
            if not tasks_drained:
                await _cancel_and_drain_parse_tasks(
                    tasks,
                    asyncio_module=asyncio_module,
                )
    else:
        for index, file_path in enumerate(repo_files):
            active_parse_tasks = 1
            _set_active_parse_tasks(active_parse_tasks)
            try:
                _record_parse_result(*(await _parse_one(index, file_path)))
                await asyncio_module.sleep(0)
            finally:
                active_parse_tasks = 0
                _set_active_parse_tasks(active_parse_tasks)
    _set_active_parse_tasks(0)

    file_data_items = [item for item in parsed_file_data if item is not None]
    if slow_files:
        slowest_summary = ", ".join(
            f"{relative_path}({elapsed_seconds:.1f}s)"
            for elapsed_seconds, relative_path in sorted(slow_files, reverse=True)
        )
        emit_log_call_fn(
            info_logger_fn,
            f"Slowest parse files in repo {repo_label}: {slowest_summary}",
            event_name="index.parse.slowest_files",
            extra_keys={
                "repo_path": str(repo_path),
                "slow_files": [
                    {
                        "relative_path": relative_path,
                        "duration_seconds": round(elapsed_seconds, 6),
                    }
                    for elapsed_seconds, relative_path in sorted(
                        slow_files,
                        reverse=True,
                    )
                ],
            },
        )
    total_elapsed = time_monotonic_fn() - repo_start
    emit_log_call_fn(
        info_logger_fn,
        f"Finished repo {repo_label} ({len(file_data_items)} parsed files) "
        f"in {total_elapsed:.1f}s",
        event_name="index.parse.completed",
        extra_keys={
            "repo_path": str(repo_path),
            "parsed_file_count": len(file_data_items),
            "duration_seconds": round(total_elapsed, 6),
            "parse_strategy": file_parse_strategy,
            "parse_workers": parse_workers,
        },
    )
    return RepositoryParseSnapshot(
        repo_path=str(repo_path),
        file_count=len(repo_files),
        imports_map=imports_map,
        file_data=file_data_items,
    )


__all__ = [
    "parse_repository_snapshot_async",
    "RepositoryParseSnapshot",
]
