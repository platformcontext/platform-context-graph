"""Runtime-status tool wrappers for the MCP server."""

from __future__ import annotations

from typing import Any, Protocol

from ..query import status as status_queries

__all__ = ["RuntimeStatusToolMixin"]


class _RuntimeStatusServer(Protocol):
    """Structural type for MCP tool helpers that need DB access."""

    db_manager: Any


class RuntimeStatusToolMixin:
    """Provide runtime-status MCP tool wrappers."""

    def get_index_status_tool(
        self: _RuntimeStatusServer, **args: Any
    ) -> dict[str, Any]:
        """Return runtime worker status for one component."""

        component = args.get("component", "worker")
        if not isinstance(component, str) or not component.strip():
            return {"error": "The 'component' argument must be a non-empty string."}
        return status_queries.get_index_status(self.db_manager, component=component)
