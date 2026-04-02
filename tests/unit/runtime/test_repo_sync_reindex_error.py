from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest


def test_repo_sync_loop_degrades_after_manual_reindex_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Manual reindex failures should degrade and continue instead of crashing."""

    sync = importlib.import_module("platform_context_graph.runtime.ingester.sync")
    monkeypatch.setenv("PCG_REPO_SYNC_INITIAL_DELAY_SECONDS", "0")

    recorded_statuses: list[dict[str, object]] = []
    completed_requests: list[dict[str, object]] = []
    wait_delays: list[int] = []
    monkeypatch.setattr(
        sync,
        "update_runtime_ingester_status",
        lambda **kwargs: recorded_statuses.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "claim_ingester_reindex_request",
        lambda **_kwargs: {
            "ingester": "repository",
            "reindex_request_token": "reindex-123",
            "requested_force": True,
            "requested_scope": "workspace",
        }
        if not completed_requests
        else None,
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "claim_ingester_scan_request",
        lambda **_kwargs: None,
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "complete_ingester_reindex_request",
        lambda **kwargs: completed_requests.append(kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "invoke_index_workspace",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        raising=False,
    )
    monkeypatch.setattr(
        sync,
        "run_repo_sync_cycle",
        lambda *_args, **_kwargs: SimpleNamespace(discovered=0),
        raising=False,
    )

    def _wait_for_next_cycle(_component: str, delay_seconds: int):
        wait_delays.append(delay_seconds)
        if len(wait_delays) == 1:
            return None
        raise KeyboardInterrupt

    monkeypatch.setattr(sync, "_wait_for_next_cycle", _wait_for_next_cycle)

    with pytest.raises(KeyboardInterrupt):
        sync.run_repo_sync_loop(interval_seconds=900)

    assert completed_requests == [
        {
            "ingester": "repository",
            "request_token": "reindex-123",
            "error_message": "boom",
        }
    ]
    assert any(status["status"] == "degraded" for status in recorded_statuses)
    assert wait_delays[0] > 0
