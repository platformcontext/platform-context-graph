"""Integration tests for MCP content tool routing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from platform_context_graph.mcp import MCPServer
from platform_context_graph.mcp.tool_registry import TOOLS


@pytest.fixture
def mock_server() -> MCPServer:
    """Create a server with its heavy collaborators mocked out."""

    with patch("platform_context_graph.mcp.server.get_database_manager") as mock_get_db:
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db

        with (
            patch("platform_context_graph.mcp.server.JobManager"),
            patch("platform_context_graph.mcp.server.GraphBuilder"),
            patch("platform_context_graph.mcp.server.CodeFinder"),
            patch("platform_context_graph.mcp.server.CodeWatcher"),
        ):
            return MCPServer()


def test_content_tools_are_registered() -> None:
    """Expose the content retrieval tools in the public MCP registry."""

    assert "get_file_content" in TOOLS
    assert "get_file_lines" in TOOLS
    assert "get_entity_content" in TOOLS
    assert "search_file_content" in TOOLS
    assert "search_entity_content" in TOOLS


def test_get_file_content_wrapper_routes_through_content_query_service(
    mock_server: MCPServer,
) -> None:
    """Delegate file-content retrieval to the shared content query layer."""

    with patch(
        "platform_context_graph.mcp.content_tools.content_queries.get_file_content"
    ) as mock_get_file_content:
        mock_get_file_content.return_value = {
            "available": True,
            "repo_id": "repository:r_ab12cd34",
            "relative_path": "src/payments.py",
            "content": "print('payments')\n",
            "source_backend": "workspace",
        }

        result = mock_server.get_file_content_tool(
            repo_id="repository:r_ab12cd34",
            relative_path="src/payments.py",
        )

    mock_get_file_content.assert_called_once_with(
        mock_server.db_manager,
        repo_id="repository:r_ab12cd34",
        relative_path="src/payments.py",
    )
    assert result["source_backend"] == "workspace"


def test_tools_call_does_not_trigger_repo_access_when_server_has_workspace_content(
    mock_server: MCPServer,
) -> None:
    """Avoid local-checkout elicitation when the server already returned content."""

    async def run_test() -> None:
        await mock_server._handle_jsonrpc_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"capabilities": {"elicitation": {}}},
            }
        )
        mock_server._client_request_handler = AsyncMock()

        with patch.object(
            mock_server,
            "handle_tool_call",
            AsyncMock(
                return_value={
                    "available": True,
                    "repo_id": "repository:r_ab12cd34",
                    "relative_path": "src/payments.py",
                    "content": "print('payments')\n",
                    "source_backend": "workspace",
                }
            ),
        ):
            response, status = await mock_server._handle_jsonrpc_request(
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "get_file_content",
                        "arguments": {
                            "repo_id": "repository:r_ab12cd34",
                            "relative_path": "src/payments.py",
                        },
                    },
                }
            )

        assert status == 200
        payload = response["result"]["content"][0]["text"]
        assert '"source_backend": "workspace"' in payload
        assert '"relative_path": "src/payments.py"' in payload
        mock_server._client_request_handler.assert_not_awaited()

    asyncio.run(run_test())


def test_search_file_content_wrapper_passes_metadata_filters(
    mock_server: MCPServer,
) -> None:
    """Metadata filters should flow through the MCP file search wrapper."""

    with patch(
        "platform_context_graph.mcp.content_tools.content_queries.search_file_content"
    ) as mock_search_file_content:
        mock_search_file_content.return_value = {"pattern": "Dockerfile", "matches": []}

        mock_server.search_file_content_tool(
            pattern="Dockerfile",
            artifact_types=["dockerfile"],
            template_dialects=["jinja"],
            iac_relevant=True,
        )

    mock_search_file_content.assert_called_once_with(
        mock_server.db_manager,
        pattern="Dockerfile",
        repo_ids=None,
        languages=None,
        artifact_types=["dockerfile"],
        template_dialects=["jinja"],
        iac_relevant=True,
    )
