"""Tool dispatch helpers for the MCP server."""

from __future__ import annotations

from typing import Any, Awaitable, Callable

SyncToolHandler = Callable[..., dict[str, Any]]
AsyncToolHandler = Callable[..., Awaitable[dict[str, Any]]]


def build_sync_tool_map(server: Any) -> dict[str, SyncToolHandler]:
    """Build the synchronous MCP tool dispatch table.

    Args:
        server: The configured MCP server instance.

    Returns:
        A mapping from public MCP tool names to bound server handlers.
    """
    return {
        "add_package_to_graph": server.add_package_to_graph_tool,
        "find_dead_code": server.find_dead_code_tool,
        "find_code": server.find_code_tool,
        "analyze_code_relationships": server.analyze_code_relationships_tool,
        "watch_directory": server.watch_directory_tool,
        "execute_cypher_query": server.execute_cypher_query_tool,
        "add_code_to_graph": server.add_code_to_graph_tool,
        "check_job_status": server.check_job_status_tool,
        "list_jobs": server.list_jobs_tool,
        "calculate_cyclomatic_complexity": server.calculate_cyclomatic_complexity_tool,
        "find_most_complex_functions": server.find_most_complex_functions_tool,
        "list_indexed_repositories": server.list_indexed_repositories_tool,
        "delete_repository": server.delete_repository_tool,
        "visualize_graph_query": server.visualize_graph_query_tool,
        "list_watched_paths": server.list_watched_paths_tool,
        "unwatch_directory": server.unwatch_directory_tool,
        "load_bundle": server.load_bundle_tool,
        "search_registry_bundles": server.search_registry_bundles_tool,
        "get_repository_stats": server.get_repository_stats_tool,
        "ecosystem_status": server.ecosystem_status_tool,
        "get_ecosystem_overview": server.get_ecosystem_overview_tool,
        "trace_deployment_chain": server.trace_deployment_chain_tool,
        "find_blast_radius": server.find_blast_radius_tool,
        "find_infra_resources": server.find_infra_resources_tool,
        "analyze_infra_relationships": server.analyze_infra_relationships_tool,
        "get_repo_summary": server.get_repo_summary_tool,
        "get_repo_context": server.get_repo_context_tool,
        "resolve_entity": server.resolve_entity_tool,
        "get_entity_context": server.get_entity_context_tool,
        "get_workload_context": server.get_workload_context_tool,
        "get_service_context": server.get_service_context_tool,
        "trace_resource_to_code": server.trace_resource_to_code_tool,
        "explain_dependency_path": server.explain_dependency_path_tool,
        "find_change_surface": server.find_change_surface_tool,
        "compare_environments": server.compare_environments_tool,
        "get_file_content": server.get_file_content_tool,
        "get_file_lines": server.get_file_lines_tool,
        "get_entity_content": server.get_entity_content_tool,
        "search_file_content": server.search_file_content_tool,
        "search_entity_content": server.search_entity_content_tool,
        "link_ecosystem": server.link_ecosystem_tool,
        "list_ingesters": server.list_ingesters_tool,
        "get_ingester_status": server.get_ingester_status_tool,
    }


def build_async_tool_map(server: Any) -> dict[str, AsyncToolHandler]:
    """Build the asynchronous MCP tool dispatch table.

    Args:
        server: The configured MCP server instance.

    Returns:
        A mapping from public MCP tool names to async server handlers.
    """
    tool_map: dict[str, AsyncToolHandler] = {}
    if hasattr(server, "index_ecosystem_tool"):
        tool_map["index_ecosystem"] = server.index_ecosystem_tool
    return tool_map
