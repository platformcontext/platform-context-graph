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
from .commit import commit_file_batch_to_graph
from .entities import build_entity_merge_statement
from .files import add_file_to_graph, write_one_file_graph
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
from .inheritance import (
    create_all_inheritance_links,
    create_csharp_inheritance_and_interfaces,
    create_inheritance_links,
)
from .call_batches import (
    contextual_call_batch_queries,
    contextual_repo_scoped_batch_query,
    file_level_call_batch_queries,
    file_level_repo_scoped_batch_query,
)
from .call_otel import emit_call_resolution_otel_metrics
from .call_prefilter import (
    build_known_callable_names,
    build_known_callable_names_by_family,
    compatible_languages,
    max_calls_for_repo_class,
)
from .calls import (
    create_all_function_calls,
    create_function_calls,
    name_from_symbol,
    safe_run_create,
)
from .types import BatchCommitResult

__all__ = (
    "_bounded_positive_int_config",
    "_merge_directory_chain",
    "_relative_path_with_fallback",
    "_run_managed_write",
    "_run_write_query",
    "add_file_to_graph",
    "BatchCommitResult",
    "build_entity_merge_statement",
    "begin_transaction",
    "collect_file_write_data",
    "collect_directory_chain_rows",
    "compatible_languages",
    "commit_file_batch_to_graph",
    "contextual_call_batch_queries",
    "contextual_repo_scoped_batch_query",
    "content_dual_write",
    "content_dual_write_batch",
    "create_all_function_calls",
    "delete_file_from_graph",
    "delete_repository_from_graph",
    "empty_accumulator",
    "emit_call_resolution_otel_metrics",
    "file_level_call_batch_queries",
    "file_level_repo_scoped_batch_query",
    "flush_directory_chain_rows",
    "flush_write_batches",
    "build_known_callable_names",
    "build_known_callable_names_by_family",
    "has_pending_rows",
    "log_prepared_entity_batches",
    "max_calls_for_repo_class",
    "merge_directory_chain",
    "merge_batches",
    "name_from_symbol",
    "add_repository_to_graph",
    "commit_batch_in_process",
    "pending_row_count",
    "run_entity_unwind",
    "read_repository_metadata",
    "should_flush_batches",
    "summarize_entity_source_files",
    "get_commit_worker_connection_params",
    "accumulate_entity_totals",
    "create_all_inheritance_links",
    "create_csharp_inheritance_and_interfaces",
    "create_function_calls",
    "create_inheritance_links",
    "safe_run_create",
    "update_file_in_graph",
    "validate_cypher_label",
    "validate_cypher_property_keys",
    "write_one_file_graph",
)
