# MCP Package

This package contains the Model Context Protocol server, transport helpers, and
tool registry used by PlatformContextGraph.

Key boundaries:
- `server.py`: MCP server orchestration and tool dispatch.
- `transport.py`: JSON-RPC and stdio transport handling.
- `repo_access.py`: local-checkout handoff and elicitation support.
- `tool_registry.py`: aggregated MCP tool definitions.
- `tools/`: MCP tool manifests and handler functions.
