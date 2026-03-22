"""Aggregate MCP tool definitions exposed by the server import surface."""

from .tools.codebase import CODEBASE_TOOLS
from .tools.content import CONTENT_TOOLS
from .tools.context import CONTEXT_TOOLS
from .tools.ecosystem import ECOSYSTEM_TOOLS
from .tools.runtime import RUNTIME_TOOLS

TOOLS = {
    **CODEBASE_TOOLS,
    **CONTENT_TOOLS,
    **ECOSYSTEM_TOOLS,
    **CONTEXT_TOOLS,
    **RUNTIME_TOOLS,
}

_READ_ONLY_TOOL_NAMES = {
    "find_dead_code",
    "find_code",
    "analyze_code_relationships",
    "execute_cypher_query",
    "calculate_cyclomatic_complexity",
    "find_most_complex_functions",
    "list_indexed_repositories",
    "visualize_graph_query",
    "search_registry_bundles",
    "get_repository_stats",
    "get_ecosystem_overview",
    "trace_deployment_chain",
    "find_blast_radius",
    "find_infra_resources",
    "analyze_infra_relationships",
    "get_repo_summary",
    "get_repo_context",
    "resolve_entity",
    "get_entity_context",
    "get_workload_context",
    "get_service_context",
    "trace_resource_to_code",
    "explain_dependency_path",
    "find_change_surface",
    "compare_environments",
    "get_file_content",
    "get_file_lines",
    "get_entity_content",
    "search_file_content",
    "search_entity_content",
    "list_ingesters",
    "get_ingester_status",
}


def tools_for_runtime_role(role: str) -> dict[str, dict]:
    """Return the public MCP tool set for one runtime role."""

    if role == "api":
        return {name: TOOLS[name] for name in _READ_ONLY_TOOL_NAMES}
    return dict(TOOLS)


__all__ = ["TOOLS", "tools_for_runtime_role"]
