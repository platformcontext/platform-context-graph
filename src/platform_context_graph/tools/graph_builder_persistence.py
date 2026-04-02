"""Persistence helpers for repository and file graph updates."""

from __future__ import annotations

import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

_GIL_YIELD_ENABLED: bool = os.environ.get("PCG_COMMIT_GIL_YIELD_ENABLED", "true").lower() != "false"

from ..cli.config_manager import get_config_value
from ..content.ingest import prepare_content_entries
from ..content.state import get_postgres_content_provider
from ..observability import get_observability
from ..utils.debug_log import emit_log_call
from ..graph.persistence.batching import (
    collect_file_write_data,
    empty_accumulator,
    flush_write_batches,
    has_pending_rows,
    log_prepared_entity_batches,
    merge_batches,
    should_flush_batches,
)
from ..graph.persistence.content_store import (
    content_dual_write as _canonical_content_dual_write,
    content_dual_write_batch as _canonical_content_dual_write_batch,
)
from ..graph.persistence.files import (
    add_file_to_graph as _canonical_add_file_to_graph,
    write_one_file_graph as _canonical_write_one_file_graph,
)
from ..graph.persistence.metrics import accumulate_entity_totals
from ..graph.persistence.types import BatchCommitResult
from ..graph.persistence.repositories import (
    _bounded_positive_int_config,
    _merge_directory_chain,
    _relative_path_with_fallback,
    _run_managed_write,
    _run_write_query,
    add_repository_to_graph,
    collect_directory_chain_rows,
    flush_directory_chain_rows,
    read_repository_metadata,
)
from ..graph.persistence.session import begin_transaction as _begin_transaction
from ..graph.persistence.unwind import resolve_max_entity_value_length


def _content_dual_write(
    file_data: dict[str, Any],
    file_name: str,
    repository: dict[str, Any],
    warning_logger_fn: Any,
) -> None:
    """Compatibility wrapper for the canonical content dual-write helper."""

    _canonical_content_dual_write(
        file_data,
        file_name,
        repository,
        warning_logger_fn,
        get_content_provider=get_postgres_content_provider,
        prepare_entries=prepare_content_entries,
    )

def _content_dual_write_batch(
    file_data_list: list[dict[str, Any]],
    repository: dict[str, Any],
    warning_logger_fn: Any,
    *,
    content_batch_size: int | None = None,
) -> None:
    """Compatibility wrapper for batched content-store dual-writes."""

    _canonical_content_dual_write_batch(
        file_data_list,
        repository,
        warning_logger_fn,
        content_batch_size=content_batch_size,
        get_content_provider=get_postgres_content_provider,
        prepare_entries=prepare_content_entries,
    )

def add_file_to_graph(
    builder: Any,
    file_data: dict[str, Any],
    repo_name: str,
    imports_map: dict[str, Any],
    *,
    debug_log_fn: Any,
    info_logger_fn: Any,
    warning_logger_fn: Any,
) -> None:
    """Compatibility wrapper for the canonical file-persistence helper."""

    _canonical_add_file_to_graph(
        builder,
        file_data,
        repo_name,
        imports_map,
        debug_log_fn=debug_log_fn,
        info_logger_fn=info_logger_fn,
        warning_logger_fn=warning_logger_fn,
        content_dual_write_fn=_content_dual_write,
        begin_transaction_fn=_begin_transaction,
    )


