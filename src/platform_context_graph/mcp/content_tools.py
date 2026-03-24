"""Content-retrieval tool wrappers mixed into the MCP server."""

from __future__ import annotations

from typing import Any, Protocol

from ..query import content as content_queries

__all__ = ["ContentToolMixin"]


class _ContentRuntime(Protocol):
    """Structural type for the server state used by content tool helpers."""

    db_manager: Any


def _require_str_argument(args: dict[str, Any], key: str) -> str | None:
    """Return a non-empty string argument when present.

    Args:
        args: Raw tool arguments.
        key: Argument name to read.

    Returns:
        Stripped argument value when present, otherwise ``None``.
    """

    value = args.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class ContentToolMixin:
    """Provide content retrieval and search wrappers for ``MCPServer``."""

    def get_file_content_tool(self: _ContentRuntime, **args: Any) -> dict[str, Any]:
        """Return file content for a portable repository-relative path."""

        repo_id = _require_str_argument(args, "repo_id")
        relative_path = _require_str_argument(args, "relative_path")
        if repo_id is None or relative_path is None:
            return {
                "error": "The 'repo_id' and 'relative_path' arguments are required."
            }
        return content_queries.get_file_content(
            self.db_manager,
            repo_id=repo_id,
            relative_path=relative_path,
        )

    def get_file_lines_tool(self: _ContentRuntime, **args: Any) -> dict[str, Any]:
        """Return a file line range for a portable repository-relative path."""

        repo_id = _require_str_argument(args, "repo_id")
        relative_path = _require_str_argument(args, "relative_path")
        start_line = args.get("start_line")
        end_line = args.get("end_line")
        if repo_id is None or relative_path is None:
            return {
                "error": "The 'repo_id' and 'relative_path' arguments are required."
            }
        if not isinstance(start_line, int) or not isinstance(end_line, int):
            return {"error": "The 'start_line' and 'end_line' arguments are required."}
        return content_queries.get_file_lines(
            self.db_manager,
            repo_id=repo_id,
            relative_path=relative_path,
            start_line=start_line,
            end_line=end_line,
        )

    def get_entity_content_tool(self: _ContentRuntime, **args: Any) -> dict[str, Any]:
        """Return source content for one content-bearing graph entity."""

        entity_id = _require_str_argument(args, "entity_id")
        if entity_id is None:
            return {"error": "The 'entity_id' argument is required."}
        return content_queries.get_entity_content(
            self.db_manager,
            entity_id=entity_id,
        )

    def search_file_content_tool(self: _ContentRuntime, **args: Any) -> dict[str, Any]:
        """Search file content through the content store."""

        pattern = _require_str_argument(args, "pattern")
        if pattern is None:
            return {"error": "The 'pattern' argument is required."}
        return content_queries.search_file_content(
            self.db_manager,
            pattern=pattern,
            repo_ids=args.get("repo_ids"),
            languages=args.get("languages"),
            artifact_types=args.get("artifact_types"),
            template_dialects=args.get("template_dialects"),
            iac_relevant=args.get("iac_relevant"),
        )

    def search_entity_content_tool(
        self: _ContentRuntime, **args: Any
    ) -> dict[str, Any]:
        """Search entity snippets through the content store."""

        pattern = _require_str_argument(args, "pattern")
        if pattern is None:
            return {"error": "The 'pattern' argument is required."}
        return content_queries.search_entity_content(
            self.db_manager,
            pattern=pattern,
            entity_types=args.get("entity_types"),
            repo_ids=args.get("repo_ids"),
            languages=args.get("languages"),
            artifact_types=args.get("artifact_types"),
            template_dialects=args.get("template_dialects"),
            iac_relevant=args.get("iac_relevant"),
        )
