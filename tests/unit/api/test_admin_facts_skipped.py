"""Tests for skipped work items in the admin facts router."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from platform_context_graph.api.routers import admin_facts


def _utc_now() -> datetime:
    """Return a stable UTC timestamp for skipped admin-router tests."""

    return datetime(2026, 4, 9, 20, 45, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_list_fact_work_items_returns_skipped_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The admin facts list endpoint should expose skipped queue rows."""

    class _FakeQueue:
        enabled = True

        def list_work_items(self, **kwargs):
            assert kwargs == {
                "statuses": ["skipped"],
                "repository_id": "repository:r_archived",
                "source_run_id": None,
                "work_type": None,
                "failure_class": "skipped_repository",
                "limit": 10,
            }
            return [
                SimpleNamespace(
                    work_item_id="work-1",
                    work_type="project-git-facts",
                    repository_id="repository:r_archived",
                    source_run_id="run-123",
                    lease_owner=None,
                    status="skipped",
                    attempt_count=2,
                    last_error="fatal: could not read Username for 'https://github.com'",
                    failure_stage="repo_sync",
                    error_class=None,
                    failure_class="skipped_repository",
                    failure_code="archived_repository",
                    retry_disposition="non_retryable",
                    dead_lettered_at=None,
                    last_attempt_started_at=_utc_now(),
                    last_attempt_finished_at=_utc_now(),
                    next_retry_at=None,
                    operator_note="Repository is archived and excluded by repo-sync policy.",
                    created_at=_utc_now(),
                    updated_at=_utc_now(),
                )
            ]

    monkeypatch.setattr(admin_facts, "get_fact_work_queue", lambda: _FakeQueue())

    response = await admin_facts.list_fact_work_items(
        admin_facts.ListFactWorkItemsRequest(
            statuses=["skipped"],
            repository_id="repository:r_archived",
            failure_class="skipped_repository",
            limit=10,
        )
    )

    assert response["count"] == 1
    assert response["items"][0]["status"] == "skipped"
    assert response["items"][0]["failure_code"] == "archived_repository"
