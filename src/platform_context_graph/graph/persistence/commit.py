"""Batch commit helpers for graph persistence."""

from __future__ import annotations

import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from ...cli.config_manager import get_config_value
from ...observability import get_observability
from ...utils.debug_log import emit_log_call
from .batching import (
    empty_accumulator,
    flush_write_batches,
    has_pending_rows,
    log_prepared_entity_batches,
    merge_batches,
    should_flush_batches,
)
from .content_store import content_dual_write_batch
from .files import write_one_file_graph
from .metrics import accumulate_entity_totals
from .repositories import (
    _bounded_positive_int_config,
    flush_directory_chain_rows,
    read_repository_metadata,
)
from .session import begin_transaction
from .types import BatchCommitResult
from .unwind import resolve_max_entity_value_length

BatchFlushFn = Callable[..., dict[str, Any]]
BeginTransactionFn = Callable[[Any], tuple[Any, bool]]
BoundedIntConfigFn = Callable[..., int]
ContentDualWriteBatchFn = Callable[..., None]
EmptyAccumulatorFn = Callable[[], dict[str, Any]]
FlushDirectoryRowsFn = Callable[[Any, list[dict[str, str]], list[dict[str, str]]], None]
LogPreparedBatchesFn = Callable[..., None]
MergeBatchesFn = Callable[[dict[str, Any], dict[str, Any]], None]
ReadRepositoryMetadataFn = Callable[[Any, Path], dict[str, Any]]
ResolveMaxEntityValueLengthFn = Callable[[Any], int]
ShouldFlushBatchesFn = Callable[..., bool]
WriteOneFileGraphFn = Callable[..., tuple[str, dict[str, Any]]]

_GIL_YIELD_ENABLED: bool = (
    os.environ.get(
        "PCG_COMMIT_GIL_YIELD_ENABLED",
        "true",
    ).lower()
    != "false"
)


