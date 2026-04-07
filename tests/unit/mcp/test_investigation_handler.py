"""Unit tests for the service investigation MCP tool wrapper."""

from __future__ import annotations

from types import SimpleNamespace

from platform_context_graph.mcp.query_tools import QueryToolMixin


class _Runtime(QueryToolMixin):
    """Minimal runtime wrapper exposing the MCP query-tool mixin."""

    def __init__(self) -> None:
        self.db_manager = object()


def test_investigate_service_tool_delegates_to_query_module(monkeypatch) -> None:
    """Route MCP investigation calls through the query-layer orchestrator."""

    def fake_investigate_service(_database, **kwargs):
        assert kwargs == {
            "service_name": "api-node-boats",
            "environment": "bg-qa",
            "intent": "deployment",
            "question": "Explain the deployment flow.",
        }
        return {
            "summary": ["dual deployment detected"],
            "coverage_summary": {"deployment_mode": "multi_plane"},
        }

    monkeypatch.setattr(
        "platform_context_graph.mcp.query_tools.investigation_queries.investigate_service",
        fake_investigate_service,
    )

    result = _Runtime().investigate_service_tool(
        service_name="api-node-boats",
        environment="bg-qa",
        intent="deployment",
        question="Explain the deployment flow.",
    )

    assert result == {
        "summary": ["dual deployment detected"],
        "coverage_summary": {"deployment_mode": "multi_plane"},
    }


def test_investigate_service_tool_requires_service_name() -> None:
    """Reject investigation MCP calls without the required service name."""

    result = _Runtime().investigate_service_tool()

    assert result == {"error": "The 'service_name' argument is required."}
