"""Unit tests for the admin refinalize router contract."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from platform_context_graph.api.routers import admin


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return list(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def run(self, query, **_kwargs):
        assert "MATCH (r:Repository)" in query
        return _FakeResult(self._rows)


def _reset_state() -> None:
    admin._finalization_state.clear()
    admin._finalization_state.update(
        {
            "running": False,
            "run_id": None,
            "stages": None,
            "current_stage": None,
            "stage_details": {},
            "targeted_repo_ids": [],
            "targeted_repo_count": 0,
            "last_run_at": None,
            "last_duration_seconds": None,
            "last_timings": None,
            "last_error": None,
            "repo_count": 0,
        }
    )


@pytest.fixture(autouse=True)
def _clean_admin_state():
    _reset_state()
    yield
    _reset_state()


@pytest.mark.asyncio
async def test_refinalize_returns_run_id_and_target_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starting admin refinalize should return the run metadata immediately."""

    started_threads: list[tuple[object, tuple[object, ...]]] = []

    class _FakeThread:
        def __init__(self, *, target, args, name, daemon):
            assert name == "refinalize-worker"
            assert daemon is True
            started_threads.append((target, args))

        def start(self) -> None:
            return None

    monkeypatch.setattr(admin.threading, "Thread", _FakeThread)

    database = SimpleNamespace(
        get_driver=lambda: SimpleNamespace(
            session=lambda: _FakeSession(
                [
                    {"repo_id": "repository:r_payments", "p": "/repos/payments-api"},
                    {"repo_id": "repository:r_orders", "p": "/repos/orders-api"},
                ]
            )
        )
    )

    response = await admin.refinalize(
        admin.RefinalizeRequest(stages=["workloads"], repo_ids=None),
        database=database,
    )

    assert response["status"] == "started"
    assert response["stages"] == ["workloads"]
    assert response["targeted_repo_ids"] == [
        "repository:r_payments",
        "repository:r_orders",
    ]
    assert response["targeted_repo_count"] == 2
    assert response["run_id"].startswith("refinalize-api-")
    assert len(started_threads) == 1


@pytest.mark.asyncio
async def test_refinalize_rejects_relationship_resolution_repo_subset() -> None:
    """Relationship resolution should stay full-generation for this API."""

    with pytest.raises(HTTPException) as exc_info:
        await admin.refinalize(
            admin.RefinalizeRequest(
                stages=["workloads", "relationship_resolution"],
                repo_ids=["repository:r_payments"],
            ),
            database=object(),
        )

    assert exc_info.value.status_code == 400
    assert "relationship_resolution" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_refinalize_status_returns_current_stage_details() -> None:
    """Status should expose the active run id, stage, and detail payload."""

    admin._finalization_state.update(
        {
            "running": True,
            "run_id": "refinalize-api-123",
            "stages": ["workloads"],
            "current_stage": "workloads",
            "stage_details": {"status": "started", "repo_count": 4},
            "targeted_repo_ids": ["repository:r_payments"],
            "targeted_repo_count": 1,
            "repo_count": 1,
        }
    )

    response = await admin.refinalize_status()

    assert response["running"] is True
    assert response["run_id"] == "refinalize-api-123"
    assert response["current_stage"] == "workloads"
    assert response["stage_details"] == {"status": "started", "repo_count": 4}
    assert response["targeted_repo_count"] == 1


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
async def test_replay_failed_facts_returns_replayed_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin replay should return the replayed work-item ids."""

    class _FakeQueue:
        def replay_failed_work_items(self, **kwargs):
            assert kwargs == {
                "work_item_ids": ["work-1"],
                "repository_id": None,
                "source_run_id": None,
                "work_type": None,
                "limit": 100,
            }
            return [
                SimpleNamespace(
                    work_item_id="work-1",
                    work_type="project-git-facts",
                    repository_id="repository:r_payments",
                    source_run_id="run-123",
                    attempt_count=0,
                )
            ]

    monkeypatch.setattr(admin, "get_fact_work_queue", lambda: _FakeQueue())

    response = await admin.replay_failed_facts(
        admin.ReplayFailedFactsRequest(work_item_ids=["work-1"]),
    )

    assert response["status"] == "replayed"
    assert response["replayed_count"] == 1
    assert response["work_item_ids"] == ["work-1"]


@pytest.mark.asyncio
async def test_replay_failed_facts_requires_a_selector() -> None:
    """Admin replay should reject unbounded replay requests."""

    with pytest.raises(HTTPException) as exc_info:
        await admin.replay_failed_facts(admin.ReplayFailedFactsRequest())

    assert exc_info.value.status_code == 400
    assert "selector" in str(exc_info.value.detail)
