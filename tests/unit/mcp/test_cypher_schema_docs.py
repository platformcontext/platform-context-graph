"""Tests for Cypher schema guidance exposed to MCP users."""

from __future__ import annotations

from platform_context_graph.mcp.tools.codebase import CODEBASE_TOOLS
from platform_context_graph.mcp.tools.ecosystem import ECOSYSTEM_TOOLS
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


def test_llm_prompt_schema_reference_mentions_terraform_module_attributes() -> None:
    """The system prompt should expose richer Terraform module properties."""

    assert "TerraformModule" in LLM_SYSTEM_PROMPT
    assert "deployment_name" in LLM_SYSTEM_PROMPT
    assert "repo_name" in LLM_SYSTEM_PROMPT
    assert "create_deploy" in LLM_SYSTEM_PROMPT
    assert "cluster_name" in LLM_SYSTEM_PROMPT
    assert "deploy_entry_point" in LLM_SYSTEM_PROMPT


def test_ecosystem_tool_docs_prefer_top_level_story_fields() -> None:
    """Summary and deployment-chain tools should advertise story-first reading."""

    summary_description = ECOSYSTEM_TOOLS["get_repo_summary"]["description"]
    trace_description = ECOSYSTEM_TOOLS["trace_deployment_chain"]["description"]

    assert "story" in summary_description
    assert "story" in trace_description
    assert "top-level" in summary_description
    assert "top-level" in trace_description


def test_llm_prompt_repository_sop_prefers_story_before_detail() -> None:
    """The prompt should steer callers toward the top-level story first."""

    assert "story" in LLM_SYSTEM_PROMPT
    assert "top-level `story`" in LLM_SYSTEM_PROMPT


def test_codebase_tool_schemas_use_canonical_repo_id_and_http_search_defaults() -> None:
    """The MCP code tool schema should mirror the HTTP code search contract."""

    find_code_schema = CODEBASE_TOOLS["find_code"]["inputSchema"]["properties"]
    relationships_schema = CODEBASE_TOOLS["analyze_code_relationships"]["inputSchema"][
        "properties"
    ]
    dead_code_schema = CODEBASE_TOOLS["find_dead_code"]["inputSchema"]["properties"]
    complexity_schema = CODEBASE_TOOLS["calculate_cyclomatic_complexity"][
        "inputSchema"
    ]["properties"]

    assert "repo_id" in find_code_schema
    assert "repo_path" not in find_code_schema
    assert "exact" in find_code_schema
    assert find_code_schema["exact"]["default"] is False
    assert "fuzzy_search" not in find_code_schema
    assert find_code_schema["limit"]["default"] == 10

    assert "repo_id" in relationships_schema
    assert "repo_path" not in relationships_schema

    assert "repo_id" in dead_code_schema
    assert "repo_path" not in dead_code_schema
    assert dead_code_schema["scope"]["default"] == "auto"

    assert "repo_id" in complexity_schema
    assert "repo_path" not in complexity_schema
