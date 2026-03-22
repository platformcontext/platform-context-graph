"""Transport and JSON-RPC helpers for the MCP server."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
import traceback
from typing import Any, Awaitable, Callable, Protocol

from ..observability import initialize_observability
from ..prompts import LLM_SYSTEM_PROMPT
from ..utils.debug_log import debug_logger, error_logger, info_logger, warning_logger


class _TransportRuntime(Protocol):
    """Structural type for the server state required by transport helpers."""

    observability: Any
    client_capabilities: dict[str, Any]
    tools: dict[str, Any]
    code_watcher: Any
    db_manager: Any
    loop: asyncio.AbstractEventLoop
    _pending_client_requests: dict[str, asyncio.Future[dict[str, Any]]]
    _next_client_request_id: int
    _client_request_handler: (
        Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None
    )
    _stdio_write_lock: asyncio.Lock | None

    async def handle_tool_call(
        self, tool_name: str | None, args: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute one MCP tool call and return the JSON-serializable result."""
        ...

    async def _apply_repo_access_handoff(
        self, payload: Any, *, transport: str
    ) -> Any:
        """Attach repo-access handoff metadata for the active transport when needed."""
        ...

    async def _send_stdio_message(self, message: dict[str, Any]) -> None:
        """Write one JSON-RPC message to the stdio transport."""
        ...


