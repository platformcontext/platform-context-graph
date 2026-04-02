from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.cli import remote, remote_commands


def test_print_json_payload_passes_native_payload() -> None:
    """Remote JSON rendering should pass the native payload to Rich."""

    console = MagicMock()
    payload = {"query": "handle_payment", "count": 1}

    remote.print_json_payload(console, payload)

    console.print_json.assert_called_once_with(data=payload, default=str)


def test_render_remote_index_status_requires_remote_target(
    monkeypatch,
) -> None:
    """Remote index status should require an explicit remote target."""

    captured_kwargs: dict[str, object] = {}
    monkeypatch.setattr(
        remote_commands,
        "resolve_remote_target",
        lambda **kwargs: captured_kwargs.update(kwargs) or SimpleNamespace(),
    )
    monkeypatch.setattr(
        remote_commands,
        "request_json",
        lambda *_args, **_kwargs: {
            "run_id": "run-123",
            "status": "running",
            "finalization_status": "pending",
            "root_path": "/srv/repos",
            "completed_repositories": 1,
            "failed_repositories": 0,
            "pending_repositories": 2,
            "repository_count": 3,
        },
    )

    remote_commands.render_remote_index_status(
        SimpleNamespace(console=MagicMock()),
        target=None,
        service_url="https://pcg.example.com",
        api_key=None,
        profile=None,
    )

    assert captured_kwargs["require_remote"] is True


def test_render_remote_workspace_status_requires_remote_target(
    monkeypatch,
) -> None:
    """Remote workspace status should require an explicit remote target."""

    captured_kwargs: dict[str, object] = {}
    monkeypatch.setattr(
        remote_commands,
        "resolve_remote_target",
        lambda **kwargs: captured_kwargs.update(kwargs) or SimpleNamespace(),
    )
    monkeypatch.setattr(
        remote_commands,
        "request_json",
        lambda *_args, **_kwargs: {
            "ingester": "repository",
            "status": "indexing",
            "active_run_id": "run-123",
            "repository_count": 3,
            "completed_repositories": 1,
            "failed_repositories": 0,
            "pending_repositories": 2,
        },
    )

    remote_commands.render_remote_workspace_status(
        SimpleNamespace(console=MagicMock()),
        service_url="https://pcg.example.com",
        api_key=None,
        profile=None,
    )

    assert captured_kwargs["require_remote"] is True
