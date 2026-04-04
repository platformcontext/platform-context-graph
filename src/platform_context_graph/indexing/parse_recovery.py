"""Helpers for recovering from repository parse execution failures."""

from __future__ import annotations

from concurrent.futures.process import BrokenProcessPool
from pathlib import Path
from typing import Any

from platform_context_graph.utils.debug_log import emit_log_call


async def parse_repository_snapshot_with_recovery(
    *,
    parse_repository_snapshot_async_fn: Any,
    builder: Any,
    repo_path: Path,
    repo_files: list[Path],
    is_dependency: bool,
    job_id: str | None,
    asyncio_module: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
    progress_callback: Any,
    parse_executor: Any | None,
    component: str,
    mode: str,
    source: str,
    parse_workers: int,
    parse_strategy: str,
) -> tuple[Any, Any | None, str]:
    """Parse one repository, degrading to threaded parsing after pool failure.

    Args:
        parse_repository_snapshot_async_fn: Repository parse coroutine factory.
        builder: Graph builder or parse facade used by the collector.
        repo_path: Repository path being parsed.
        repo_files: Files scheduled for parsing.
        is_dependency: Whether the repository is indexed as a dependency.
        job_id: Optional job identifier for progress tracking.
        asyncio_module: Asyncio-compatible module or test double.
        info_logger_fn: Structured info logger callback.
        warning_logger_fn: Warning logger callback used for degradation notices.
        progress_callback: Repo progress callback passed into parsing.
        parse_executor: Shared process pool executor when multiprocess parsing is
            enabled.
        component: Telemetry component label.
        mode: Telemetry mode label.
        source: Telemetry source label.
        parse_workers: Configured parse worker count.
        parse_strategy: Current pipeline parse strategy label.

    Returns:
        A tuple of the parsed snapshot, the executor to use for future repos,
        and the effective parse strategy label.

    Raises:
        BrokenProcessPool: If threaded fallback is unavailable or also fails.
        Exception: Any other parse error from the repository parse coroutine.
    """

    try:
        snapshot = await parse_repository_snapshot_async_fn(
            builder,
            repo_path,
            repo_files,
            is_dependency=is_dependency,
            job_id=job_id,
            asyncio_module=asyncio_module,
            info_logger_fn=info_logger_fn,
            progress_callback=progress_callback,
            parse_executor=parse_executor,
            component=component,
            mode=mode,
            source=source,
            parse_workers=parse_workers,
        )
        return snapshot, parse_executor, parse_strategy
    except BrokenProcessPool as exc:
        if parse_executor is None:
            raise
        emit_log_call(
            warning_logger_fn,
            "Process-pool parsing failed for "
            f"{repo_path.resolve()}: {exc}. Falling back to threaded parsing "
            "for the rest of this indexing run.",
            event_name="index.parse.multiprocess.broken_pool_fallback",
            extra_keys={
                "repo_path": str(repo_path.resolve()),
                "file_count": len(repo_files),
                "parse_strategy": parse_strategy,
                "parse_workers": parse_workers,
            },
        )
        snapshot = await parse_repository_snapshot_async_fn(
            builder,
            repo_path,
            repo_files,
            is_dependency=is_dependency,
            job_id=job_id,
            asyncio_module=asyncio_module,
            info_logger_fn=info_logger_fn,
            progress_callback=progress_callback,
            parse_executor=None,
            component=component,
            mode=mode,
            source=source,
            parse_workers=parse_workers,
        )
        return snapshot, None, "threaded"
