"""Runtime-status tool wrappers for the MCP server."""

from __future__ import annotations

from typing import Any, Protocol

from ..indexing.run_status import describe_index_run
from ..query import status as status_queries

__all__ = ["RuntimeStatusToolMixin"]


class _RuntimeStatusServer(Protocol):
    """Structural type for MCP tool helpers that need DB access."""

    db_manager: Any


class RuntimeStatusToolMixin:
    """Provide runtime-ingester MCP tool wrappers."""

    def list_ingesters_tool(
        self: _RuntimeStatusServer, **args: Any
    ) -> list[dict[str, Any]]:
        """Return the current status for all configured ingesters."""

        return status_queries.list_ingesters(self.db_manager)

    def get_ingester_status_tool(
        self: _RuntimeStatusServer, **args: Any
    ) -> dict[str, Any]:
        """Return runtime status for one ingester."""

        ingester = args.get("ingester", "repository")
        if not isinstance(ingester, str) or not ingester.strip():
            return {"error": "The 'ingester' argument must be a non-empty string."}
        if ingester not in status_queries.KNOWN_INGESTERS:
            return {"error": f"Unknown ingester: {ingester}"}
        return status_queries.get_ingester_status(self.db_manager, ingester=ingester)

    def get_index_status_tool(
        self: _RuntimeStatusServer, **args: Any
    ) -> dict[str, Any]:
        """Return checkpointed index-run status for a path or run ID."""

        target = args.get("target")
        resolved_target = status_queries.resolve_index_status_target(
            self.db_manager,
            target=target,
            ingester="repository",
        )
        summary = describe_index_run(resolved_target or ".")
        if summary is None:
            return {"error": "Index status not found"}
        return summary