class ServerTransportMixin:
    """Provide JSON-RPC request handling and transport loops for ``MCPServer``."""

    async def _handle_jsonrpc_request(
        self: _TransportRuntime,
        body: dict[str, Any],
        transport: str = "jsonrpc-stdio",
    ) -> tuple[dict[str, Any] | None, int]:
        """Handle one JSON-RPC request for any supported transport.

        Args:
            body: The parsed JSON-RPC request body.
            transport: The active transport identifier.

        Returns:
            A ``(response, status_code)`` tuple. Notifications return
            ``(None, 204)``.
        """
        runtime = initialize_observability(component="mcp")
        self.observability = runtime
        method = body.get("method")
        params = body.get("params", {})
        request_id = body.get("id")
        request_started = time.perf_counter()
        request_success = False
        span_attributes = {
            "pcg.jsonrpc.method": method or "unknown",
            "pcg.transport": transport,
        }

        with runtime.request_context(component="mcp", transport=transport):
            with runtime.start_span(
                "pcg.mcp.request",
                component="mcp",
                attributes=span_attributes,
            ) as request_span:
                try:
                    if request_id is not None:
                        info_logger(f"JSON-RPC request method={method} id={request_id}")
                    else:
                        debug_logger(f"JSON-RPC notification method={method}")

                    if method == "initialize":
                        self.client_capabilities = dict(
                            params.get("capabilities") or {}
                        )
                        request_success = True
                        return {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {
                                "protocolVersion": "2025-03-26",
                                "serverInfo": {
                                    "name": "PlatformContextGraph",
                                    "version": "0.1.0",
                                    "systemPrompt": LLM_SYSTEM_PROMPT,
                                },
                                "capabilities": {"tools": {"listTools": True}},
                            },
                        }, 200

                    if method == "tools/list":
                        request_success = True
                        return {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "result": {"tools": list(self.tools.values())},
                        }, 200

                    if method == "tools/call":
                        tool_name = params.get("name")
                        args = params.get("arguments", {})
                        info_logger(
                            f"tools/call -> {tool_name} args={list(args.keys())}"
                        )
                        tool_started = time.perf_counter()
                        tool_success = False
                        tool_metric_name = str(tool_name or "unknown")
                        with runtime.start_span(
                            "pcg.mcp.tool",
                            component="mcp",
                            attributes={
                                "pcg.tool.name": tool_metric_name,
                                "pcg.transport": transport,
                            },
                        ) as tool_span:
                            try:
                                result = await self.handle_tool_call(tool_name, args)
                                result = await self._apply_repo_access_handoff(
                                    result, transport=transport
                                )
                                tool_success = "error" not in result
                                if "error" in result:
                                    if tool_span is not None:
                                        tool_span.set_attribute(
                                            "pcg.tool.success", False
                                        )
                                    return {
                                        "jsonrpc": "2.0",
                                        "id": request_id,
                                        "error": {
                                            "code": -32000,
                                            "message": "Tool execution error",
                                            "data": result,
                                        },
                                    }, 200
                                request_success = True
                                if tool_span is not None:
                                    tool_span.set_attribute("pcg.tool.success", True)
                                return {
                                    "jsonrpc": "2.0",
                                    "id": request_id,
                                    "result": {
                                        "content": [
                                            {
                                                "type": "text",
                                                "text": json.dumps(result, indent=2),
                                            }
                                        ]
                                    },
                                }, 200
                            except Exception as exc:
                                if tool_span is not None:
                                    tool_span.record_exception(exc)
                                raise
                            finally:
                                runtime.record_mcp_tool(
                                    tool_name=tool_metric_name,
                                    transport=transport,
                                    duration_seconds=time.perf_counter() - tool_started,
                                    success=tool_success,
                                )

                    if request_id is None:
                        request_success = True
                        return None, 204

                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"Method not found: {method}",
                        },
                    }, 200
                except Exception as exc:
                    if request_span is not None:
                        request_span.record_exception(exc)
                    raise
                finally:
                    runtime.record_mcp_request(
                        method=str(method or "unknown"),
                        transport=transport,
                        duration_seconds=time.perf_counter() - request_started,
                        success=request_success,
                    )

    async def run(self: _TransportRuntime) -> None:
        """Run the stdio JSON-RPC server loop."""
        print(
            "MCP Server is running. Waiting for requests...",
            file=sys.stderr,
            flush=True,
        )
        self.code_watcher.start()
        self._stdio_write_lock = asyncio.Lock()
        incoming_requests: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def read_loop() -> None:
            """Read inbound stdio JSON-RPC messages into a queue."""
            loop = asyncio.get_running_loop()
            while True:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    await incoming_requests.put(None)
                    return
                try:
                    message = json.loads(line.strip())
                except Exception:
                    warning_logger(
                        "Ignoring malformed JSON-RPC message received on stdio"
                    )
                    continue
                if (
                    isinstance(message, dict)
                    and message.get("id") in self._pending_client_requests
                    and "method" not in message
                ):
                    future = self._pending_client_requests.pop(message["id"])
                    if "error" in message:
                        future.set_exception(RuntimeError(json.dumps(message["error"])))
                    else:
                        future.set_result(message.get("result", {}))
                    continue
                await incoming_requests.put(message)

        async def stdio_request_handler(
            method: str, params: dict[str, Any]
        ) -> dict[str, Any]:
            """Send an outbound JSON-RPC request to the connected stdio client."""
            request_id = f"pcg-elicit-{self._next_client_request_id}"
            self._next_client_request_id += 1
            future: asyncio.Future[dict[str, Any]] = self.loop.create_future()
            self._pending_client_requests[request_id] = future
            await self._send_stdio_message(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                }
            )
            try:
                return await future
            finally:
                self._pending_client_requests.pop(request_id, None)

        self._client_request_handler = stdio_request_handler
        reader_task = asyncio.create_task(read_loop())
        try:
            while True:
                request = await incoming_requests.get()
                if request is None:
                    debug_logger("Client disconnected (EOF received). Shutting down.")
                    break
                try:
                    response, _ = await self._handle_jsonrpc_request(
                        request, transport="jsonrpc-stdio"
                    )
                    if response is not None:
                        await self._send_stdio_message(response)
                except Exception as exc:
                    error_logger(
                        f"Error processing request: {exc}\n{traceback.format_exc()}"
                    )
                    request_id = "unknown"
                    if isinstance(request, dict):
                        request_id = request.get("id", "unknown")
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32603,
                            "message": f"Internal error: {exc}",
                            "data": traceback.format_exc(),
                        },
                    }
                    await self._send_stdio_message(error_response)
        finally:
            self._client_request_handler = None
            reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await reader_task

    async def _send_stdio_message(self, payload: dict[str, Any]) -> None:
        """Write one JSON-RPC payload to stdout."""
        if self._stdio_write_lock is None:
            print(json.dumps(payload), flush=True)
            return
        async with self._stdio_write_lock:
            print(json.dumps(payload), flush=True)

    async def run_sse(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """Run the MCP server over HTTP with an SSE keepalive endpoint.

        Args:
            host: The interface to bind.
            port: The TCP port to bind.
        """
        from fastapi import FastAPI, Request
        from fastapi.responses import JSONResponse, StreamingResponse
        from starlette.responses import Response
        import uvicorn

        app = FastAPI(title="PlatformContextGraph MCP Server")
        self.code_watcher.start()

        @app.get("/health")
        async def health() -> dict[str, str]:
            """Return a basic health payload."""
            return {"status": "ok"}

        @app.post("/message")
        async def message(request: Request) -> JSONResponse | Response:
            """Handle one JSON-RPC request over HTTP."""
            try:
                body = await request.json()
            except (json.JSONDecodeError, ValueError):
                return JSONResponse(
                    status_code=400,
                    content={
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "Parse error"},
                    },
                )

            response, status_code = await self._handle_jsonrpc_request(
                body, transport="jsonrpc-http"
            )
            if response is None:
                return Response(status_code=204)
            return JSONResponse(content=response, status_code=status_code)

        @app.get("/sse")
        async def sse() -> StreamingResponse:
            """Stream keepalive events for SSE clients."""

            async def event_stream():
                """Yield periodic keepalive events."""
                while True:
                    yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                    await asyncio.sleep(30)

            return StreamingResponse(event_stream(), media_type="text/event-stream")

        info_logger(f"Starting SSE transport on {host}:{port}")
        info_logger(f"Database connected: {self.db_manager.is_connected()}")
        info_logger(f"Tools registered: {len(self.tools)}")
        config = uvicorn.Config(app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    def shutdown(self) -> None:
        """Stop watchers and close the database driver."""
        debug_logger("Shutting down server...")
        self.code_watcher.stop()
        self.db_manager.close_driver()
