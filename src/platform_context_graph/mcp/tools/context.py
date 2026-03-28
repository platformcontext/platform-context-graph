"""Tool definitions for entity resolution and contextual graph lookups."""

CONTEXT_TOOLS = {
    "resolve_entity": {
        "name": "resolve_entity",
        "description": "Resolve a fuzzy or user-supplied identifier into ranked canonical graph entities such as workloads, repositories, and cloud resources.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Free-form identifier or search string to resolve.",
                },
                "types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional entity type filter.",
                },
                "kinds": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional workload kind filter.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment filter, such as prod or stage.",
                },
                "repo_id": {
                    "type": "string",
                    "description": "Optional canonical repository identifier to scope results.",
                },
                "exact": {
                    "type": "boolean",
                    "description": "If true, only exact textual or canonical identifier matches are returned.",
                    "default": False,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of ranked matches to return.",
                    "default": 10,
                },
            },
            "required": ["query"],
        },
    },
    "get_entity_context": {
        "name": "get_entity_context",
        "description": "Get context for a canonical entity ID, including workload and workload-instance entities.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Canonical entity identifier.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment override for logical workload entities.",
                },
            },
            "required": ["entity_id"],
        },
    },
    "get_workload_context": {
        "name": "get_workload_context",
        "description": "Get logical or environment-specific context for a canonical workload identifier.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workload_id": {
                    "type": "string",
                    "description": "Canonical workload identifier.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment to select a workload instance view.",
                },
            },
            "required": ["workload_id"],
        },
    },
    "get_workload_story": {
        "name": "get_workload_story",
        "description": "Get a structured story for a workload: subject, story lines, story sections, deployment overview, evidence, limitations, and drill-down handles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workload_id": {
                    "type": "string",
                    "description": "Canonical workload identifier or plain workload name.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment to select a workload instance view.",
                },
            },
            "required": ["workload_id"],
        },
    },
    "get_service_context": {
        "name": "get_service_context",
        "description": "Alias for workload context that only accepts canonical workload identifiers for service workloads.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workload_id": {
                    "type": "string",
                    "description": "Canonical workload identifier for a service workload.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment to select a service instance view.",
                },
            },
            "required": ["workload_id"],
        },
    },
    "get_service_story": {
        "name": "get_service_story",
        "description": "Alias for workload story that accepts service workload identifiers or plain service names and returns a structured story contract.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workload_id": {
                    "type": "string",
                    "description": "Canonical workload identifier or plain service name.",
                },
                "environment": {
                    "type": "string",
                    "description": "Optional environment to select a service instance view.",
                },
            },
            "required": ["workload_id"],
        },
    },
}

__all__ = ["CONTEXT_TOOLS"]
