"""Tool definitions for runtime ingester status."""

RUNTIME_TOOLS = {
    "list_ingesters": {
        "name": "list_ingesters",
        "description": "Return the current status for the configured ingesters.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    "get_ingester_status": {
        "name": "get_ingester_status",
        "description": "Return the current status for one ingester, including degraded states, retry timing, and repository progress counts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ingester": {
                    "type": "string",
                    "description": "Ingester name. Defaults to repository.",
                    "default": "repository",
                }
            },
        },
    },
}

__all__ = ["RUNTIME_TOOLS"]
