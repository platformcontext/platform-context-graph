"""Graph persistence helpers exposed from the canonical graph package."""

from .mutations import (
    delete_file_from_graph,
    delete_repository_from_graph,
    update_file_in_graph,
)
from .directories import (
    collect_directory_chain_rows,
    flush_directory_chain_rows,
    merge_directory_chain,
)
from .content_store import content_dual_write, content_dual_write_batch
from .entities import build_entity_merge_statement
from .metrics import accumulate_entity_totals
from .repositories import (
    _bounded_positive_int_config,
    _merge_directory_chain,
    _relative_path_with_fallback,
    _run_managed_write,
    _run_write_query,
    add_repository_to_graph,
    read_repository_metadata,
)
from .session import begin_transaction
from .worker import (
    commit_batch_in_process,
    get_commit_worker_connection_params,
)
from .unwind import (
    run_entity_unwind,
    validate_cypher_label,
    validate_cypher_property_keys,
)
from .batching import (
    collect_file_write_data,
    empty_accumulator,
    flush_write_batches,
    has_pending_rows,
    log_prepared_entity_batches,
    merge_batches,
    pending_row_count,
    should_flush_batches,
    summarize_entity_source_files,
)
from .types import BatchCommitResult

__all__ = (
    "_bounded_positive_int_config",
    "_merge_directory_chain",
    "_relative_path_with_fallback",
    "_run_managed_write",
    "_run_write_query",
    "BatchCommitResult",
    "build_entity_merge_statement",
    "begin_transaction",
    "collect_file_write_data",
    "collect_directory_chain_rows",
    "content_dual_write",
    "content_dual_write_batch",
    "delete_file_from_graph",
    "delete_repository_from_graph",
    "empty_accumulator",
    "flush_directory_chain_rows",
    "flush_write_batches",
    "has_pending_rows",
    "log_prepared_entity_batches",
    "merge_directory_chain",
    "merge_batches",
    "add_repository_to_graph",
    "commit_batch_in_process",
    "pending_row_count",
    "run_entity_unwind",
    "read_repository_metadata",
    "should_flush_batches",
    "summarize_entity_source_files",
    "get_commit_worker_connection_params",
    "accumulate_entity_totals",
    "update_file_in_graph",
    "validate_cypher_label",
    "validate_cypher_property_keys",
)
