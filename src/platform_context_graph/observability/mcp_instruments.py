"""MCP tool instrumentation helpers for observability."""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from .structured_logging import emit_structured_log

if TYPE_CHECKING:
    from .runtime import ObservabilityRuntime

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def instrument_mcp_tool(
    runtime: ObservabilityRuntime,
    *,
    tool_name: str,
    handler: Callable[..., Any],
) -> Iterator[None]:
    """Instrument one MCP tool invocation with spans, metrics, and logs.

    Args:
        runtime: The active observability runtime.
        tool_name: The MCP tool name being invoked.
        handler: The tool handler function (for reference).

    Yields:
        ``None`` while the tool executes.
    """
    start = time.perf_counter()
    status = "succeeded"

    with runtime.start_span(
        "pcg.mcp.tool_call",
        component="mcp",
        attributes={
            "pcg.mcp.tool_name": tool_name,
            "pcg.component": "mcp",
            "pcg.transport": "mcp",
        },
    ):
        try:
            yield
        except Exception:
            status = "failed"
            raise
        finally:
            duration = time.perf_counter() - start
            _record_tool_metrics(
                runtime,
                tool_name=tool_name,
                duration_seconds=duration,
                status=status,
            )
            emit_structured_log(
                logger,
                logging.INFO,
                f"MCP tool call completed: {tool_name}",
                event_name="mcp.tool.instrumented",
                extra_keys={
                    "tool_name": tool_name,
                    "duration_seconds": round(duration, 6),
                    "status": status,
                },
            )


def _record_tool_metrics(
    runtime: ObservabilityRuntime,
    *,
    tool_name: str,
    duration_seconds: float,
    status: str,
) -> None:
    """Record MCP tool metrics to the observability runtime.

    Args:
        runtime: The active observability runtime.
        tool_name: The MCP tool name.
        duration_seconds: The tool execution duration in seconds.
        status: The tool execution status (succeeded/failed).
    """
    if not runtime.enabled:
        return

    attrs = {
        "tool_name": tool_name,
        "status": status,
    }

    if hasattr(runtime, "mcp_tool_calls_total") and runtime.mcp_tool_calls_total:
        runtime.mcp_tool_calls_total.add(1, attrs)

    if hasattr(runtime, "mcp_tool_duration") and runtime.mcp_tool_duration:
        runtime.mcp_tool_duration.record(duration_seconds, {"tool_name": tool_name})


__all__ = ["instrument_mcp_tool"]
