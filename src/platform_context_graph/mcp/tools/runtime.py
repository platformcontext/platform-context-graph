"""Tool definitions for runtime worker status."""

RUNTIME_TOOLS = {
    "get_index_status": {
        "name": "get_index_status",
        "description": "Return the current repo-sync/index worker status, including degraded states and retry timing.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "component": {
                    "type": "string",
                    "description": "Runtime component name. Defaults to repo-sync.",
                    "default": "repo-sync",
                }
            },
        },
    }
}

__all__ = ["RUNTIME_TOOLS"]
