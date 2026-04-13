"""Tests for facts-first admin recovery endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from platform_context_graph.api.routers import admin_facts


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for recovery router tests."""

    return datetime(2026, 4, 3, 19, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_dead_letter_fact_work_items_returns_updated_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin recovery endpoint should return dead-lettered rows."""

    class _FakeQueue:
        enabled = True

        def dead_letter_work_items(self, **kwargs):
            assert kwargs == {
                "work_item_ids": None,
                "repository_id": "repository:r_payments",
                "source_run_id": None,
                "work_type": None,
                "failure_class": "manual_override",
                "operator_note": "manual stop",
                "limit": 25,
            }
            return [
                SimpleNamespace(
                    work_item_id="work-1",
                    work_type="project-git-facts",
                    repository_id="repository:r_payments",
                    source_run_id="run-123",
                    status="failed",
                    attempt_count=3,
                    last_error="Operator moved work item to dead letter",
                    failure_stage="operator_action",
                    error_class=None,
                    failure_class="manual_override",
                    failure_code="manual_dead_letter",
                    retry_disposition="manual_review",
                    dead_lettered_at=_utc_now(),
                    last_attempt_started_at=None,
                    last_attempt_finished_at=_utc_now(),
                    next_retry_at=None,
                    operator_note="manual stop",
                    created_at=_utc_now(),
                    updated_at=_utc_now(),
                )
            ]

    monkeypatch.setattr(admin_facts, "get_fact_work_queue", lambda: _FakeQueue())

    response = await admin_facts.dead_letter_fact_work_items(
        admin_facts.DeadLetterFactWorkItemsRequest(
            repository_id="repository:r_payments",
            operator_note="manual stop",
            limit=25,
        )
    )

    assert response["count"] == 1
    assert response["items"][0]["failure_class"] == "manual_override"


@pytest.mark.asyncio
async def test_skip_repository_work_items_returns_skipped_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin skip endpoint should return repository-scoped skipped rows."""

    class _FakeQueue:
        enabled = True

        def skip_repository_work_items(self, **kwargs):
            assert kwargs == {
                "repository_id": "repository:r_archived",
                "operator_note": "historical residue",
            }
            return [
                SimpleNamespace(
                    work_item_id="work-archived-1",
                    work_type="project-git-facts",
                    repository_id="repository:r_archived",
                    source_run_id="run-archived",
                    status="skipped",
                    attempt_count=4,
                    last_error="historical failure",
                    failure_stage="repo_sync",
                    error_class=None,
                    failure_class="skipped_repository",
                    failure_code="archived_repository",
                    retry_disposition="non_retryable",
                    dead_lettered_at=None,
                    last_attempt_started_at=None,
                    last_attempt_finished_at=_utc_now(),
                    next_retry_at=None,
                    operator_note="historical residue",
                    created_at=_utc_now(),
                    updated_at=_utc_now(),
                )
            ]

    monkeypatch.setattr(admin_facts, "get_fact_work_queue", lambda: _FakeQueue())

    response = await admin_facts.skip_repository_fact_work_items(
        admin_facts.SkipRepositoryFactWorkItemsRequest(
            repository_id="repository:r_archived",
            operator_note="historical residue",
        )
    )

    assert response["count"] == 1
    assert response["items"][0]["status"] == "skipped"
    assert response["items"][0]["failure_code"] == "archived_repository"


@pytest.mark.asyncio
async def test_skip_repository_work_items_requires_repository_id() -> None:
    """The admin skip endpoint should reject unscoped requests."""

    with pytest.raises(HTTPException) as exc_info:
        await admin_facts.skip_repository_fact_work_items(
            admin_facts.SkipRepositoryFactWorkItemsRequest(repository_id="")
        )

    assert exc_info.value.status_code == 400
    assert "repository_id" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_request_fact_backfill_returns_durable_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin backfill endpoint should return the created request row."""

    class _FakeQueue:
        enabled = True

        def request_backfill(self, **kwargs):
            assert kwargs == {
                "repository_id": "repository:r_payments",
                "source_run_id": "run-123",
                "operator_note": "refresh after replay",
            }
            return SimpleNamespace(
                backfill_request_id="fact-backfill:1",
                repository_id="repository:r_payments",
                source_run_id="run-123",
                operator_note="refresh after replay",
                created_at=_utc_now(),
            )

    monkeypatch.setattr(admin_facts, "get_fact_work_queue", lambda: _FakeQueue())

    response = await admin_facts.request_fact_backfill(
        admin_facts.RequestFactBackfillRequest(
            repository_id="repository:r_payments",
            source_run_id="run-123",
            operator_note="refresh after replay",
        )
    )

    assert response["status"] == "accepted"
    assert response["backfill_request"]["backfill_request_id"] == "fact-backfill:1"


@pytest.mark.asyncio
async def test_list_fact_replay_events_returns_durable_audit_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin replay-events endpoint should list durable replay records."""

    class _FakeQueue:
        enabled = True

        def list_replay_events(self, **kwargs):
            assert kwargs == {
                "repository_id": "repository:r_payments",
                "source_run_id": None,
                "work_item_id": "work-1",
                "failure_class": "timeout",
                "limit": 10,
            }
            return [
                SimpleNamespace(
                    replay_event_id="fact-replay:1",
                    work_item_id="work-1",
                    repository_id="repository:r_payments",
                    source_run_id="run-123",
                    work_type="project-git-facts",
                    failure_class="timeout",
                    operator_note="operator replay",
                    created_at=_utc_now(),
                )
            ]

    monkeypatch.setattr(admin_facts, "get_fact_work_queue", lambda: _FakeQueue())

    response = await admin_facts.list_fact_replay_events(
        admin_facts.ListFactReplayEventsRequest(
            repository_id="repository:r_payments",
            work_item_id="work-1",
            failure_class="timeout",
            limit=10,
        )
    )

    assert response["count"] == 1
    assert response["events"][0]["replay_event_id"] == "fact-replay:1"
