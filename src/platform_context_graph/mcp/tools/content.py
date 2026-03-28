"""Tool definitions for content retrieval and indexed source search."""

CONTENT_TOOLS = {
    "get_file_content": {
        "name": "get_file_content",
        "description": (
            "Return source for a repo-relative file using either a canonical "
            "repository identifier or a plain repository name/slug. This reads "
            "from the server-side content store or workspace and does not "
            "require a raw filesystem path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {
                    "type": "string",
                    "description": "Canonical repository identifier or plain repository name.",
                },
                "relative_path": {
                    "type": "string",
                    "description": "Portable repo-relative file path.",
                },
            },
            "required": ["repo_id", "relative_path"],
        },
    },
    "get_file_lines": {
        "name": "get_file_lines",
        "description": (
            "Return a line range for a repo-relative file using either "
            "canonical repository identity or a plain repository name."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_id": {"type": "string"},
                "relative_path": {"type": "string"},
                "start_line": {"type": "integer"},
                "end_line": {"type": "integer"},
            },
            "required": ["repo_id", "relative_path", "start_line", "end_line"],
        },
    },
    "get_entity_content": {
        "name": "get_entity_content",
        "description": (
            "Return source for a content-bearing graph entity using its canonical "
            "content entity identifier."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entity_id": {
                    "type": "string",
                    "description": "Canonical content entity identifier.",
                }
            },
            "required": ["entity_id"],
        },
    },
    "search_file_content": {
        "name": "search_file_content",
        "description": (
            "Search indexed file content across repositories using the PostgreSQL "
            "content store."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "repo_ids": {"type": "array", "items": {"type": "string"}},
                "languages": {"type": "array", "items": {"type": "string"}},
                "artifact_types": {"type": "array", "items": {"type": "string"}},
                "template_dialects": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "iac_relevant": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
    },
    "search_entity_content": {
        "name": "search_entity_content",
        "description": (
            "Search cached entity source snippets across repositories using the "
            "PostgreSQL content store."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "entity_types": {"type": "array", "items": {"type": "string"}},
                "repo_ids": {"type": "array", "items": {"type": "string"}},
                "languages": {"type": "array", "items": {"type": "string"}},
                "artifact_types": {"type": "array", "items": {"type": "string"}},
                "template_dialects": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "iac_relevant": {"type": "boolean"},
            },
            "required": ["pattern"],
        },
    },
}

__all__ = ["CONTENT_TOOLS"]
