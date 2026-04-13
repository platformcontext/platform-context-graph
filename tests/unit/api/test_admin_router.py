"""Unit tests for the admin router endpoints (reindex, tuning report)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from platform_context_graph.api.routers import admin


@pytest.mark.asyncio
async def test_reindex_persists_async_request_and_returns_acceptance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin reindex should enqueue work for the ingester instead of doing it inline."""

    monkeypatch.setattr(
        admin,
        "request_ingester_reindex_control",
        lambda _database, *, ingester, requested_by, force, scope: {
            "runtime_family": "ingester",
            "ingester": ingester,
            "provider": ingester,
            "reindex_request_token": "reindex-123",
            "reindex_request_state": "pending",
            "reindex_requested_at": "2026-04-02T16:00:00+00:00",
            "reindex_requested_by": requested_by,
            "requested_force": force,
            "requested_scope": scope,
            "run_id": None,
        },
    )

    response = await admin.reindex(database=object())

    assert response["status"] == "accepted"
    assert response["ingester"] == "repository"
    assert response["request_token"] == "reindex-123"
    assert response["request_state"] == "pending"
    assert response["force"] is True
    assert response["scope"] == "workspace"


@pytest.mark.asyncio
async def test_reindex_rejects_unknown_scope() -> None:
    """The initial admin reindex API should validate the supported scope contract."""

    with pytest.raises(HTTPException) as exc_info:
        await admin.reindex(
            admin.ReindexRequest(scope="repo"),
            database=object(),
        )

    assert exc_info.value.status_code == 400
    assert "workspace" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_shared_projection_tuning_report_returns_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin router should expose the deterministic tuning report payload."""

    monkeypatch.setattr(
        admin,
        "build_tuning_report",
        lambda **kwargs: {
            "projection_domains": ["repo_dependency"],
            "include_platform": kwargs["include_platform"],
            "recommended": {"setting": "4x2"},
        },
    )

    response = await admin.shared_projection_tuning_report(include_platform=True)

    assert response["include_platform"] is True
    assert response["recommended"]["setting"] == "4x2"
