from __future__ import annotations

from unittest.mock import patch

from platform_context_graph.mcp import MCPServer


def test_trace_deployment_chain_tool_routes_explicit_shaping_controls() -> None:
    server = MCPServer.__new__(MCPServer)
    server.db_manager = object()

    with patch(
        "platform_context_graph.mcp.query_tools.ecosystem.trace_deployment_chain",
        return_value={"repository": {"name": "api-node-boats"}},
    ) as mock_trace:
        result = server.trace_deployment_chain_tool(
            service_name="api-node-boats",
            direct_only=False,
            max_depth=3,
            include_related_module_usage=True,
        )

    mock_trace.assert_called_once_with(
        server.db_manager,
        "api-node-boats",
        direct_only=False,
        max_depth=3,
        include_related_module_usage=True,
    )
    assert result["repository"]["name"] == "api-node-boats"


def test_trace_deployment_chain_tool_uses_hosted_focused_defaults() -> None:
    server = MCPServer.__new__(MCPServer)
    server.db_manager = object()

    with patch(
        "platform_context_graph.mcp.query_tools.ecosystem.trace_deployment_chain",
        return_value={"repository": {"name": "api-node-boats"}},
    ) as mock_trace:
        server.trace_deployment_chain_tool(service_name="api-node-boats")

    mock_trace.assert_called_once_with(
        server.db_manager,
        "api-node-boats",
        direct_only=True,
        max_depth=None,
        include_related_module_usage=False,
    )
