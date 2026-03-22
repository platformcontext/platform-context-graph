"""Tool definitions for runtime worker status."""

RUNTIME_TOOLS = {
    "get_index_status": {
        "name": "get_index_status",
        "description": "Return the current worker sync/index status, including degraded states, retry timing, and repo progress counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "component": {
                    "type": "string",
                    "description": "Runtime component name. Defaults to worker.",
                    "default": "worker",
                }
            },
        },
    }
}

__all__ = ["RUNTIME_TOOLS"]
