"""Async repository snapshot commit with per-batch event-loop yielding.

When ``PCG_ASYNC_COMMIT_ENABLED=true``, the commit pipeline dispatches
each file batch to a single-thread executor via ``run_in_executor``,
yielding to the asyncio event loop between batches.  This allows
multiple commit workers (``PCG_COMMIT_WORKERS>1``) to make real
progress in parallel rather than serialising behind the GIL.

When ``process_executor`` is provided (``PCG_COMMIT_WORKERS>1``), each
batch is dispatched to a child process via ``commit_batch_in_process``,
giving each worker its own GIL and avoiding CPU-bound starvation.

The sync persistence code (``commit_file_batch_to_graph``) is reused
as-is — no async Neo4j driver is required.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..repository_identity import git_remote_for_path, repository_metadata
from ..utils.debug_log import emit_log_call, warning_logger
from .commit_timing import CommitTimingResult
from .coordinator_models import RepositorySnapshot
from .coordinator_storage import _graph_store_adapter

from ..tools.graph_builder_persistence_worker import commit_batch_in_process

logger = logging.getLogger(__name__)

_ASYNC_COMMIT_ENABLED: bool = (
    os.environ.get("PCG_ASYNC_COMMIT_ENABLED", "false").lower() == "true"
)


def _positive_int_env(name: str, default: int, *, maximum: int = 128) -> int:
    """Return a bounded positive integer from the environment."""
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        return max(1, min(int(raw_value), maximum))
    except ValueError:
        return default


def _normalize_result(
    commit_result: Any,
    batch: list[dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return committed and failed file paths from one builder batch result."""
    if commit_result is None:
        return tuple(str(Path(item["path"]).resolve()) for item in batch), ()
    committed = tuple(getattr(commit_result, "committed_file_paths", ()) or ())
    failed = tuple(getattr(commit_result, "failed_file_paths", ()) or ())
    return committed, failed


def _sync_setup_repo(
    builder: Any,
    snapshot: RepositorySnapshot,
    repo_path: Path,
    is_dependency: bool,
) -> None:
    """Run the synchronous repo setup (delete old data + add repo node).

    This must execute on the same thread that will later run batch
    commits, because the Neo4j session is not thread-safe.
    """
    graph_store = _graph_store_adapter(builder)
    metadata = repository_metadata(
        name=repo_path.name,
        local_path=str(repo_path),
        remote_url=git_remote_for_path(repo_path),
    )

    try:
        graph_store.delete_repository(metadata["id"])
    except Exception as exc:
        emit_log_call(
            warning_logger,
            "Failed to delete repository from graph store",
            event_name="index.async_commit.graph_delete_failed",
            extra_keys={"repo_id": metadata["id"], "error": str(exc)},
            exc_info=exc,
        )
        raise

    content_provider = getattr(builder, "_content_provider", None)
    if content_provider is None:
        from platform_context_graph.content.state import get_postgres_content_provider

        content_provider = get_postgres_content_provider()
        builder._content_provider = content_provider

    if content_provider is not None and content_provider.enabled:
        content_provider.delete_repository_content(metadata["id"])

    builder.add_repository_to_graph(repo_path, is_dependency=is_dependency)


def _accumulate_timing(
    timing: CommitTimingResult,
    commit_result: Any,
    batch: list[dict[str, Any]],
    duration: float,
) -> None:
    """Fold one batch result into the accumulated timing."""
    timing.accumulate_graph_batch(duration_seconds=duration, row_count=len(batch))
    if commit_result is None:
        return
    result_entity_totals = getattr(commit_result, "entity_totals", None)
    if result_entity_totals:
        timing.merge_entity_totals(result_entity_totals)
    if hasattr(commit_result, "content_write_duration_seconds"):
        timing.content_write_duration_seconds += (
            commit_result.content_write_duration_seconds
        )
        timing.content_batch_count += (
            getattr(commit_result, "content_batch_count", 0) or 0
        )


