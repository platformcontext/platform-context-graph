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
    "get_index_status": {
        "name": "get_index_status",
        "description": "Return the latest checkpointed index status for a workspace path, repository path, repository name, or run ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Optional workspace path, repository path, repository name, or checkpoint run ID. Defaults to the configured checkpoint root for the repository ingester.",
                }
            },
        },
    },
}

__all__ = ["RUNTIME_TOOLS"]
