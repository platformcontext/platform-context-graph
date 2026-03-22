"""Read-only graph query tool wrappers for the MCP server."""

from __future__ import annotations

from typing import Any, Protocol

from ..query import compare as compare_queries
from ..query import context as context_queries
from ..query import entity_resolution as entity_resolution_queries
from ..query import impact as impact_queries
from ..query import infra as infra_queries
from ..query import repositories as repository_queries
from .tools.handlers import ecosystem
from .tool_args import require_str_argument

__all__ = ["QueryToolMixin"]


class _QueryRuntime(Protocol):
    """Structural type for server state required by read-only query tools."""

    db_manager: Any


class QueryToolMixin:
    """Provide read-only graph query wrappers for ``MCPServer``."""

    def get_ecosystem_overview_tool(self: _QueryRuntime) -> dict[str, Any]:
        """Return a high-level ecosystem overview."""

        return infra_queries.get_ecosystem_overview(self.db_manager)

    def trace_deployment_chain_tool(
        self: _QueryRuntime, **args: Any
    ) -> dict[str, Any]:
        """Trace deployment relationships across the indexed ecosystem."""

        service_name = require_str_argument(args, "service_name")
        if service_name is None:
            return {"error": "The 'service_name' argument is required."}
        return ecosystem.trace_deployment_chain(self.db_manager, service_name)

    def find_blast_radius_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Compute blast radius for an infrastructure change."""

        target = require_str_argument(args, "target")
        if target is None:
            return {"error": "The 'target' argument is required."}
        target_type = require_str_argument(args, "target_type") or "repository"
        return ecosystem.find_blast_radius(self.db_manager, target, target_type)

    def find_infra_resources_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Search infrastructure resources by query and category."""

        query_text = require_str_argument(args, "query")
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

    def analyze_infra_relationships_tool(
        self: _QueryRuntime, **args: Any
    ) -> dict[str, Any]:
        """Analyze relationships for an infrastructure target."""

        target = require_str_argument(args, "target")
        if target is None:
            return {"error": "The 'target' argument is required."}
        relationship_type = require_str_argument(args, "query_type")
        if relationship_type is None:
            return {"error": "The 'query_type' argument is required."}
        return infra_queries.get_infra_relationships(
            self.db_manager,
            target=target,
            relationship_type=relationship_type,
            environment=None,
        )

    def get_repo_summary_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Return a summary for one repository."""

        repo_name = require_str_argument(args, "repo_name")
        if repo_name is None:
            return {"error": "The 'repo_name' argument is required."}
        return ecosystem.get_repo_summary(self.db_manager, repo_name)

    def get_repo_context_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Return repository context anchored by repository name."""

        repo_name = require_str_argument(args, "repo_name")
        if repo_name is None:
            return {"error": "The 'repo_name' argument is required."}
        return repository_queries.get_repository_context(
            self.db_manager,
            repo_id=repo_name,
        )

    def resolve_entity_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Resolve a graph entity from a fuzzy or exact query."""

        query_text = require_str_argument(args, "query")
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

    def get_entity_context_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Return graph context for one entity identifier."""

        entity_id = require_str_argument(args, "entity_id")
        if entity_id is None:
            return {"error": "The 'entity_id' argument is required."}
        return context_queries.get_entity_context(
            self.db_manager,
            entity_id=entity_id,
            environment=args.get("environment"),
        )

    def get_workload_context_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Return graph context for one workload identifier."""

        workload_id = require_str_argument(args, "workload_id")
        if workload_id is None:
            return {"error": "The 'workload_id' argument is required."}
        return context_queries.get_workload_context(
            self.db_manager,
            workload_id=workload_id,
            environment=args.get("environment"),
        )

    def get_service_context_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Return service context or a structured alias error."""

        workload_id = require_str_argument(args, "workload_id")
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

    def trace_resource_to_code_tool(
        self: _QueryRuntime, **args: Any
    ) -> dict[str, Any]:
        """Trace a cloud resource back to related code."""

        start = require_str_argument(args, "start")
        if start is None:
            return {"error": "The 'start' argument is required."}
        return impact_queries.trace_resource_to_code(
            self.db_manager,
            start=start,
            environment=args.get("environment"),
            max_depth=args.get("max_depth", 8),
        )

    def explain_dependency_path_tool(
        self: _QueryRuntime, **args: Any
    ) -> dict[str, Any]:
        """Explain the dependency path between two graph entities."""

        source = require_str_argument(args, "source")
        target = require_str_argument(args, "target")
        if source is None or target is None:
            return {"error": "Both 'source' and 'target' arguments are required."}
        return impact_queries.explain_dependency_path(
            self.db_manager,
            source=source,
            target=target,
            environment=args.get("environment"),
        )

    def find_change_surface_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Find the change surface for a graph target."""

        target = require_str_argument(args, "target")
        if target is None:
            return {"error": "The 'target' argument is required."}
        return impact_queries.find_change_surface(
            self.db_manager,
            target=target,
            environment=args.get("environment"),
        )

    def compare_environments_tool(self: _QueryRuntime, **args: Any) -> dict[str, Any]:
        """Compare workload context across two environments."""

        workload_id = require_str_argument(args, "workload_id")
        left = require_str_argument(args, "left")
        right = require_str_argument(args, "right")
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
