"""Aggregate MCP tool definitions exposed by the server import surface."""

from .tools.codebase import CODEBASE_TOOLS
from .tools.content import CONTENT_TOOLS
from .tools.context import CONTEXT_TOOLS
from .tools.ecosystem import ECOSYSTEM_TOOLS

TOOLS = {
    **CODEBASE_TOOLS,
    **CONTENT_TOOLS,
    **ECOSYSTEM_TOOLS,
    **CONTEXT_TOOLS,
}

__all__ = ["TOOLS"]
