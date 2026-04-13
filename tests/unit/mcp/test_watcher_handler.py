"""Tests for MCP watch handler ownership boundaries."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from platform_context_graph.mcp.tools.handlers import watcher


def test_watch_directory_uses_go_owned_initial_scan_without_duplicate_handler_scan(
    tmp_path: Path,
) -> None:
    """Unindexed watch requests should start one scan and register watchers cold."""

    repo_path = tmp_path / "repo"
    repo_path.mkdir()

    watch_calls: list[dict[str, object]] = []
    add_code_calls: list[dict[str, object]] = []

    code_watcher = SimpleNamespace(
        watched_paths=set(),
        watch_directory=lambda *args, **kwargs: watch_calls.append(
            {"args": args, "kwargs": kwargs}
        ),
    )

    result = watcher.watch_directory(
        code_watcher,
        lambda: {"repositories": []},
        lambda **kwargs: add_code_calls.append(kwargs) or {"job_id": "job-123"},
        path=str(repo_path),
        scope="workspace",
    )

    assert result["success"] is True
    assert result["job_id"] == "job-123"
    assert add_code_calls == [
        {"path": str(repo_path.resolve()), "is_dependency": False},
    ]
    assert watch_calls == [
        {
            "args": (str(repo_path.resolve()),),
            "kwargs": {
                "perform_initial_scan": False,
                "scope": "workspace",
                "include_repositories": None,
                "exclude_repositories": None,
            },
        }
    ]
