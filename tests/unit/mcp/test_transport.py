"""Unit tests for MCP transport helpers."""

from __future__ import annotations

import asyncio
import io
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from platform_context_graph.mcp import MCPServer


def _build_server() -> MCPServer:
    """Construct an MCP server with external dependencies patched out."""

    with patch("platform_context_graph.mcp.server.get_database_manager") as mock_get_db:
        mock_db = MagicMock()
        mock_db.get_driver.return_value = MagicMock()
        mock_db.is_connected.return_value = True
        mock_get_db.return_value = mock_db

        with (
            patch("platform_context_graph.mcp.server.JobManager"),
            patch("platform_context_graph.mcp.server.GraphBuilder"),
            patch("platform_context_graph.mcp.server.CodeFinder"),
            patch("platform_context_graph.mcp.server.CodeWatcher"),
        ):
            return MCPServer()


def test_stdio_transport_sanitizes_internal_errors() -> None:
    """Stdio clients should not receive server tracebacks or exception details."""

    server = _build_server()
    captured_messages: list[dict[str, object]] = []

    async def _capture(payload: dict[str, object]) -> None:
        captured_messages.append(payload)

    server._send_stdio_message = _capture  # type: ignore[method-assign]
    server.handle_tool_call = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

    request = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "find_code",
                "arguments": {"query": "payments"},
            },
        }
    )

    async def run_test() -> None:
        with (
            patch.object(sys, "stdin", io.StringIO(f"{request}\n")),
            patch.object(sys, "stderr", io.StringIO()),
        ):
            await server.run()

    asyncio.run(run_test())

    assert len(captured_messages) == 1
    payload = captured_messages[0]
    error = payload["error"]
    assert isinstance(error, dict)
    assert error["message"] == "Internal error"
    assert error["data"] == {"request_id": 7}
    serialized = json.dumps(payload)
    assert "Traceback" not in serialized
    assert "boom" not in serialized
