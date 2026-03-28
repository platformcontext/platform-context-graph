"""Unit tests for MCP runtime-status tool helpers."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.mcp import runtime_tools
from platform_context_graph.mcp.tools.runtime import RUNTIME_TOOLS


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


def test_get_index_status_tool_resolves_repo_names_before_lookup(
    monkeypatch,
) -> None:
    """Repo-name targets should resolve to the indexed repository path."""

    captured_target = {}
    monkeypatch.setattr(
        runtime_tools.status_queries,
        "resolve_index_status_target",
        lambda _database, *, target, ingester="repository": Path(
            "/srv/repos/api-node-boats"
        ),
    )

    def fake_describe_index_run(target):
        captured_target["value"] = target
        return {"run_id": "run-456", "status": "completed"}

    monkeypatch.setattr(runtime_tools, "describe_index_run", fake_describe_index_run)

    result = _Server().get_index_status_tool(target="api-node-boats")

    assert captured_target["value"] == Path("/srv/repos/api-node-boats")
    assert result == {"run_id": "run-456", "status": "completed"}


def test_get_index_status_schema_describes_checkpoint_root_default() -> None:
    """Tool schema should match the checkpoint-root default behavior."""

    description = RUNTIME_TOOLS["get_index_status"]["inputSchema"]["properties"][
        "target"
    ]["description"]

    assert "checkpoint root" in description
    assert "current working directory" not in description
