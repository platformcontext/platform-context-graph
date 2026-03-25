"""Unit tests for MCP runtime-status tool helpers."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.mcp import runtime_tools


class _Server(runtime_tools.RuntimeStatusToolMixin):
    """Minimal runtime-tools host used to exercise the mixin directly."""

    db_manager = object()


def test_get_index_status_tool_defaults_to_checkpoint_target(monkeypatch) -> None:
    """MCP index-status should use the configured checkpoint root by default."""

    captured_target = {}
    monkeypatch.setattr(
        runtime_tools.status_queries,
        "default_index_status_target",
        lambda _ingester="repository": Path("/srv/repos"),
    )

    def fake_describe_index_run(target):
        captured_target["value"] = target
        return {"run_id": "run-123", "status": "running"}

    monkeypatch.setattr(
        runtime_tools,
        "describe_index_run",
        fake_describe_index_run,
    )

    result = _Server().get_index_status_tool()

    assert captured_target["value"] == Path("/srv/repos")
    assert result == {"run_id": "run-123", "status": "running"}
