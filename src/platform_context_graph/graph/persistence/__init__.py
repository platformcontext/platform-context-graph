"""Lazy exports for canonical graph persistence helpers."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "_bounded_positive_int_config": (".repositories", "_bounded_positive_int_config"),
    "_merge_directory_chain": (".repositories", "_merge_directory_chain"),
    "_relative_path_with_fallback": (
        ".repositories",
        "_relative_path_with_fallback",
    ),
    "_run_managed_write": (".repositories", "_run_managed_write"),
    "_run_write_query": (".repositories", "_run_write_query"),
    "add_file_to_graph": (".files", "add_file_to_graph"),
    "add_repository_to_graph": (".repositories", "add_repository_to_graph"),
    "BatchCommitResult": (".types", "BatchCommitResult"),
    "begin_transaction": (".session", "begin_transaction"),
    "build_entity_merge_statement": (".entities", "build_entity_merge_statement"),
    "build_known_callable_names": (
        ".call_prefilter",
        "build_known_callable_names",
    ),
    "build_known_callable_names_by_family": (
        ".call_prefilter",
        "build_known_callable_names_by_family",
    ),
    "collect_directory_chain_rows": (
        ".directories",
        "collect_directory_chain_rows",
    ),
    "collect_file_write_data": (".batching", "collect_file_write_data"),
    "commit_batch_in_process": (".worker", "commit_batch_in_process"),
    "commit_file_batch_to_graph": (".commit", "commit_file_batch_to_graph"),
    "compatible_languages": (".call_prefilter", "compatible_languages"),
    "contextual_call_batch_queries": (
        ".call_batches",
        "contextual_call_batch_queries",
    ),
    "contextual_repo_scoped_batch_query": (
        ".call_batches",
        "contextual_repo_scoped_batch_query",
    ),
    "content_dual_write": (".content_store", "content_dual_write"),
    "content_dual_write_batch": (".content_store", "content_dual_write_batch"),
    "create_all_function_calls": (".calls", "create_all_function_calls"),
    "create_all_inheritance_links": (
        ".inheritance",
        "create_all_inheritance_links",
    ),
    "create_csharp_inheritance_and_interfaces": (
        ".inheritance",
        "create_csharp_inheritance_and_interfaces",
    ),
    "create_function_calls": (".calls", "create_function_calls"),
    "create_inheritance_links": (".inheritance", "create_inheritance_links"),
    "delete_file_from_graph": (".mutations", "delete_file_from_graph"),
    "delete_repository_from_graph": (".mutations", "delete_repository_from_graph"),
    "reset_repository_subtree_in_graph": (
        ".mutations",
        "reset_repository_subtree_in_graph",
    ),
    "empty_accumulator": (".batching", "empty_accumulator"),
    "emit_call_resolution_otel_metrics": (
        ".call_otel",
        "emit_call_resolution_otel_metrics",
    ),
    "file_level_call_batch_queries": (
        ".call_batches",
        "file_level_call_batch_queries",
    ),
    "file_level_repo_scoped_batch_query": (
        ".call_batches",
        "file_level_repo_scoped_batch_query",
    ),
    "flush_directory_chain_rows": (".directories", "flush_directory_chain_rows"),
    "flush_write_batches": (".batching", "flush_write_batches"),
    "get_commit_worker_connection_params": (
        ".worker",
        "get_commit_worker_connection_params",
    ),
    "has_pending_rows": (".batching", "has_pending_rows"),
    "log_prepared_entity_batches": (".batching", "log_prepared_entity_batches"),
    "max_calls_for_repo_class": (".call_prefilter", "max_calls_for_repo_class"),
    "merge_batches": (".batching", "merge_batches"),
    "merge_directory_chain": (".directories", "merge_directory_chain"),
    "name_from_symbol": (".calls", "name_from_symbol"),
    "pending_row_count": (".batching", "pending_row_count"),
    "read_repository_metadata": (".repositories", "read_repository_metadata"),
    "run_entity_unwind": (".unwind", "run_entity_unwind"),
    "safe_run_create": (".calls", "safe_run_create"),
    "should_flush_batches": (".batching", "should_flush_batches"),
    "summarize_entity_source_files": (".batching", "summarize_entity_source_files"),
    "update_file_in_graph": (".mutations", "update_file_in_graph"),
    "validate_cypher_label": (".unwind", "validate_cypher_label"),
    "validate_cypher_property_keys": (
        ".unwind",
        "validate_cypher_property_keys",
    ),
    "write_one_file_graph": (".files", "write_one_file_graph"),
}

__all__ = tuple(_EXPORTS)


def __getattr__(name: str) -> object:
    """Resolve graph-persistence exports lazily by attribute name."""

    module_path, attribute_name = _EXPORTS[name]
    module = import_module(module_path, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return the available lazy export names for introspection."""

    return sorted(list(globals().keys()) + list(__all__))