async def commit_repository_snapshot_async(
    builder: Any,
    snapshot: RepositorySnapshot,
    *,
    is_dependency: bool,
    progress_callback: Any | None = None,
    iter_snapshot_file_data_batches_fn: Any | None = None,
    repo_class: str | None = None,
    process_executor: Any | None = None,
    connection_params: dict[str, str | None] | None = None,
) -> CommitTimingResult:
    """Async commit that yields to the event loop between file batches.

    Each file-batch commit runs synchronously on a dedicated executor.
    When ``process_executor`` is provided, batches dispatch to child
    processes for true parallelism. Otherwise, uses ThreadPoolExecutor
    for backward compatibility.

    Args:
        builder: GraphBuilder instance.
        snapshot: Parsed repository snapshot to commit.
        is_dependency: Whether the repo is a dependency.
        progress_callback: Optional progress reporter.
        iter_snapshot_file_data_batches_fn: NDJSON batch iterator factory.
        repo_class: Repo classification for adaptive batch sizing.
        process_executor: Optional ProcessPoolExecutor for multi-worker parallelism.
        connection_params: Connection parameters for child process workers.

    Returns:
        Accumulated ``CommitTimingResult`` across all batches.
    """
    from .adaptive_batch_config import resolve_batch_config

    batch_config = resolve_batch_config(repo_class=repo_class)
    repo_path = Path(snapshot.repo_path).resolve()

    loop = asyncio.get_running_loop()

    # Always use asyncio.to_thread for repo setup (needs builder's driver)
    await asyncio.to_thread(
        _sync_setup_repo,
        builder,
        snapshot,
        repo_path,
        is_dependency,
    )

    # Choose executor based on whether ProcessPoolExecutor is provided
    use_process_pool = process_executor is not None and connection_params is not None
    executor = (
        None
        if use_process_pool
        else ThreadPoolExecutor(max_workers=1, thread_name_prefix="pcg-async-commit")
    )

    try:

        batch_size = min(
            batch_config.file_batch_size,
            _positive_int_env("PCG_FILE_BATCH_SIZE", 50, maximum=512),
        )
        total_files = snapshot.file_count or len(snapshot.file_data)
        committed_files = 0
        timing = CommitTimingResult()

        commit_kwargs: dict[str, Any] = {
            "adaptive_flush_threshold": batch_config.flush_row_threshold,
            "adaptive_entity_batch_size": batch_config.entity_batch_size,
            "adaptive_tx_file_limit": batch_config.tx_file_limit,
            "adaptive_content_batch_size": batch_config.content_upsert_batch_size,
        }

        logger.info(
            "Async commit: repo_class=%s, file_batch=%d, tx_file_limit=%d",
            batch_config.repo_class,
            batch_size,
            batch_config.tx_file_limit,
        )

        if snapshot.file_data:
            while snapshot.file_data:
                batch = snapshot.file_data[:batch_size]
                del snapshot.file_data[:batch_size]

                _t0 = time.perf_counter()
                if use_process_pool:
                    # Dispatch to child process via commit_batch_in_process
                    commit_result = await loop.run_in_executor(
                        process_executor,
                        functools.partial(
                            commit_batch_in_process,
                            **connection_params,
                            file_data_list=batch,
                            repo_path=str(repo_path),
                            **commit_kwargs,
                        ),
                    )
                else:
                    # Backward compat: ThreadPoolExecutor
                    commit_result = await loop.run_in_executor(
                        executor,
                        functools.partial(
                            builder.commit_file_batch_to_graph,
                            batch,
                            repo_path,
                            **commit_kwargs,
                        ),
                    )
                _accumulate_timing(
                    timing, commit_result, batch, time.perf_counter() - _t0
                )
                committed_paths, failed_paths = _normalize_result(commit_result, batch)
                committed_files += len(committed_paths)
                if callable(progress_callback) and committed_paths:
                    progress_callback(
                        processed_files=min(committed_files, total_files),
                        total_files=total_files,
                        current_file=committed_paths[-1],
                        committed=True,
                    )
                if failed_paths:
                    raise RuntimeError(
                        f"Failed to persist {len(failed_paths)} files for "
                        f"repository {repo_path}: {', '.join(failed_paths)}"
                    )
            return timing

        if not callable(iter_snapshot_file_data_batches_fn):
            raise FileNotFoundError(
                f"Missing file data batches for repository {repo_path.resolve()}"
            )

        for batch in iter_snapshot_file_data_batches_fn(repo_path, batch_size):
            if not batch:
                continue
            _t0 = time.perf_counter()
            if use_process_pool:
                # Dispatch to child process via commit_batch_in_process
                commit_result = await loop.run_in_executor(
                    process_executor,
                    functools.partial(
                        commit_batch_in_process,
                        **connection_params,
                        file_data_list=batch,
                        repo_path=str(repo_path),
                        **commit_kwargs,
                    ),
                )
            else:
                # Backward compat: ThreadPoolExecutor
                commit_result = await loop.run_in_executor(
                    executor,
                    functools.partial(
                        builder.commit_file_batch_to_graph,
                        batch,
                        repo_path,
                        **commit_kwargs,
                    ),
                )
            _accumulate_timing(timing, commit_result, batch, time.perf_counter() - _t0)
            committed_paths, failed_paths = _normalize_result(commit_result, batch)
            committed_files += len(committed_paths)
            if callable(progress_callback) and committed_paths:
                progress_callback(
                    processed_files=min(committed_files, total_files),
                    total_files=total_files,
                    current_file=committed_paths[-1],
                    committed=True,
                )
            if failed_paths:
                raise RuntimeError(
                    f"Failed to persist {len(failed_paths)} files for "
                    f"repository {repo_path}: {', '.join(failed_paths)}"
                )
        return timing

    finally:
        # Only shutdown if we created a ThreadPoolExecutor
        # ProcessPoolExecutor is managed by the pipeline
        if executor is not None:
            executor.shutdown(wait=False)


__all__ = [
    "commit_repository_snapshot_async",
    "_ASYNC_COMMIT_ENABLED",
]
