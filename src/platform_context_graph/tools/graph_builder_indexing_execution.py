"""Compatibility exports for the relocated Git collector execution helpers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from platform_context_graph.observability import get_observability
from platform_context_graph.utils.debug_log import emit_log_call

from ..collectors.git.execution import (
    build_graph_from_path_async as _canonical_build_graph_from_path_async,
)
from ..collectors.git.finalize import finalize_index_batch, finalize_single_repository
from ..collectors.git.parse_execution import (
    parse_repository_snapshot_async as _canonical_parse_repository_snapshot_async,
)
from .graph_builder_indexing_discovery import resolve_repository_file_sets
from .graph_builder_indexing_types import RepositoryParseSnapshot
from .parse_worker import parse_file_in_worker
from .repository_display import repository_display_name

_REPO_PARSE_PROGRESS_MIN_FILES = 250
_REPO_PARSE_PROGRESS_TARGET_STEPS = 20
_SLOW_PARSE_FILE_THRESHOLD_SECONDS = 1.0


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
) -> RepositoryParseSnapshot:
    """Compatibility wrapper for the canonical repo-parse helper."""

    return await _canonical_parse_repository_snapshot_async(
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
        emit_log_call_fn=emit_log_call,
        get_observability_fn=get_observability,
        parse_file_in_worker_fn=parse_file_in_worker,
        repository_display_name_fn=repository_display_name,
        repo_parse_progress_min_files=_REPO_PARSE_PROGRESS_MIN_FILES,
        repo_parse_progress_target_steps=_REPO_PARSE_PROGRESS_TARGET_STEPS,
        slow_parse_file_threshold_seconds=_SLOW_PARSE_FILE_THRESHOLD_SECONDS,
        time_monotonic_fn=time.monotonic,
    )


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
    """Compatibility wrapper for the canonical path-orchestration helper."""

    await _canonical_build_graph_from_path_async(
        builder,
        path,
        is_dependency,
        job_id,
        asyncio_module=asyncio_module,
        datetime_cls=datetime_cls,
        debug_log_fn=debug_log_fn,
        error_logger_fn=error_logger_fn,
        get_config_value_fn=get_config_value_fn,
        info_logger_fn=info_logger_fn,
        pathspec_module=pathspec_module,
        warning_logger_fn=warning_logger_fn,
        job_status_enum=job_status_enum,
        emit_log_call_fn=emit_log_call,
        repository_display_name_fn=repository_display_name,
        resolve_repository_file_sets_fn=resolve_repository_file_sets,
        time_monotonic_fn=time.monotonic,
    )


__all__ = [
    "RepositoryParseSnapshot",
    "build_graph_from_path_async",
    "finalize_index_batch",
    "finalize_single_repository",
    "parse_repository_snapshot_async",
]
