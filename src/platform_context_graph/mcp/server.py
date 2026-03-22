"""Public MCP server entrypoints for PlatformContextGraph."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, cast

from ..core import get_database_manager
from ..core.ecosystem_indexer import EcosystemIndexer
from ..core.jobs import JobManager
from ..core.watcher import CodeWatcher
from ..observability import initialize_observability
from ..query import code as code_queries
from ..query import compare as compare_queries
from ..query import context as context_queries
from ..query import entity_resolution as entity_resolution_queries
from ..query import impact as impact_queries
from ..query import infra as infra_queries
from ..query import repositories as repository_queries
from ..tools.code_finder import CodeFinder
from ..tools.cross_repo_linker import CrossRepoLinker
from ..tools.graph_builder import GraphBuilder
from .content_tools import ContentToolMixin
from .repo_access import ServerRepoAccessMixin
from .tool_dispatch import build_async_tool_map, build_sync_tool_map
from .tool_registry import TOOLS
from .tools.handlers import (
    ecosystem,
    indexing,
    management,
    query,
    watcher,
)
from .transport import ServerTransportMixin

DEFAULT_EDIT_DISTANCE = 2
DEFAULT_FUZZY_SEARCH = False


def _require_str_argument(args: dict[str, Any], key: str) -> str | None:
    """Return a string argument when present and non-empty."""
    value = args.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


class MCPServer(ServerTransportMixin, ServerRepoAccessMixin, ContentToolMixin):
    """Coordinate MCP tool execution, watchers, and transport-facing state."""

    def __init__(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Initialize the MCP server and its core collaborators.

        Args:
            loop: The event loop to use for thread-sensitive components. When
                omitted, the current running loop is used or a new loop is
                created.

        Raises:
            ValueError: If the database configuration is invalid.
        """
        try:
            self.db_manager: Any = get_database_manager()
            self.db_manager.get_driver()
        except ValueError as exc:
            raise ValueError(f"Database configuration error: {exc}") from exc

        self.job_manager = JobManager()
        if loop is None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        self.loop = loop

        db_manager = cast(Any, self.db_manager)
        self.graph_builder = GraphBuilder(db_manager, self.job_manager, loop)
        self.code_finder = CodeFinder(db_manager)
        self.code_watcher = CodeWatcher(self.graph_builder, self.job_manager)
        self.ecosystem_indexer = EcosystemIndexer(self.graph_builder, self.job_manager)
        self.cross_repo_linker = CrossRepoLinker(db_manager)
        self.observability = initialize_observability(component="mcp")
        self.client_capabilities: dict[str, Any] = {}
        self._client_request_handler: (
            Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None
        ) = None
        self._pending_client_requests: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._next_client_request_id = 1
        self._stdio_write_lock: asyncio.Lock | None = None
        self._init_tools()

    def _init_tools(self) -> None:
        """Load the MCP tool manifest exposed to clients."""
        self.tools = TOOLS

    def get_database_status(self) -> dict[str, bool]:
        """Return the current database connection state."""
        return {"connected": self.db_manager.is_connected()}

    def execute_cypher_query_tool(self, **args: Any) -> dict[str, Any]:
        """Run the raw Cypher query tool."""
        return query.execute_cypher_query(self.db_manager, **args)

    def visualize_graph_query_tool(self, **args: Any) -> dict[str, Any]:
        """Run the graph visualization query tool."""
        return query.visualize_graph_query(self.db_manager, **args)

    def find_dead_code_tool(self, **args: Any) -> dict[str, Any]:
        """Find dead code in the indexed repository graph."""
        try:
            results = code_queries.find_dead_code(
                self.code_finder,
                repo_path=args.get("repo_path"),
                exclude_decorated_with=args.get("exclude_decorated_with", []),
            )
        except Exception as exc:
            return {"error": f"Failed to find dead code: {exc}"}
        return {"success": True, "query_type": "dead_code", "results": results}

    def calculate_cyclomatic_complexity_tool(self, **args: Any) -> dict[str, Any]:
        """Calculate cyclomatic complexity for a specific function."""
        function_name = args.get("function_name")
        path = args.get("path")
        try:
            results = code_queries.get_complexity(
                self.code_finder,
                mode="function",
                function_name=function_name,
                path=path,
                repo_id=args.get("repo_path"),
            )
        except Exception as exc:
            return {"error": f"Failed to calculate cyclomatic complexity: {exc}"}
        response = {
            "success": True,
            "function_name": function_name,
            "results": results,
        }
        if path:
            response["path"] = path
        return response

    def find_most_complex_functions_tool(self, **args: Any) -> dict[str, Any]:
        """List the highest-complexity indexed functions."""
        limit = args.get("limit", 10)
        try:
            results = code_queries.get_complexity(
                self.code_finder,
                mode="top",
                limit=limit,
                repo_id=args.get("repo_path"),
            )
        except Exception as exc:
            return {"error": f"Failed to find most complex functions: {exc}"}
        return {"success": True, "limit": limit, "results": results}

    def analyze_code_relationships_tool(self, **args: Any) -> dict[str, Any]:
        """Analyze relationships for a code symbol or module."""
        query_type = args.get("query_type")
        target = args.get("target")
        if not query_type or not target:
            return {
                "error": "Both 'query_type' and 'target' are required",
                "supported_query_types": [
                    "find_callers",
                    "find_callees",
                    "find_all_callers",
                    "find_all_callees",
                    "find_importers",
                    "who_modifies",
                    "class_hierarchy",
                    "overrides",
                    "dead_code",
                    "call_chain",
                    "module_deps",
                    "variable_scope",
                    "find_complexity",
                    "find_functions_by_argument",
                    "find_functions_by_decorator",
                ],
            }

        try:
            results = code_queries.get_code_relationships(
                self.code_finder,
                query_type=query_type,
                target=target,
                context=args.get("context"),
                repo_id=args.get("repo_path"),
            )
        except Exception as exc:
            return {"error": f"Failed to analyze relationships: {exc}"}
        return {
            "success": True,
            "query_type": query_type,
            "target": target,
            "context": args.get("context"),
            "results": results,
        }

    def find_code_tool(self, **args: Any) -> dict[str, Any]:
        """Search indexed code by exact or fuzzy symbol name."""
        query = _require_str_argument(args, "query")
        if query is None:
            return {"error": "The 'query' argument is required."}
        fuzzy_search = args.get("fuzzy_search", DEFAULT_FUZZY_SEARCH)
        edit_distance = args.get("edit_distance", DEFAULT_EDIT_DISTANCE)
        if fuzzy_search and isinstance(query, str):
            query = query.lower().replace("_", " ").strip()

        try:
            results = code_queries.search_code(
                self.code_finder,
                query=query,
                repo_id=args.get("repo_path"),
                exact=not fuzzy_search,
                limit=15,
                edit_distance=edit_distance if fuzzy_search else None,
            )
        except Exception as exc:
            return {"error": f"Failed to find code: {exc}"}
        return {"success": True, "query": query, "results": results}

    def list_indexed_repositories_tool(self, **args: Any) -> dict[str, Any]:
        """List repositories that are currently indexed."""
        return management.list_indexed_repositories(self.code_finder, **args)

    def delete_repository_tool(self, **args: Any) -> dict[str, Any]:
        """Delete one indexed repository from the graph."""
        return management.delete_repository(self.graph_builder, **args)

    def check_job_status_tool(self, **args: Any) -> dict[str, Any]:
        """Return the status for one background job."""
        return management.check_job_status(self.job_manager, **args)

    def list_jobs_tool(self) -> dict[str, Any]:
        """List background jobs known to the server."""
        return management.list_jobs(self.job_manager)

    def list_watched_paths_tool(self, **args: Any) -> dict[str, Any]:
        """List directories watched for incremental indexing."""
        return watcher.list_watched_paths(self.code_watcher, **args)

    def unwatch_directory_tool(self, **args: Any) -> dict[str, Any]:
        """Stop watching a directory for changes."""
        return watcher.unwatch_directory(self.code_watcher, **args)

    def add_code_to_graph_tool(self, **args: Any) -> dict[str, Any]:
        """Index repository source code into the graph."""
        return indexing.add_code_to_graph(
            self.graph_builder,
            self.job_manager,
            self.loop,
            self.list_indexed_repositories_tool,
            **args,
        )

    def add_package_to_graph_tool(self, **args: Any) -> dict[str, Any]:
        """Index an installed package into the graph."""
        return indexing.add_package_to_graph(
            self.graph_builder,
            self.job_manager,
            self.loop,
            self.list_indexed_repositories_tool,
            **args,
        )

    def watch_directory_tool(self, **args: Any) -> dict[str, Any]:
        """Watch a directory and trigger indexing updates."""
        return watcher.watch_directory(
            self.code_watcher,
            self.list_indexed_repositories_tool,
            self.add_code_to_graph_tool,
            **args,
        )

    def load_bundle_tool(self, **args: Any) -> dict[str, Any]:
        """Load a previously-created bundle into the graph."""
        return management.load_bundle(self.code_finder, **args)

    def search_registry_bundles_tool(self, **args: Any) -> dict[str, Any]:
        """Search the bundle registry."""
        return management.search_registry_bundles(self.code_finder, **args)

    def get_repository_stats_tool(self, **args: Any) -> dict[str, Any]:
        """Return summary statistics for one repository."""
        return repository_queries.get_repository_stats(
            self.code_finder,
            repo_id=args.get("repo_path"),
        )

    async def index_ecosystem_tool(self, **args: Any) -> dict[str, Any]:
        """Index a full ecosystem definition."""
        return await self.ecosystem_indexer.index_ecosystem(**args)

    def ecosystem_status_tool(self) -> dict[str, Any]:
        """Return ecosystem indexing status."""
        return self.ecosystem_indexer.get_status()

    def get_ecosystem_overview_tool(self) -> dict[str, Any]:
        """Return a high-level ecosystem overview."""
        return infra_queries.get_ecosystem_overview(self.db_manager)

    def trace_deployment_chain_tool(self, **args: Any) -> dict[str, Any]:
        """Trace deployment relationships across the indexed ecosystem."""
        service_name = _require_str_argument(args, "service_name")
        if service_name is None:
            return {"error": "The 'service_name' argument is required."}
        return ecosystem.trace_deployment_chain(self.db_manager, service_name)

    def find_blast_radius_tool(self, **args: Any) -> dict[str, Any]:
        """Compute blast radius for an infrastructure change."""
        target = _require_str_argument(args, "target")
        if target is None:
            return {"error": "The 'target' argument is required."}
        target_type = _require_str_argument(args, "target_type") or "repository"
        return ecosystem.find_blast_radius(
            self.db_manager,
            target,
            target_type,
        )

    def find_infra_resources_tool(self, **args: Any) -> dict[str, Any]:
        """Search infrastructure resources by query and category."""
        query_text = _require_str_argument(args, "query")
        if query_text is None:
            return {"error": "The 'query' argument is required."}
        category = args.get("category", "")
        return infra_queries.search_infra_resources(
            self.db_manager,
            query=query_text,
            types=[category] if category else None,
            environment=None,
            limit=50,
        )

    def analyze_infra_relationships_tool(self, **args: Any) -> dict[str, Any]:
        """Analyze relationships for an infrastructure target."""
        target = _require_str_argument(args, "target")
        if target is None:
            return {"error": "The 'target' argument is required."}
        relationship_type = _require_str_argument(args, "query_type")
        if relationship_type is None:
            return {"error": "The 'query_type' argument is required."}
        return infra_queries.get_infra_relationships(
            self.db_manager,
            target=target,
            relationship_type=relationship_type,
            environment=None,
        )

    def get_repo_summary_tool(self, **args: Any) -> dict[str, Any]:
        """Return a summary for one repository."""
        repo_name = _require_str_argument(args, "repo_name")
        if repo_name is None:
            return {"error": "The 'repo_name' argument is required."}
        return ecosystem.get_repo_summary(self.db_manager, repo_name)

    def get_repo_context_tool(self, **args: Any) -> dict[str, Any]:
        """Return repository context anchored by repository name."""
        repo_name = _require_str_argument(args, "repo_name")
        if repo_name is None:
            return {"error": "The 'repo_name' argument is required."}
        return repository_queries.get_repository_context(
            self.db_manager,
            repo_id=repo_name,
        )

    def resolve_entity_tool(self, **args: Any) -> dict[str, Any]:
        """Resolve a graph entity from a fuzzy or exact query."""
        query_text = _require_str_argument(args, "query")
        if query_text is None:
            return {"error": "The 'query' argument is required."}
        return entity_resolution_queries.resolve_entity(
            self.db_manager,
            query=query_text,
            types=args.get("types"),
            kinds=args.get("kinds"),
            environment=args.get("environment"),
            repo_id=args.get("repo_id"),
            exact=args.get("exact", False),
            limit=args.get("limit", 10),
        )

    def get_entity_context_tool(self, **args: Any) -> dict[str, Any]:
        """Return graph context for one entity identifier."""
        entity_id = _require_str_argument(args, "entity_id")
        if entity_id is None:
            return {"error": "The 'entity_id' argument is required."}
        return context_queries.get_entity_context(
            self.db_manager,
            entity_id=entity_id,
            environment=args.get("environment"),
        )

    def get_workload_context_tool(self, **args: Any) -> dict[str, Any]:
        """Return graph context for one workload identifier."""
        workload_id = _require_str_argument(args, "workload_id")
        if workload_id is None:
            return {"error": "The 'workload_id' argument is required."}
        return context_queries.get_workload_context(
            self.db_manager,
            workload_id=workload_id,
            environment=args.get("environment"),
        )

    def get_service_context_tool(self, **args: Any) -> dict[str, Any]:
        """Return service context or a structured alias error."""
        workload_id = _require_str_argument(args, "workload_id")
        if workload_id is None:
            return {"error": "The 'workload_id' argument is required."}
        try:
            return context_queries.get_service_context(
                self.db_manager,
                workload_id=workload_id,
                environment=args.get("environment"),
            )
        except context_queries.ServiceAliasError as exc:
            return {"error": str(exc)}

    def trace_resource_to_code_tool(self, **args: Any) -> dict[str, Any]:
        """Trace a cloud resource back to related code."""
        start = _require_str_argument(args, "start")
        if start is None:
            return {"error": "The 'start' argument is required."}
        return impact_queries.trace_resource_to_code(
            self.db_manager,
            start=start,
            environment=args.get("environment"),
            max_depth=args.get("max_depth", 8),
        )

    def explain_dependency_path_tool(self, **args: Any) -> dict[str, Any]:
        """Explain the dependency path between two graph entities."""
        source = _require_str_argument(args, "source")
        target = _require_str_argument(args, "target")
        if source is None or target is None:
            return {"error": "Both 'source' and 'target' arguments are required."}
        return impact_queries.explain_dependency_path(
            self.db_manager,
            source=source,
            target=target,
            environment=args.get("environment"),
        )

    def find_change_surface_tool(self, **args: Any) -> dict[str, Any]:
        """Find the change surface for a graph target."""
        target = _require_str_argument(args, "target")
        if target is None:
            return {"error": "The 'target' argument is required."}
        return impact_queries.find_change_surface(
            self.db_manager,
            target=target,
            environment=args.get("environment"),
        )

    def compare_environments_tool(self, **args: Any) -> dict[str, Any]:
        """Compare workload context across two environments."""
        workload_id = _require_str_argument(args, "workload_id")
        left = _require_str_argument(args, "left")
        right = _require_str_argument(args, "right")
        if workload_id is None or left is None or right is None:
            return {
                "error": "The 'workload_id', 'left', and 'right' arguments are required."
            }
        return compare_queries.compare_environments(
            self.db_manager,
            workload_id=workload_id,
            left=left,
            right=right,
        )

    def link_ecosystem_tool(self) -> dict[str, Any]:
        """Link repositories and workloads across the ecosystem graph."""
        return self.cross_repo_linker.link_all()

    async def handle_tool_call(
        self, tool_name: str, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Dispatch one MCP tool call to its server-side implementation.

        Args:
            tool_name: The MCP tool name provided by the client.
            args: The parsed tool arguments.

        Returns:
            The tool result payload or an error object.
        """
        tool_map = build_sync_tool_map(self)
        async_tools = build_async_tool_map(self)

        async_handler = async_tools.get(tool_name)
        if async_handler is not None:
            return await async_handler(**args)

        handler = tool_map.get(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}
        return await asyncio.to_thread(handler, **args)
