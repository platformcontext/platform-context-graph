"""Tests for Cypher schema guidance exposed to MCP users."""

from __future__ import annotations

from platform_context_graph.mcp.tools.codebase import CODEBASE_TOOLS
from platform_context_graph.prompts import LLM_SYSTEM_PROMPT


def test_execute_cypher_query_tool_documents_directory_and_repo_contains() -> None:
    """The Cypher fallback tool should describe the flat repo-file edge."""

    description = CODEBASE_TOOLS["execute_cypher_query"]["description"]

    assert "Directory" in description
    assert "REPO_CONTAINS" in description
    assert "CONTAINS*" in description


def test_llm_prompt_schema_reference_mentions_repo_contains() -> None:
    """The system prompt should teach the new file traversal shape."""

    assert "Directory" in LLM_SYSTEM_PROMPT
    assert "REPO_CONTAINS" in LLM_SYSTEM_PROMPT