def _write_one_file_graph(
    tx: Any,
    file_data: dict[str, Any],
    *,
    repo_path_obj: Path,
    max_entity_value_length: int,
    warning_logger_fn: Any,
    dir_rows_accumulator: list[dict[str, str]] | None = None,
    containment_rows_accumulator: list[dict[str, str]] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Compatibility wrapper for the canonical per-file graph writer."""

    return _canonical_write_one_file_graph(
        tx,
        file_data,
        repo_path_obj=repo_path_obj,
        max_entity_value_length=max_entity_value_length,
        warning_logger_fn=warning_logger_fn,
        collect_file_write_data_fn=collect_file_write_data,
        dir_rows_accumulator=dir_rows_accumulator,
        containment_rows_accumulator=containment_rows_accumulator,
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
) -> BatchCommitResult:
    """Persist parsed files using bounded Neo4j write transactions."""
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
    max_entity_value_length = resolve_max_entity_value_length(
        get_config_value("PCG_MAX_ENTITY_VALUE_LENGTH")
    )
    if adaptive_tx_file_limit is not None:
        tx_file_limit = min(adaptive_tx_file_limit, max(1, len(file_data_list)))
    else:
        tx_file_limit = _bounded_positive_int_config(
            "PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE",
            5,
            maximum=max(1, len(file_data_list)),
        )

    with builder.driver.session() as session:
        repository = read_repository_metadata(session, repo_path_obj)
        total_files = len(file_data_list)
        committed_files = 0
        committed_file_paths: list[str] = []
        repo_entity_totals: dict[str, int] = {}
        content_write_total, graph_write_total = 0.0, 0.0
        for start in range(0, total_files, tx_file_limit):
            tx_chunk = file_data_list[start : start + tx_file_limit]
            _t0 = time.perf_counter()
            _content_dual_write_batch(
                tx_chunk,
                repository,
                warning_logger_fn,
                content_batch_size=adaptive_content_batch_size,
            )
            content_write_total += time.perf_counter() - _t0
            _t0, tx, is_explicit = time.perf_counter(), *_begin_transaction(session)
            chunk_file_paths: list[str] = []
            try:
                with get_observability().start_span(
                    "pcg.graph.commit_chunk",
                    attributes={
                        "pcg.graph.repo_path": repo_path_str,
                        "pcg.graph.chunk_file_count": len(tx_chunk),
                    },
                ):
                    accumulator = empty_accumulator()
                    chunk_dir_rows: list[dict[str, str]] = []
                    chunk_containment_rows: list[dict[str, str]] = []

                    for chunk_index, file_data in enumerate(tx_chunk, start=1):
                        file_path_str, file_batches = _write_one_file_graph(
                            tx,
                            file_data,
                            max_entity_value_length=max_entity_value_length,
                            repo_path_obj=repo_path_obj,
                            warning_logger_fn=warning_logger_fn,
                            dir_rows_accumulator=chunk_dir_rows,
                            containment_rows_accumulator=chunk_containment_rows,
                        )
                        chunk_file_paths.append(file_path_str)
                        merge_batches(accumulator, file_batches)
                        if callable(progress_callback):
                            progress_callback(
                                processed_files=committed_files + chunk_index,
                                total_files=total_files,
                                current_file=file_path_str,
                                committed=False,
                            )
                        if should_flush_batches(
                            accumulator, flush_threshold=adaptive_flush_threshold
                        ):
                            log_prepared_entity_batches(
                                accumulator,
                                repo_path_str=repo_path_str,
                                info_logger_fn=info_logger_fn,
                                debug_logger_fn=debug_log_fn,
                            )
                            flush_metrics = flush_write_batches(
                                tx,
                                accumulator,
                                info_logger_fn=info_logger_fn,
                                debug_logger_fn=debug_log_fn,
                                entity_batch_size=adaptive_entity_batch_size,
                            )
                            accumulate_entity_totals(repo_entity_totals, flush_metrics)
                            accumulator = empty_accumulator()

                    flush_directory_chain_rows(
                        tx, chunk_dir_rows, chunk_containment_rows
                    )

                    if has_pending_rows(accumulator):
                        log_prepared_entity_batches(
                            accumulator,
                            repo_path_str=repo_path_str,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                        )
                        flush_metrics = flush_write_batches(
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
                    graph_write_total += time.perf_counter() - _t0
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
                    _retry_t0 = time.perf_counter()
                    tx, is_explicit = _begin_transaction(session)
                    try:
                        file_path_str, file_batches = _write_one_file_graph(
                            tx,
                            file_data,
                            max_entity_value_length=max_entity_value_length,
                            repo_path_obj=repo_path_obj,
                            warning_logger_fn=warning_logger_fn,
                        )
                        log_prepared_entity_batches(
                            file_batches,
                            repo_path_str=repo_path_str,
                            info_logger_fn=info_logger_fn,
                            debug_logger_fn=debug_log_fn,
                        )
                        flush_metrics = flush_write_batches(
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
                        graph_write_total += time.perf_counter() - _retry_t0
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

__all__ = ["BatchCommitResult", "add_file_to_graph", "add_repository_to_graph",
           "commit_file_batch_to_graph"]