def commit_file_batch_to_graph(
    builder: Any,
    file_data_list: list[dict[str, Any]],
    repo_path: Path,
    *,
    progress_callback: Any | None = None,
    debug_log_fn: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
    adaptive_flush_threshold: int | None = None,
    adaptive_entity_batch_size: int | None = None,
    adaptive_tx_file_limit: int | None = None,
    adaptive_content_batch_size: int | None = None,
    bounded_positive_int_config_fn: BoundedIntConfigFn = _bounded_positive_int_config,
    begin_transaction_fn: BeginTransactionFn = begin_transaction,
    content_dual_write_batch_fn: ContentDualWriteBatchFn = content_dual_write_batch,
    empty_accumulator_fn: EmptyAccumulatorFn = empty_accumulator,
    flush_directory_chain_rows_fn: FlushDirectoryRowsFn = flush_directory_chain_rows,
    flush_write_batches_fn: BatchFlushFn = flush_write_batches,
    has_pending_rows_fn: Callable[[dict[str, Any]], bool] = has_pending_rows,
    log_prepared_entity_batches_fn: LogPreparedBatchesFn = log_prepared_entity_batches,
    merge_batches_fn: MergeBatchesFn = merge_batches,
    read_repository_metadata_fn: ReadRepositoryMetadataFn = read_repository_metadata,
    resolve_max_entity_value_length_fn: ResolveMaxEntityValueLengthFn = (
        resolve_max_entity_value_length
    ),
    should_flush_batches_fn: ShouldFlushBatchesFn = should_flush_batches,
    write_one_file_graph_fn: WriteOneFileGraphFn = write_one_file_graph,
) -> BatchCommitResult:
    """Persist parsed files using bounded graph write transactions."""

    if not file_data_list:
        return BatchCommitResult()
    repo_path_obj = repo_path.resolve()
    repo_path_str = str(repo_path_obj)

    emit_log_call(
        debug_log_fn,
        f"commit_file_batch_to_graph: {len(file_data_list)} files for {repo_path_str}",
        event_name="graph.batch.commit.started",
        extra_keys={
            "repo_path": repo_path_str,
            "file_count": len(file_data_list),
        },
    )
    max_entity_value_length = resolve_max_entity_value_length_fn(
        get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH")
    )
    if adaptive_tx_file_limit is not None:
        tx_file_limit = min(adaptive_tx_file_limit, max(1, len(file_data_list)))
    else:
        tx_file_limit = bounded_positive_int_config_fn(
            "PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE",
            5,
            maximum=max(1, len(file_data_list)),
        )

    with builder.driver.session() as session:
        repository = read_repository_metadata_fn(session, repo_path_obj)
        total_files = len(file_data_list)
        committed_files = 0
        committed_file_paths: list[str] = []
        repo_entity_totals: dict[str, int] = {}
        content_write_total, graph_write_total = 0.0, 0.0
        for start in range(0, total_files, tx_file_limit):
            tx_chunk = file_data_list[start : start + tx_file_limit]
            content_t0 = time.perf_counter()
            content_dual_write_batch_fn(
                tx_chunk,
                repository,
                warning_logger_fn,
                content_batch_size=adaptive_content_batch_size,
            )
            content_write_total += time.perf_counter() - content_t0
            graph_t0 = time.perf_counter()
            tx, is_explicit = begin_transaction_fn(session)
            chunk_file_paths: list[str] = []
            try:
                with get_observability().start_span(
                    "pcg.graph.commit_chunk",
                    attributes={
                        "pcg.graph.repo_path": repo_path_str,
                        "pcg.graph.chunk_file_count": len(tx_chunk),
                    },
                ):
                    accumulator = empty_accumulator_fn()
                    chunk_dir_rows: list[dict[str, str]] = []
                    chunk_containment_rows: list[dict[str, str]] = []

                    for chunk_index, file_data in enumerate(tx_chunk, start=1):
                        file_path_str, file_batches = write_one_file_graph_fn(
                            tx,
                            file_data,
                            max_entity_value_length=max_entity_value_length,
                            repo_path_obj=repo_path_obj,
                            warning_logger_fn=warning_logger_fn,
                            dir_rows_accumulator=chunk_dir_rows,
                            containment_rows_accumulator=chunk_containment_rows,
                        )
                        chunk_file_paths.append(file_path_str)
                        merge_batches_fn(accumulator, file_batches)
                        if callable(progress_callback):
                            progress_callback(
                                processed_files=committed_files + chunk_index,
                                total_files=total_files,
                                current_file=file_path_str,
                                committed=False,
                            )
                        if should_flush_batches_fn(
                            accumulator,
                            flush_threshold=adaptive_flush_threshold,
                        ):
                            log_prepared_entity_batches_fn(
                                accumulator,
                                repo_path_str=repo_path_str,
                                info_logger_fn=info_logger_fn,
                                debug_logger_fn=debug_log_fn,
                            )
                            flush_metrics = flush_write_batches_fn(
                                tx,
                                accumulator,
                                info_logger_fn=info_logger_fn,
                                debug_logger_fn=debug_log_fn,
                                entity_batch_size=adaptive_entity_batch_size,
                            )
                            accumulate_entity_totals(repo_entity_totals, flush_metrics)
                            accumulator = empty_accumulator_fn()

                    flush_directory_chain_rows_fn(
                        tx,
                        chunk_dir_rows,
                        chunk_containment_rows,
                    )

                    if has_pending_rows_fn(accumulator):
                        log_prepared_entity_batches_fn(
                            accumulator,
                            repo_path_str=repo_path_str,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                        )
                        flush_metrics = flush_write_batches_fn(
                            tx,
                            accumulator,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                            entity_batch_size=adaptive_entity_batch_size,
                        )
                        accumulate_entity_totals(repo_entity_totals, flush_metrics)
                    if is_explicit:
                        tx.commit()
                        if _GIL_YIELD_ENABLED:
                            time.sleep(0)
                    graph_write_total += time.perf_counter() - graph_t0
            except Exception as exc:
                if is_explicit:
                    tx.rollback()
                emit_log_call(
                    warning_logger_fn,
                    (
                        f"Graph batch chunk failed for {repo_path_str}; "
                        "retrying files individually"
                    ),
                    event_name="graph.batch.commit.chunk_retry",
                    extra_keys={
                        "repo_path": repo_path_str,
                        "chunk_file_count": len(tx_chunk),
                    },
                    exc_info=exc,
                )
                failed_file_paths: list[str] = []
                for file_data in tx_chunk:
                    retry_t0 = time.perf_counter()
                    tx, is_explicit = begin_transaction_fn(session)
                    try:
                        file_path_str, file_batches = write_one_file_graph_fn(
                            tx,
                            file_data,
                            max_entity_value_length=max_entity_value_length,
                            repo_path_obj=repo_path_obj,
                            warning_logger_fn=warning_logger_fn,
                        )
                        log_prepared_entity_batches_fn(
                            file_batches,
                            repo_path_str=repo_path_str,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                        )
                        flush_metrics = flush_write_batches_fn(
                            tx,
                            file_batches,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                            entity_batch_size=adaptive_entity_batch_size,
                        )
                        accumulate_entity_totals(repo_entity_totals, flush_metrics)
                        if is_explicit:
                            tx.commit()
                            if _GIL_YIELD_ENABLED:
                                time.sleep(0)
                        graph_write_total += time.perf_counter() - retry_t0
                        committed_files += 1
                        committed_file_paths.append(file_path_str)
                    except Exception as file_exc:
                        if is_explicit:
                            tx.rollback()
                        failed_path = str(Path(file_data["path"]).resolve())
                        failed_file_paths.append(failed_path)
                        emit_log_call(
                            warning_logger_fn,
                            f"Graph file write failed during fallback for {failed_path}",
                            event_name="graph.batch.commit.file_failed",
                            extra_keys={
                                "repo_path": repo_path_str,
                                "file_path": failed_path,
                            },
                            exc_info=file_exc,
                        )
                if failed_file_paths:
                    return BatchCommitResult(
                        committed_file_paths=tuple(committed_file_paths),
                        failed_file_paths=tuple(failed_file_paths),
                    )
                if callable(progress_callback) and tx_chunk:
                    progress_callback(
                        processed_files=committed_files,
                        total_files=total_files,
                        current_file=committed_file_paths[-1],
                        committed=True,
                    )
                continue

            committed_files += len(tx_chunk)
            committed_file_paths.extend(chunk_file_paths)
            if callable(progress_callback) and tx_chunk:
                progress_callback(
                    processed_files=committed_files,
                    total_files=total_files,
                    current_file=str(Path(tx_chunk[-1]["path"]).resolve()),
                    committed=True,
                )
        if repo_entity_totals and callable(info_logger_fn):
            entity_summary = ", ".join(
                f"{label}={count}"
                for label, count in sorted(repo_entity_totals.items())
                if count > 0
            )
            emit_log_call(
                info_logger_fn,
                f"Committed graph entities for {repo_path_str}: {entity_summary}",
                event_name="graph.batch.commit.entity_summary",
                extra_keys={
                    "repo_path": repo_path_str,
                    "file_count": len(file_data_list),
                    "entity_totals": repo_entity_totals,
                },
            )
        return replace(
            BatchCommitResult(committed_file_paths=tuple(committed_file_paths)),
            content_write_duration_seconds=content_write_total,
            graph_write_duration_seconds=graph_write_total,
            entity_totals=repo_entity_totals,
        )


__all__ = ["commit_file_batch_to_graph"]
