"""Persistence helpers for repository and file graph updates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..content.ingest import prepare_content_entries
from ..content.state import get_postgres_content_provider
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
from ..graph.persistence.commit import (
    commit_file_batch_to_graph as _canonical_commit_file_batch_to_graph,
)
from ..graph.persistence.files import (
    add_file_to_graph as _canonical_add_file_to_graph,
    write_one_file_graph as _canonical_write_one_file_graph,
)
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
    """Compatibility wrapper for the canonical batch commit helper."""

    return _canonical_commit_file_batch_to_graph(
        builder,
        file_data_list,
        repo_path,
        progress_callback=progress_callback,
        debug_log_fn=debug_log_fn,
        info_logger_fn=info_logger_fn,
        warning_logger_fn=warning_logger_fn,
        adaptive_flush_threshold=adaptive_flush_threshold,
        adaptive_entity_batch_size=adaptive_entity_batch_size,
        adaptive_tx_file_limit=adaptive_tx_file_limit,
        adaptive_content_batch_size=adaptive_content_batch_size,
        bounded_positive_int_config_fn=_bounded_positive_int_config,
        begin_transaction_fn=_begin_transaction,
        content_dual_write_batch_fn=_content_dual_write_batch,
        empty_accumulator_fn=empty_accumulator,
        flush_directory_chain_rows_fn=flush_directory_chain_rows,
        flush_write_batches_fn=flush_write_batches,
        has_pending_rows_fn=has_pending_rows,
        log_prepared_entity_batches_fn=log_prepared_entity_batches,
        merge_batches_fn=merge_batches,
        read_repository_metadata_fn=read_repository_metadata,
        resolve_max_entity_value_length_fn=resolve_max_entity_value_length,
        should_flush_batches_fn=should_flush_batches,
        write_one_file_graph_fn=_write_one_file_graph,
    )


__all__ = [
    "BatchCommitResult",
    "add_file_to_graph",
    "add_repository_to_graph",
    "commit_file_batch_to_graph",
]
